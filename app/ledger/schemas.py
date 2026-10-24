from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    Field,
)

from core.enums import LedgerKind
from core.schema_types import FormModel, InvoiceDate, Money, OutputDate, Quantity, Text


# the ledger input has the strict formats of the form
class OutflowCreate(FormModel):
    occurred_on: InvoiceDate
    amount: Annotated[
        Money,
        Field(
            gt=0,
        ),
    ]
    comment: Text | None


class SaleCreate(FormModel):
    occurred_on: InvoiceDate
    # goes into the till
    cash: Money
    # goes straight to the bank account, only the stock goes down by it
    card: Money
    comment: Text | None


class CashOutCreate(FormModel):
    occurred_on: InvoiceDate
    amount: Annotated[
        Money,
        Field(
            gt=0,
        ),
    ]
    # what the money was taken for, there are no separate kinds of spending
    comment: Text


class StocktakeCreate(FormModel):
    occurred_on: InvoiceDate
    # stock at retail prices as counted, the balance becomes this amount
    counted: Money
    comment: Text | None


class CashCountCreate(FormModel):
    occurred_on: InvoiceDate
    # cash in the till as counted, the cash balance becomes this amount
    counted: Money
    comment: Text | None


class RevaluationLine(FormModel):
    product_id: Annotated[
        int,
        Field(
            gt=0,
        ),
    ]
    # counted on the shelf
    quantity: Quantity
    # whole rubles
    new_price: Annotated[
        int,
        Field(
            gt=0,
        ),
    ]


class RevaluationCreate(FormModel):
    occurred_on: InvoiceDate
    comment: Text | None
    lines: Annotated[
        list[RevaluationLine],
        Field(
            min_length=1,
        ),
    ]


class RevaluationLineOut(BaseModel):
    product_id: int
    product_name: str
    quantity: Decimal
    old_price: Decimal
    new_price: Decimal
    # signed, what the line adds to the stock at retail prices
    amount: Decimal


class LedgerEntryOut(BaseModel):
    id: int
    occurred_on: OutputDate
    kind: LedgerKind
    # signed, positive brings stock in
    amount: Decimal
    # signed, positive brings cash into the till
    cash: Decimal
    # the running balances in the ledger order, including this entry
    balance_after: Decimal
    cash_after: Decimal
    comment: str | None
    # the entry this one cancels
    reverses_id: int | None
    # the entry that cancels this one
    reversed_by_id: int | None
    invoice_id: int | None
    invoice_number: str | None
    supplier_name: str | None


class LedgerPage(BaseModel):
    balance: Decimal
    cash_balance: Decimal
    entries: list[LedgerEntryOut]
    has_more: bool


class LedgerBalance(BaseModel):
    # stock at retail prices at the end of the day, or now
    balance: Decimal
    # cash in the till at the end of the day, or now
    cash_balance: Decimal
    # the day of the latest stocktake, no stock entry may be dated before it
    closed_on: OutputDate | None
    # the day of the latest cash count, no cash entry may be dated before it
    cash_closed_on: OutputDate | None


class LedgerPosted(BaseModel):
    id: int
    amount: Decimal
    cash: Decimal
    balance: Decimal
    cash_balance: Decimal
