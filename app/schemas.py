import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
)

from enums import InvoiceStatus, LedgerKind

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


class SupplierExtraction(ExtractionModel):
    name: Text | None
    inn: Inn | None


class InvoiceItemExtraction(ExtractionModel):
    line_no: LineNo | None
    name: Text | None
    quantity: Quantity | None
    unit: Text | None
    base_price: Money | None
    base_price_total: Money | None
    cost_price: Money | None
    cost_price_total: Money | None
    vat_percent: VatPercent | None


class TotalsExtraction(ExtractionModel):
    base_total: Money | None
    cost_total: Money | None


class InvoiceExtraction(ExtractionModel):
    supplier: SupplierExtraction
    invoice_number: Text | None
    invoice_date: InvoiceDate | None
    items: list[InvoiceItemExtraction]
    totals: TotalsExtraction


# the draft form keeps the strict formats of the extraction, so it goes back and forth as is
class FormModel(ExtractionModel):
    pass


class SupplierRef(FormModel):
    id: Annotated[
        int,
        Field(
            gt=0,
        ),
    ]


# created when the invoice is confirmed
class NewSupplier(FormModel):
    name: Text
    inn: Inn | None


class FormLine(FormModel):
    # saved drafts without this field keep their current numbering
    line_no: (
        Annotated[
            int,
            Field(
                gt=0,
                le=MAX_LINE_NO,
            ),
        ]
        | None
    ) = None
    name: Text | None
    quantity: Quantity | None
    unit: Text | None
    vat_percent: VatPercent | None
    # the line total actually paid, with VAT if any, every price is derived from it
    cost_price_total: Money | None
    # None to find the product by name, a product of the supplier this line is another spelling of
    product_id: (
        Annotated[
            int,
            Field(
                gt=0,
            ),
        ]
        | None
    )
    # None to keep the current markup of the product, whole rubles to set a new one
    retail_price: (
        Annotated[
            int,
            Field(
                gt=0,
            ),
        ]
        | None
    )
    # the old stock on the shelf that takes the new price, a draft saved before has no key
    revalue_quantity: Quantity | None = None


# as printed on the invoice, only to check the lines against
class FormTotals(FormModel):
    cost_total: Money | None
    base_total: Money | None


class DraftForm(FormModel):
    invoice_number: Text | None
    invoice_date: InvoiceDate | None
    supplier: SupplierRef | NewSupplier | None
    totals: FormTotals
    lines: list[FormLine]


class Issue(BaseModel):
    # stable line number, None means the issue is about the whole invoice
    line: int | None
    message: str
    # a blocking issue prevents confirming the invoice, the others are worth a look
    blocking: bool = True
    # set for the issues a client may show its own way, e.g. similar_product
    code: str | None = None


class SimilarProduct(BaseModel):
    id: int
    name: str
    # percent of matching characters of the normalized names
    similarity: int


class DraftLine(BaseModel):
    # stable line number from the form
    line: int
    # derived from the line total and rounded to kopecks
    cost_price: Decimal | None
    base_price: Decimal | None
    base_price_total: Decimal | None
    # None for a product that is created when the invoice is confirmed
    product_id: int | None
    product_name: str | None
    new_product: bool
    markup_pct: Decimal | None
    retail_price: Decimal | None
    retail_price_total: Decimal | None
    # the cost with VAT of the last delivery of the product, None when it is the same or unknown
    previous_cost_price: Decimal | None
    # the shelf price of the product when the line changes it, None when it stays
    previous_retail_price: Decimal | None
    # supplier products with a close name while the line has none, most similar first
    similar: list[SimilarProduct]


class DraftTotals(BaseModel):
    # sums of the line values, None while any line has no value
    base_total: Decimal | None
    cost_total: Decimal | None
    retail_total: Decimal | None


class SupplierSummary(BaseModel):
    id: int
    name: str
    # printed in the reports instead of the full name
    short_name: str | None
    inn: str | None


class SupplierEdit(FormModel):
    name: Text
    # None prints the full name in the reports
    short_name: Text | None
    inn: Inn | None


class ProductSummary(BaseModel):
    id: int
    name: str
    markup_pct: Decimal
    # from the last posted line, None while the product was never posted
    unit: str | None
    vat_percent: Decimal | None
    cost_price: Decimal | None
    retail_price: Decimal | None


class CatalogProduct(ProductSummary):
    supplier_id: int
    # other names the product was printed with, the name itself is not repeated
    spellings: list[str]
    # a shelf tag with the current retail price is hanging
    has_price_tag: bool


class Catalog(BaseModel):
    # every supplier, including the ones without products yet
    suppliers: list[SupplierSummary]
    products: list[CatalogProduct]


class SupplierCandidate(SupplierSummary):
    # lines of this invoice that match the supplier product names
    matched_lines: int


class ConfirmedInvoice(BaseModel):
    id: int
    ledger_entry_id: int
    # the inflow written to the ledger
    retail_total: Decimal
    # the revaluation of the old stock, None when nothing was revalued
    revaluation: Decimal | None
    # stock at retail prices after this invoice
    balance: Decimal


