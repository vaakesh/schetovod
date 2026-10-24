from core.schema_types import (
    ExtractionModel,
    Inn,
    InvoiceDate,
    LineNo,
    Money,
    Quantity,
    Text,
    VatPercent,
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
