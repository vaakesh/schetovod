import re
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
)

DECIMAL_PATTERN = r"[0-9]+(?:\.[0-9]+)?"
LINE_NO_PATTERN = r"[0-9]+"
MAX_LINE_NO = 2_147_483_647
DATE_PATTERN = r"[0-9]{2}-[0-9]{2}-[0-9]{4}"


def parse_decimal(value: object) -> Decimal:
    if (
        not isinstance(
            value,
            str,
        )
        or re.fullmatch(
            pattern=DECIMAL_PATTERN,
            string=value,
        )
        is None
    ):
        raise ValueError(
            "Expected a decimal string with a dot separator",
        )
    return Decimal(
        value=value,
    )


def parse_line_no(value: object) -> int:
    if (
        not isinstance(
            value,
            str,
        )
        or re.fullmatch(
            pattern=LINE_NO_PATTERN,
            string=value,
        )
        is None
    ):
        raise ValueError(
            "Expected an integer string",
        )
    return int(
        value,
    )


def parse_invoice_date(value: object) -> date:
    if (
        not isinstance(
            value,
            str,
        )
        or re.fullmatch(
            pattern=DATE_PATTERN,
            string=value,
        )
        is None
    ):
        raise ValueError(
            "Expected a date string in DD-MM-YYYY format",
        )
    return date.strptime(
        value,
        "%d-%m-%Y",
    )


def format_invoice_date(value: date) -> str:
    return f"{value.day:02d}-{value.month:02d}-{value.year:04d}"


Money = Annotated[
    Decimal,
    Field(
        ge=0,
        max_digits=14,
        decimal_places=2,
        allow_inf_nan=False,
    ),
    BeforeValidator(
        func=parse_decimal,
        json_schema_input_type=Annotated[
            str,
            Field(
                pattern=rf"^{DECIMAL_PATTERN}$",
            ),
        ],
    ),
]
Quantity = Annotated[
    Decimal,
    Field(
        gt=0,
        max_digits=12,
        decimal_places=3,
        allow_inf_nan=False,
    ),
    BeforeValidator(
        func=parse_decimal,
        json_schema_input_type=Annotated[
            str,
            Field(
                pattern=rf"^{DECIMAL_PATTERN}$",
            ),
        ],
    ),
]
VatPercent = Annotated[
    Decimal,
    Field(
        ge=0,
        le=100,
        max_digits=5,
        decimal_places=2,
        allow_inf_nan=False,
    ),
    BeforeValidator(
        func=parse_decimal,
        json_schema_input_type=Annotated[
            str,
            Field(
                pattern=rf"^{DECIMAL_PATTERN}$",
            ),
        ],
    ),
]
LineNo = Annotated[
    int,
    Field(
        gt=0,
        le=MAX_LINE_NO,
    ),
    BeforeValidator(
        func=parse_line_no,
        json_schema_input_type=Annotated[
            str,
            Field(
                pattern=rf"^{LINE_NO_PATTERN}$",
            ),
        ],
    ),
    PlainSerializer(
        func=str,
        return_type=str,
    ),
]
InvoiceDate = Annotated[
    date,
    BeforeValidator(
        func=parse_invoice_date,
        json_schema_input_type=Annotated[
            str,
            Field(
                pattern=rf"^{DATE_PATTERN}$",
            ),
        ],
    ),
    PlainSerializer(
        func=format_invoice_date,
        return_type=str,
    ),
]
# a date the api returns from the database, written the same way as the input
OutputDate = Annotated[
    date,
    PlainSerializer(
        func=format_invoice_date,
        return_type=str,
    ),
]
Text = Annotated[
    str,
    Field(
        min_length=1,
        pattern=r"\S",
    ),
]
Inn = Annotated[
    str,
    Field(
        pattern=r"^[0-9]{10}([0-9]{2})?$",
    ),
]


class ExtractionModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )


# the draft form keeps the strict formats of the extraction, so it goes back and forth as is
class FormModel(ExtractionModel):
    pass
