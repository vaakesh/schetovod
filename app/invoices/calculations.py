from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from invoices.extraction import InvoiceExtraction, InvoiceItemExtraction
from invoices.schemas import Issue
from products.pricing import (
    MAX_MARKUP_PCT,
    markup_for_price,
    retail_price,
    retail_price_total,
    revaluation_amount,
)

if TYPE_CHECKING:
    from invoices.planning import DraftPlan, ProductKey


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


PRICE_CHANGED = "price_changed"


def block(
    plan: DraftPlan,
    message: str,
    line: int | None = None,
) -> None:
    plan.issues.append(
        Issue(
            line=line,
            message=message,
        ),
    )


def issue_text(issue: Issue) -> str:
    if issue.line is None:
        return issue.message
    return f"строка {issue.line}: {issue.message}"


def price_lines(plan: DraftPlan) -> None:
    """one markup per product: from a price the user set, else the current one"""
    markups: dict[ProductKey, tuple[Decimal, int]] = {}
    # lines with a price that cannot be used, they already have their issue
    rejected: set[int] = set()
    for line in plan.lines:
        price = line.form.retail_price
        if price is None or line.key is None:
            continue
        if not line.cost_price:
            block(
                plan=plan,
                message="нет закупочной цены, наценку посчитать не из чего",
                line=line.position,
            )
            rejected.add(
                line.position,
            )
            continue
        markup_pct = markup_for_price(
            cost_price=line.cost_price,
            price=Decimal(
                value=price,
            ),
        )
        # an unchanged price keeps the markup, rounding would shift it a little
        if (
            line.product is not None
            and retail_price(
                cost_price=line.cost_price,
                markup_pct=line.product.markup_pct,
            )
            == price
        ):
            markup_pct = line.product.markup_pct
        if not 0 <= markup_pct <= MAX_MARKUP_PCT:
            block(
                plan=plan,
                message=(
                    f"при цене {price} и закупке {line.cost_price} наценка {markup_pct}%, "
                    f"а она должна быть от 0 до {MAX_MARKUP_PCT}%"
                ),
                line=line.position,
            )
            rejected.add(
                line.position,
            )
            continue
        other = markups.setdefault(
            line.key,
            (markup_pct, line.position),
        )
        if other[0] != markup_pct:
            block(
                plan=plan,
                message=f"у этого товара уже задана другая цена в строке {other[1]}",
                line=line.position,
            )

    for line in plan.lines:
        if line.key is None or line.position in rejected:
            continue
        found = markups.get(
            line.key,
        )
        markup_pct = found[0] if found else None
        if markup_pct is None and line.product is not None:
            markup_pct = line.product.markup_pct
        if markup_pct is None:
            # until the supplier is settled the product may still be found
            if not plan.catalog_known:
                continue
            block(
                plan=plan,
                message="новый товар, укажите розничную цену",
                line=line.position,
            )
            continue
        line.markup_pct = markup_pct
        if line.cost_price is not None:
            line.retail_price = retail_price(
                cost_price=line.cost_price,
                markup_pct=markup_pct,
            )
            if line.form.quantity is not None:
                line.retail_price_total = retail_price_total(
                    retail_price=line.retail_price,
                    quantity=line.form.quantity,
                )


def check_revaluation(plan: DraftPlan) -> None:
    """a changed shelf price asks for the old stock, one count per product"""
    for line in plan.lines:
        if (
            line.product is not None
            and line.retail_price is not None
            and line.retail_price != line.product.retail_price
        ):
            line.previous_retail_price = line.product.retail_price

    counted: dict[ProductKey, int] = {}
    for line in plan.lines:
        quantity = line.form.revalue_quantity
        if quantity is None:
            continue
        if line.previous_retail_price is None or line.retail_price is None:
            block(
                plan=plan,
                message="цена на полке не меняется, переоценивать нечего",
                line=line.position,
            )
            continue
        if line.key is not None:
            other = counted.setdefault(
                line.key,
                line.position,
            )
            if other != line.position:
                block(
                    plan=plan,
                    message=f"переоценка этого товара уже указана в строке {other}",
                    line=line.position,
                )
                continue
        if not revaluation_amount(
            quantity=quantity,
            old_price=line.previous_retail_price,
            new_price=line.retail_price,
        ):
            block(
                plan=plan,
                message="переоценка выходит меньше копейки, проверьте количество",
                line=line.position,
            )

    # the warning stays until the old stock of the product is counted in any of its lines
    warned: set[ProductKey] = set()
    for line in plan.lines:
        if (
            line.previous_retail_price is None
            or line.retail_price is None
            or line.key is None
            or line.key in counted
            or line.key in warned
        ):
            continue
        warned.add(
            line.key,
        )
        plan.issues.append(
            Issue(
                line=line.position,
                message=(
                    f"цена на полке меняется с {line.previous_retail_price:.0f} "
                    f"на {line.retail_price:.0f} ₽, укажите, сколько старого товара "
                    "осталось, чтобы переоценить"
                ),
                blocking=False,
                code=PRICE_CHANGED,
            ),
        )
