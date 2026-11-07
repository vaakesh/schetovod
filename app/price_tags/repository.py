from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert

from core.db import SessionDep
from price_tags.models import PriceTag

# an insert has a limit of 32767 parameters, a tag takes 10
BATCH_SIZE = 1000
# a line break and a no-break space
SPACES = "\n" + chr(0xA0)


def searchable(text: Any) -> Any:
    """line breaks and no-break spaces shape the print, a search sees them as spaces"""
    return func.translate(
        text,
        SPACES,
        " " * len(SPACES),
    )


class PriceTagRepository:
    def __init__(
        self,
        session: SessionDep,
    ) -> None:
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def get(
        self,
        tag_id: int,
    ) -> PriceTag | None:
        return await self.session.get(
            entity=PriceTag,
            ident=tag_id,
        )

    async def find_by_key(
        self,
        dedup_key: str,
    ) -> PriceTag | None:
        return await self.session.scalar(
            statement=select(
                PriceTag,
            ).where(
                PriceTag.dedup_key == dedup_key,
            ),
        )

    async def all(self) -> list[PriceTag]:
        result = await self.session.scalars(
            statement=select(
                PriceTag,
            ).order_by(
                PriceTag.name,
                PriceTag.id,
            ),
        )
        return list(
            result.all(),
        )

    async def delete(
        self,
        tag: PriceTag,
    ) -> None:
        await self.session.delete(
            instance=tag,
        )

    async def add_missing(
        self,
        tags: list[dict[str, Any]],
    ) -> int:
        """inserts the tags whose dedup_key is new, returns how many were added"""
        added = 0
        for start in range(
            0,
            len(
                tags,
            ),
            BATCH_SIZE,
        ):
            result = await self.session.scalars(
                statement=insert(
                    table=PriceTag,
                )
                .values(
                    tags[start : start + BATCH_SIZE],
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        PriceTag.dedup_key,
                    ],
                )
                .returning(
                    PriceTag.id,
                ),
            )
            added += len(
                result.all(),
            )
        return added

    async def search(
        self,
        words: list[str],
        prefix: str,
        limit: int,
    ) -> list[PriceTag]:
        """tags whose name and subtitle contain every word, the names starting with the prefix first"""
        text = searchable(
            text=PriceTag.name
            + " "
            + func.coalesce(
                PriceTag.subtitle,
                "",
            ),
        )
        name = searchable(
            text=PriceTag.name,
        )
        result = await self.session.scalars(
            statement=select(
                PriceTag,
            )
            .where(
                *(
                    text.icontains(
                        other=word,
                        autoescape=True,
                    )
                    for word in words
                ),
            )
            .order_by(
                case(
                    (
                        name.istartswith(
                            other=prefix,
                            autoescape=True,
                        ),
                        0,
                    ),
                    else_=1,
                ),
                PriceTag.name,
                PriceTag.subtitle,
                PriceTag.id.desc(),
            )
            .limit(
                limit=limit,
            ),
        )
        return list(
            result.all(),
        )


PriceTagRepositoryDep = Annotated[
    PriceTagRepository,
    Depends(
        dependency=PriceTagRepository,
    ),
]
