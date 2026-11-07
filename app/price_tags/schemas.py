from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)

from core.enums import PriceTagOrigin, PriceTagUnit
from core.schema_types import FormModel, Money, Text
from price_tags.pdf import SIZES

MAX_TEXT = 200
MAX_COPIES = 100
MAX_ROWS = 200
# about 25 sheets of the smallest tags
MAX_TAGS = 500


def blank_to_none(value: object) -> object:
    """an empty field of the form means the tag has no such line"""
    if (
        isinstance(
            value,
            str,
        )
        and not value.strip()
    ):
        return None
    return value


TagText = Annotated[
    Text,
    Field(
        max_length=MAX_TEXT,
    ),
]
OptionalTagText = Annotated[
    Annotated[
        str,
        Field(
            max_length=MAX_TEXT,
        ),
    ]
    | None,
    BeforeValidator(
        func=blank_to_none,
    ),
]


class PriceTagFields(FormModel):
    """everything printed on a tag"""

    width_mm: int
    height_mm: int
    # the form sends the plain value, a strict model expects an enum member
    unit: Annotated[
        PriceTagUnit,
        Field(
            strict=False,
        ),
    ]
    pack: OptionalTagText
    name: TagText
    subtitle: OptionalTagText
    # None leaves the price blank, it is written by hand
    price: Money | None
    origin: Annotated[
        PriceTagOrigin,
        Field(
            strict=False,
        ),
    ]
    origin_name: TagText

    @model_validator(
        mode="after",
    )
    def known_size(self) -> Self:
        if (self.width_mm, self.height_mm) not in SIZES:
            raise ValueError(
                "Размер ценника — 4×5, 5×8, 6×7 или 7×10 см",
            )
        return self


class PriceTagOut(BaseModel):
    id: int
    width_mm: int
    height_mm: int
    unit: PriceTagUnit
    pack: str | None
    name: str
    subtitle: str | None
    price: Decimal | None
    origin: PriceTagOrigin
    origin_name: str


class PrintRow(PriceTagFields):
    # copies of the same tag
    quantity: Annotated[
        int,
        Field(
            ge=1,
            le=MAX_COPIES,
        ),
    ]


class PrintRequest(FormModel):
    rows: Annotated[
        list[PrintRow],
        Field(
            min_length=1,
            max_length=MAX_ROWS,
        ),
    ]

    @model_validator(
        mode="after",
    )
    def not_too_many(self) -> Self:
        if sum(row.quantity for row in self.rows) > MAX_TAGS:
            raise ValueError(
                f"За раз можно напечатать не больше {MAX_TAGS} ценников",
            )
        return self


class GeneralTag(BaseModel):
    """a record of general.json from the cenniki-v2 skill"""

    model_config = ConfigDict(
        extra="forbid",
    )

    w: int
    h: int
    left: Literal["ШТ.", "ВЕС"]
    right: str
    name: str
    sub: str = ""
    rub: str
    kop: str = "00"
    foot_label: Literal["Производитель", "Страна"]
    foot: str
    # a size off the list printed once on request, the shop list keeps only the four sizes
    custom: bool = False
