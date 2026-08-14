from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from schemas import InvoiceExtraction, InvoiceItemExtraction, Issue

KOPECK = Decimal(
    value="0.01",
)
# a printed unit price is rounded to kopecks
PRICE_ROUNDING = Decimal(
    value="0.005",
)
# a printed line total may come from a rounded unit price or from a rounded VAT split,
# its error is spread over the quantity when a unit price is derived from it
TOTAL_ROUNDING = Decimal(
    value="0.01",
)


@dataclass(frozen=True)
class LinePrices:
    """exact prices derived from the line total, None when there is nothing to derive from"""

    cost_price_total: Decimal | None
    cost_price: Decimal | None
    base_price_total: Decimal | None
    base_price: Decimal | None


def to_kopecks(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(
        KOPECK,
        rounding=ROUND_HALF_UP,
    )


def sum_known(values: Iterable[Decimal | None]) -> Decimal | None:
    """sum of values, None if any of them is unknown"""
    total = Decimal(
        value=0,
    )
    for value in values:
        if value is None:
            return None
        total += value
    return total


def source_total_field(item: InvoiceItemExtraction) -> str:
    """the field with the line total actually paid, every other price is derived from it"""
    if item.vat_percent or item.cost_price_total is not None:
        return "cost_price_total"
    # without VAT both totals are the same amount, the model may put it in either
    return "base_price_total"


def printed_cost_total_field(invoice: InvoiceExtraction) -> str:
    """the field with the invoice total to pay"""
    if invoice.totals.cost_total is not None or any(
        item.vat_percent for item in invoice.items
    ):
        return "cost_total"
    # without VAT the only printed total may be read as the one without VAT
    return "base_total"


def line_prices(
    cost_total: Decimal | None,
    vat_percent: Decimal | None,
    quantity: Decimal | None,
) -> LinePrices:
    if cost_total is None:
        return LinePrices(
            cost_price_total=None,
            cost_price=None,
            base_price_total=None,
            base_price=None,
        )
    base_total = cost_total
    if vat_percent:
        base_total = cost_total / (1 + vat_percent / 100)
    return LinePrices(
        cost_price_total=cost_total,
        cost_price=cost_total / quantity if quantity else None,
        base_price_total=base_total,
        base_price=base_total / quantity if quantity else None,
    )


def check_read_prices(
    line: int,
    read: InvoiceItemExtraction,
    prices: LinePrices,
    quantity: Decimal | None,
) -> list[Issue]:
    """warns where what the model read disagrees with the prices derived from the line total"""
    checks = [
        (
            "сумма без НДС",
            read.base_price_total,
            prices.base_price_total,
            TOTAL_ROUNDING,
        ),
    ]
    if quantity:
        checks += [
            (
                "цена за единицу",
                read.cost_price,
                prices.cost_price,
                PRICE_ROUNDING + PRICE_ROUNDING / quantity,
            ),
            (
                "цена без НДС",
                read.base_price,
                prices.base_price,
                PRICE_ROUNDING + TOTAL_ROUNDING / quantity,
            ),
        ]
    issues: list[Issue] = []
    for label, read_value, derived, tolerance in checks:
        if read_value is None or derived is None:
            continue
        if abs(read_value - derived) > tolerance:
            shown = to_kopecks(
                value=derived,
            )
            issues.append(
                Issue(
                    line=line,
                    message=f"{label}: в накладной {read_value}, по сумме строки {shown}",
                    blocking=False,
                ),
            )
    return issues


def check_totals(
    cost_total: Decimal | None,
    base_total: Decimal | None,
    prices: list[LinePrices],
    with_vat: bool,
) -> list[Issue]:
    """warns where the printed totals disagree with the sums of the lines"""
    if cost_total is None:
        return [
            Issue(
                line=None,
                message="итог в накладной не указан, посчитанный итог сверить не с чем",
                blocking=False,
            ),
        ]
    issues: list[Issue] = []
    lines_cost = sum_known(
        values=(line.cost_price_total for line in prices),
    )
    if lines_cost is not None and abs(lines_cost - cost_total) > TOTAL_ROUNDING:
        issues.append(
            Issue(
                line=None,
                message=f"итог к оплате: в накладной {cost_total}, по строкам {lines_cost}",
                blocking=False,
            ),
        )
    # without VAT the total without it is the same amount and is already checked
    if base_total is not None and with_vat:
        lines_base = sum_known(
            values=(line.base_price_total for line in prices),
        )
        # every line adds its own rounding of the VAT split
        tolerance = TOTAL_ROUNDING * max(
            len(prices),
            1,
        )
        if lines_base is not None and abs(lines_base - base_total) > tolerance:
            shown = to_kopecks(
                value=lines_base,
            )
            issues.append(
                Issue(
                    line=None,
                    message=f"итог без НДС: в накладной {base_total}, по строкам {shown}",
                    blocking=False,
                ),
            )
    return issues
