from hashlib import sha256
from typing import Annotated, Never
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from core.config import now
from stocktakes.events import CHANNEL
from stocktakes.models import Stocktake, StocktakeLine, StocktakeRequest
from stocktakes.queries import StocktakeQueries
from stocktakes.schemas import Acknowledgement, AddLine, DeleteLine, EditLine, name_key


def conflict(code: str, message: str, line_id: int | None = None) -> Never:
    raise HTTPException(
        status_code=409,
        detail={"code": code, "message": message, "line_id": line_id},
    )


class StocktakeService(StocktakeQueries):
    async def advance_version(self, doc: Stocktake) -> None:
        doc.version += 1
        # PostgreSQL delivers the revision only if the whole transaction commits
        await self.session.execute(
            statement=select(
                func.pg_notify(
                    CHANNEL,
                    f"{doc.id}:{doc.version}",
                ),
            ),
        )

    async def replay(self, request_id: UUID, signature: str) -> Acknowledgement | None:
        receipt = await self.session.get(
            entity=StocktakeRequest,
            ident=request_id,
        )
        if receipt is None:
            return None
        if receipt.signature != signature:
            conflict(
                code="request_reused",
                message="Этот запрос уже использован для другого действия",
            )
        return Acknowledgement(
            document_id=receipt.document_id,
            line_id=receipt.line_id,
        )

    async def acknowledge(
        self, request_id: UUID, signature: str, doc: Stocktake, line_id: int | None
    ) -> Acknowledgement:
        self.session.add(
            instance=StocktakeRequest(
                id=request_id,
                signature=signature,
                document_id=doc.id,
                line_id=line_id,
            ),
        )
        try:
            await self.session.commit()
        except IntegrityError:
            # another document can receive the same request id under a different lock
            await self.session.rollback()
            previous = await self.replay(
                request_id=request_id,
                signature=signature,
            )
            if previous:
                return previous
            raise
        return Acknowledgement(
            document_id=doc.id,
            line_id=line_id,
        )

    async def open(self, request_id: UUID) -> Acknowledgement:
        # starts must also serialize when there is no document yet to lock
        await self.session.execute(
            statement=select(
                func.pg_advisory_xact_lock(
                    63902438,
                ),
            ),
        )
        previous = await self.replay(
            request_id=request_id,
            signature="open",
        )
        if previous:
            return previous
        doc = await self.session.scalar(
            statement=select(
                Stocktake,
            )
            .where(
                Stocktake.completed_at.is_(
                    other=None,
                ),
            )
            .with_for_update(),
        )
        if doc is None:
            doc = Stocktake()
            self.session.add(
                instance=doc,
            )
            await self.session.flush()
        return await self.acknowledge(
            request_id=request_id,
            signature="open",
            doc=doc,
            line_id=None,
        )

    async def change_line(
        self,
        document_id: int,
        line_id: int | None,
        payload: AddLine | EditLine | DeleteLine,
        correction: bool,
    ) -> Acknowledgement:
        doc = await self.get(
            document_id=document_id,
            writing=True,
        )
        # omit unused fields so retries match receipts created before amount entry existed
        digest = sha256(
            data=payload.model_dump_json(
                exclude_none=True,
            ).encode(),
        ).hexdigest()
        signature = f"{document_id}/{line_id}/{correction}/{digest}"
        previous = await self.replay(
            request_id=payload.request_id,
            signature=signature,
        )
        if previous:
            return previous
        if (doc.completed_at is not None) != correction:
            conflict(
                code="document_state",
                message="Статус переучёта изменился. Для завершённого документа выберите «Исправить»",
            )

        if isinstance(
            payload,
            (EditLine, DeleteLine),
        ):
            line = await self.session.scalar(
                statement=select(
                    StocktakeLine,
                ).where(
                    StocktakeLine.document_id == doc.id,
                    StocktakeLine.id == line_id,
                ),
            )
            if line is None:
                conflict(
                    code="line_deleted",
                    message="Коллега удалил эту строку",
                    line_id=line_id,
                )
            if line.version != payload.version:
                conflict(
                    code="line_changed",
                    message="Коллега изменил эту строку",
                    line_id=line_id,
                )
            line.version += 1
        else:
            line = StocktakeLine(
                document_id=doc.id,
            )

        if isinstance(
            payload,
            DeleteLine,
        ):
            await self.session.delete(
                instance=line,
            )
        else:
            key = name_key(
                name=payload.name,
            )
            duplicate = await self.session.scalar(
                statement=select(
                    StocktakeLine.id,
                ).where(
                    StocktakeLine.document_id == doc.id,
                    StocktakeLine.name_key == key,
                ),
            )
            if duplicate is not None and duplicate != line_id:
                conflict(
                    code="duplicate",
                    message="Такое название уже в переучёте",
                    line_id=duplicate,
                )
            line.name = payload.name
            line.name_key = key
            line.price = payload.price
            line.unit = payload.unit
            line.quantity = payload.quantity
            line.entered_amount = payload.entered_amount
            self.session.add(
                instance=line,
            )
        await self.advance_version(
            doc=doc,
        )
        await self.session.flush()
        return await self.acknowledge(
            request_id=payload.request_id,
            signature=signature,
            doc=doc,
            line_id=line.id,
        )

    async def complete(self, document_id: int, version: int) -> None:
        doc = await self.get(
            document_id=document_id,
            writing=True,
        )
        if doc.completed_at is not None:
            return
        if version != doc.version:
            conflict(
                code="document_changed",
                message="Состав переучёта изменился. Проверьте обновлённый итог",
            )
        doc.completed_at = now()
        await self.advance_version(
            doc=doc,
        )
        await self.session.commit()


ServiceDep = Annotated[
    StocktakeService,
    Depends(
        dependency=StocktakeService,
    ),
]
