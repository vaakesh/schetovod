from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, Field, field_validator, model_validator

from core.enums import StocktakeUnit
from core.schema_types import Money, parse_decimal


def decimal_separator(value: object) -> object:
    if isinstance(
        value,
        str,
    ):
        return value.replace(
            ",",
            ".",
        )
    return value


def name_key(name: str) -> str:
    return (
        " ".join(
            name.split(),
        )
        .lower()
        .replace(
            "ё",
            "е",
        )
    )


class RequestId(BaseModel):
    request_id: UUID


class Version(BaseModel):
    version: Annotated[
        int,
        Field(
            gt=0,
        ),
    ]


class DeleteLine(RequestId, Version):
    pass


StocktakeMoney = Annotated[
    Money,
    BeforeValidator(
        func=decimal_separator,
    ),
]
StocktakeQuantity = Annotated[
    Decimal,
    Field(
        ge=0,
        max_digits=12,
        decimal_places=3,
    ),
    BeforeValidator(
        func=parse_decimal,
    ),
    BeforeValidator(
        func=decimal_separator,
    ),
]


class AddLine(RequestId):
    name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=300,
        ),
    ]
    unit: StocktakeUnit
    price: StocktakeMoney | None = None
    quantity: StocktakeQuantity | None = None
    entered_amount: StocktakeMoney | None = None

    @field_validator(
        "name",
        mode="before",
    )
    @classmethod
    def clean_name(cls, value: object) -> object:
        if isinstance(
            value,
            str,
        ):
            return " ".join(
                value.split(),
            )
        return value

    @model_validator(
        mode="after",
    )
    def validate_measurement(self) -> Self:
        if (self.quantity is None) == (self.entered_amount is None):
            raise ValueError(
                "Введите либо количество, либо общую сумму",
            )
        if self.quantity is None:
            return self
        if self.price is None:
            raise ValueError(
                "Для остатка в штуках или килограммах укажите цену за единицу",
            )
        if self.unit == StocktakeUnit.PIECE and self.quantity % 1:
            raise ValueError(
                "Количество в штуках должно быть целым",
            )
        return self


class EditLine(AddLine, Version):
    pass


class Line(BaseModel):
    id: int
    name: str
    unit: StocktakeUnit
    price: Decimal | None
    quantity: Decimal | None
    amount: Decimal
    version: int


class Summary(BaseModel):
    id: int
    started_at: datetime
    completed_at: datetime | None
    version: int
    line_count: int
    total: Decimal


class Document(Summary):
    lines: list[Line]


class Suggestion(BaseModel):
    name: str
    unit: StocktakeUnit
    price: Decimal | None
    current_line_id: int | None
    current_quantity: Decimal | None
    current_amount: Decimal | None


class Acknowledgement(BaseModel):
    document_id: int
    line_id: int | None
