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

from enums import InvoiceStatus

DECIMAL_PATTERN = r"[0-9]+(?:\.[0-9]+)?"
LINE_NO_PATTERN = r"[0-9]+"
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
        le=2_147_483_647,
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
    # 1-based position in the form lines, None means the issue is about the whole invoice
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
    # 1-based position in the form lines
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
    inn: str | None


class ProductSummary(BaseModel):
    id: int
    name: str
    markup_pct: Decimal
    # from the last posted line, None while the product was never posted
    unit: str | None
    vat_percent: Decimal | None
    cost_price: Decimal | None
    retail_price: Decimal | None


class SupplierCandidate(SupplierSummary):
    # lines of this invoice that match the supplier product names
    matched_lines: int


class ConfirmedInvoice(BaseModel):
    id: int
    ledger_entry_id: int
    # the inflow written to the ledger
    retail_total: Decimal
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


class PostedInvoice(BaseModel):
    id: int
    invoice_number: str
    invoice_date: OutputDate
    supplier: SupplierSummary
    lines: list[PostedLine]
    cost_total: Decimal
    retail_total: Decimal
    ledger_entry_id: int


# the ledger input has the strict formats of the form
