from datetime import datetime
from decimal import Decimal
from typing import Annotated

from sqlalchemy import BigInteger, DateTime, Numeric
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import mapped_column

from core.enums import InvoiceStatus, LedgerKind

# column templates for Mapped[...], the mapped_column on a field is merged on top of them
BigInt = Annotated[
    int,
    mapped_column(
        BigInteger,
    ),
]
# rubles with kopecks
Money = Annotated[
    Decimal,
    mapped_column(
        Numeric(
            precision=14,
            scale=2,
        ),
    ),
]
# markup and VAT rate, up to 999.99
Percent = Annotated[
    Decimal,
    mapped_column(
        Numeric(
            precision=5,
            scale=2,
        ),
    ),
]
# pieces or kilograms with grams
Quantity = Annotated[
    Decimal,
    mapped_column(
        Numeric(
            precision=12,
            scale=3,
        ),
    ),
]
# timestamp with time zone, a plain datetime maps to a timestamp without it
DateTimeTz = Annotated[
    datetime,
    mapped_column(
        DateTime(
            timezone=True,
        ),
    ),
]


# enums are stored by value as plain strings instead of a postgres enum with member names,
# create_constraint adds a check with the allowed values, validate_strings rejects a typo before the query
invoice_status_enum = SQLAlchemyEnum(
    InvoiceStatus,
    name="invoice_status",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    values_callable=lambda enum_class: [member.value for member in enum_class],
)
ledger_kind_enum = SQLAlchemyEnum(
    LedgerKind,
    name="ledger_kind",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    values_callable=lambda enum_class: [member.value for member in enum_class],
)