class InvoiceDraft(BaseModel):
    id: int
    # no blocking issues, the invoice can be confirmed
    ready: bool
    issues: list[Issue]
    # edit and send back to save the draft
    form: DraftForm
    lines: list[DraftLine]
    totals: DraftTotals
    # the existing supplier chosen in the form, None while it is new or not chosen
    supplier: SupplierSummary | None
    # existing suppliers that look alike while the form has a new one or none
    supplier_candidates: list[SupplierCandidate]
    # what the model read, for reference
    extraction: InvoiceExtraction


class InvoiceListItem(BaseModel):
    id: int
    status: InvoiceStatus
    invoice_number: str | None
    invoice_date: OutputDate | None
    # the chosen supplier, or the name the model read while there is none
    supplier_name: str | None
    # the inflow at retail prices, None until the invoice is confirmed
    retail_total: Decimal | None
    # owed to the supplier and not paid yet, None until the invoice is confirmed
    debt: Decimal | None
    lines: int
    created_at: datetime


class InvoiceList(BaseModel):
    items: list[InvoiceListItem]
    has_more: bool


class PostedLine(BaseModel):
    line_no: int
    # as printed on the invoice
    name: str
    # the catalog product the line was posted to
    product_name: str
    quantity: Decimal
    unit: str | None
    vat_percent: Decimal | None
    base_price: Decimal | None
    cost_price: Decimal
    cost_price_total: Decimal
    markup_pct: Decimal
    retail_price: Decimal
    retail_price_total: Decimal


class PaymentOut(BaseModel):
    id: int
    paid_on: OutputDate
    amount: Decimal
    comment: str | None


class PostedInvoice(BaseModel):
    id: int
    invoice_number: str
    invoice_date: OutputDate
    supplier: SupplierSummary
    lines: list[PostedLine]
    # owed to the supplier
    cost_total: Decimal
    retail_total: Decimal
    ledger_entry_id: int
    paid: Decimal
    debt: Decimal
    payments: list[PaymentOut]


class InvoiceConfirm(FormModel):
    # the day the goods came, the inflow goes into the ledger on it
    occurred_on: InvoiceDate


class PaymentCreate(FormModel):
    paid_on: InvoiceDate
    amount: Annotated[
        Money,
        Field(
            gt=0,
        ),
    ]
    comment: Text | None


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


class ProductRevaluation(FormModel):
    occurred_on: InvoiceDate
    # the old stock counted on the shelf
    quantity: Quantity
    comment: Text | None


class ProductEdit(FormModel):
    # the old name stays as another spelling of the product
    name: Text
    # whole rubles
    retail_price: Annotated[
        int,
        Field(
            gt=0,
        ),
    ]
    # None when there is no old stock, the price then changes without a ledger entry
    revaluation: ProductRevaluation | None


class PriceTagMark(FormModel):
    has_price_tag: bool
    # the price the user saw, a tag hung for an older price is not the current one
    retail_price: Annotated[
        int,
        Field(
            ge=0,
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


class LedgerReport(BaseModel):
    date_from: OutputDate
    date_to: OutputDate
    # stock at retail prices at the end of the day before the period
    opening: Decimal
    # signed stock sums of the period by kind, a reversal counts with the kind it cancels
    invoices: Decimal
    sales: Decimal
    write_offs: Decimal
    stocktakes: Decimal
    revaluations: Decimal
    # stock at retail prices at the end of the last day
    closing: Decimal
    # cash in the till at the end of the day before the period
    cash_opening: Decimal
    # the sales split into what went into the till and what went to the bank account
    sales_cash: Decimal
    sales_card: Decimal
    # signed cash sums of the period by kind
    cash_ins: Decimal
    cash_outs: Decimal
    cash_counts: Decimal
    # cash in the till at the end of the last day
    cash_closing: Decimal
    # in the ledger order
    entries: list[LedgerEntryOut]


class ReportInvoice(BaseModel):
    supplier_name: str
    invoice_number: str
    # owed to the supplier
    cost_total: Decimal
    # the inflow at retail prices
    retail_total: Decimal
    # paid by the end of the period
    paid: Decimal


class CashNote(BaseModel):
    kind: LedgerKind
    # signed, positive brings cash into the till
    cash: Decimal
    comment: str | None


class ReportDay(BaseModel):
    day: OutputDate
    invoices: list[ReportInvoice]
    sales_cash: Decimal
    sales_card: Decimal
    # signed, the cash ins, the cash outs and the cash counts of the day
    cash_moves: Decimal
    # what each of them was, the reversed ones and the reversals are left out
    cash_notes: list[CashNote]
    # the balances at the end of the day
    cash_after: Decimal
    balance_after: Decimal


class SupplierDebt(BaseModel):
    supplier_name: str
    invoice_number: str
    # a confirmed invoice always has it
    invoice_date: OutputDate | None
    cost_total: Decimal
    paid: Decimal
    debt: Decimal


class PeriodReport(BaseModel):
    """the period day by day, for the printed report"""

    date_from: OutputDate
    date_to: OutputDate
    # the balances at the end of the day before the period
    opening: Decimal
    cash_opening: Decimal
    # only the days with entries
    days: list[ReportDay]
    # paid to the suppliers on the days of the period, for any invoices
    paid_in_period: Decimal
    # unpaid at the end of the period
    debts: list[SupplierDebt]
