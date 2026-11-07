from collections.abc import Sequence
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from core.enums import PriceTagOrigin, PriceTagUnit
from core.http import conflict, invalid
from price_tags.models import PriceTag
from price_tags.pdf import PriceTagError, PrintedTag, price_tags_pdf
from price_tags.repository import PriceTagRepositoryDep
from price_tags.schemas import GeneralTag, PriceTagFields, PriceTagOut, PrintRequest

UNIT_LABELS = {
    PriceTagUnit.PIECE: "ШТ.",
    PriceTagUnit.WEIGHT: "ВЕС",
}
ORIGIN_LABELS = {
    PriceTagOrigin.MAKER: "Производитель",
    PriceTagOrigin.COUNTRY: "Страна",
}
# separates the fields of the key, never typed in a form
KEY_SEPARATOR = "\x1f"


def normalized(text: str | None) -> str:
    """case, line breaks and no-break spaces do not make another tag"""
    return " ".join(
        (text or "").split(),
    ).casefold()


def price_tag_key(tag: PriceTagFields) -> str:
    return KEY_SEPARATOR.join(
        (
            f"{tag.width_mm}x{tag.height_mm}",
            tag.unit.value,
            normalized(
                text=tag.pack,
            ),
            normalized(
                text=tag.name,
            ),
            normalized(
                text=tag.subtitle,
            ),
            "" if tag.price is None else f"{tag.price:.2f}",
            tag.origin.value,
            normalized(
                text=tag.origin_name,
            ),
        ),
    )


def price_tag_values(tag: PriceTagFields) -> dict[str, Any]:
    """the columns of a new row, the texts are kept as typed"""
    return {
        "width_mm": tag.width_mm,
        "height_mm": tag.height_mm,
        "unit": tag.unit,
        "pack": tag.pack,
        "name": tag.name,
        "subtitle": tag.subtitle,
        "price": tag.price,
        "origin": tag.origin,
        "origin_name": tag.origin_name,
        "dedup_key": price_tag_key(
            tag=tag,
        ),
    }


def unique_values(tags: Sequence[PriceTagFields]) -> list[dict[str, Any]]:
    """one row per key, the first spelling wins"""
    rows: dict[str, dict[str, Any]] = {}
    for tag in tags:
        values = price_tag_values(
            tag=tag,
        )
        rows.setdefault(
            values["dedup_key"],
            values,
        )
    return list(
        rows.values(),
    )


def general_tag_fields(tag: GeneralTag) -> PriceTagFields:
    """a general.json record in the form of the api, both empty rub and kop mean no price"""
    blank_price = tag.rub == "" and tag.kop == ""
    return PriceTagFields.model_validate(
        obj={
            "width_mm": tag.w,
            "height_mm": tag.h,
            "unit": PriceTagUnit.PIECE if tag.left == "ШТ." else PriceTagUnit.WEIGHT,
            "pack": tag.right,
            "name": tag.name,
            "subtitle": tag.sub,
            "price": None if blank_price else f"{int(tag.rub)}.{int(tag.kop):02d}",
            "origin": (
                PriceTagOrigin.MAKER
                if tag.foot_label == "Производитель"
                else PriceTagOrigin.COUNTRY
            ),
            "origin_name": tag.foot,
        },
    )


def printed_tag(tag: PriceTagFields) -> PrintedTag:
    if tag.price is None:
        rub = ""
        kop = ""
    else:
        kopecks = int(
            tag.price * 100,
        )
        rub = str(
            kopecks // 100,
        )
        kop = f"{kopecks % 100:02d}"
    return PrintedTag(
        width_mm=tag.width_mm,
        height_mm=tag.height_mm,
        left=UNIT_LABELS[tag.unit],
        right=tag.pack or "",
        name=tag.name,
        sub=tag.subtitle or "",
        rub=rub,
        kop=kop,
        foot_label=ORIGIN_LABELS[tag.origin],
        foot=tag.origin_name,
    )


def price_tag_out(tag: PriceTag) -> PriceTagOut:
    return PriceTagOut(
        id=tag.id,
        width_mm=tag.width_mm,
        height_mm=tag.height_mm,
        unit=tag.unit,
        pack=tag.pack,
        name=tag.name,
        subtitle=tag.subtitle,
        price=tag.price,
        origin=tag.origin,
        origin_name=tag.origin_name,
        created_at=tag.created_at,
    )


class PriceTagService:
    def __init__(
        self,
        tags: PriceTagRepositoryDep,
    ) -> None:
        self.tags = tags

    async def search(
        self,
        query: str,
        limit: int,
    ) -> list[PriceTagOut]:
        words = query.split()
        if not words:
            return []
        found = await self.tags.search(
            words=words,
            prefix=" ".join(
                words,
            ),
            limit=limit,
        )
        return [
            price_tag_out(
                tag=tag,
            )
            for tag in found
        ]

    async def print_pdf(
        self,
        request: PrintRequest,
    ) -> bytes:
        """the PDF of the rows, new tags are remembered for the next search"""
        printed = [
            printed_tag(
                tag=row,
            )
            for row in request.rows
            for _ in range(row.quantity)
        ]
        # a tag that does not print is not saved either
        try:
            pdf = await run_in_threadpool(
                func=price_tags_pdf,
                tags=printed,
            )
        except PriceTagError as error:
            invalid(
                detail=str(
                    error,
                ),
            )
        await self.tags.add_missing(
            tags=unique_values(
                tags=request.rows,
            ),
        )
        await self.tags.commit()
        return pdf

    async def all_tags(self) -> list[PriceTagOut]:
        """the whole base, a few thousand rows at most, the page filters it itself"""
        return [
            price_tag_out(
                tag=tag,
            )
            for tag in await self.tags.all()
        ]

    async def edit(
        self,
        tag_id: int,
        fields: PriceTagFields,
    ) -> PriceTagOut:
        tag = await self._get(
            tag_id=tag_id,
        )
        key = price_tag_key(
            tag=fields,
        )
        same = await self.tags.find_by_key(
            dedup_key=key,
        )
        if same is not None and same.id != tag.id:
            conflict(
                detail="Точно такой ценник уже есть в базе",
            )
        # a tag that does not print is not saved either
        await self._check_prints(
            fields=fields,
        )
        for column, value in price_tag_values(
            tag=fields,
        ).items():
            setattr(
                tag,
                column,
                value,
            )
        await self.tags.commit()
        return price_tag_out(
            tag=tag,
        )

    async def delete(
        self,
        tag_id: int,
    ) -> None:
        tag = await self._get(
            tag_id=tag_id,
        )
        await self.tags.delete(
            tag=tag,
        )
        await self.tags.commit()

    async def _get(
        self,
        tag_id: int,
    ) -> PriceTag:
        tag = await self.tags.get(
            tag_id=tag_id,
        )
        if tag is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ценник не найден, обновите страницу",
            )
        return tag

    async def _check_prints(
        self,
        fields: PriceTagFields,
    ) -> None:
        try:
            await run_in_threadpool(
                func=price_tags_pdf,
                tags=[
                    printed_tag(
                        tag=fields,
                    ),
                ],
            )
        except PriceTagError as error:
            invalid(
                detail=str(
                    error,
                ),
            )


PriceTagServiceDep = Annotated[
    PriceTagService,
    Depends(
        dependency=PriceTagService,
    ),
]
