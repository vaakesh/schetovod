from decimal import Decimal
from typing import Any

import pytest

from normalize import (
    LinePrices,
    check_read_prices,
    check_totals,
    line_prices,
    printed_cost_total_field,
    source_total_field,
    to_kopecks,
)
from schemas import InvoiceExtraction, InvoiceItemExtraction

# lines of a real invoice with VAT, unit prices without VAT are printed rounded
REAL_LINES = [
    {
        "quantity": "10.000",
        "base_price": "386.36",
        "base_price_total": "3863.64",
        "cost_price_total": "4250.00",
        "vat_percent": "10",
    },
    {
        "quantity": "10.000",
        "base_price": "65.46",
        "base_price_total": "654.55",
        "cost_price_total": "720.00",
        "vat_percent": "10",
    },
    {
        "quantity": "0.800",
        "base_price": "559.09",
        "base_price_total": "447.27",
        "cost_price_total": "492.00",
        "vat_percent": "10",
    },
    {
        "quantity": "1.200",
        "base_price": "581.82",
        "base_price_total": "698.18",
        "cost_price_total": "768.00",
        "vat_percent": "10",
    },
]


def make_item(fields: dict[str, Any]) -> InvoiceItemExtraction:
    defaults = {
        "line_no": None,
        "name": "Товар",
        "quantity": "1",
        "unit": "шт",
        "base_price": None,
        "base_price_total": None,
        "cost_price": None,
        "cost_price_total": None,
        "vat_percent": None,
    }
    return InvoiceItemExtraction.model_validate(
        obj=defaults | fields,
    )


def prices_of(item: InvoiceItemExtraction) -> LinePrices:
    """prices derived the way the draft does it, from the total in the source field"""
    return line_prices(
        cost_total=getattr(
            item,
            source_total_field(
                item=item,
            ),
        ),
        vat_percent=item.vat_percent,
        quantity=item.quantity,
    )


def rounded(prices: LinePrices) -> tuple[Decimal | None, ...]:
    return tuple(
        to_kopecks(
            value=value,
        )
        for value in (
            prices.cost_price_total,
            prices.cost_price,
            prices.base_price_total,
            prices.base_price,
        )
    )


def read_messages(fields: dict[str, Any]) -> list[str]:
    item = make_item(
        fields=fields,
    )
    issues = check_read_prices(
        line=1,
        read=item,
        prices=prices_of(
            item=item,
        ),
        quantity=item.quantity,
    )
    # every read mismatch is only worth a look
    assert all(
        (not issue.blocking for issue in issues),
    )
    return [issue.message for issue in issues]


class TestLinePrices:
    def test_derives_every_price_from_the_total_with_vat(self) -> None:
        assert rounded(
            prices=prices_of(
                item=make_item(
                    fields=REAL_LINES[0],
                ),
            ),
        ) == (
            Decimal(
                value="4250.00",
            ),
            Decimal(
                value="425.00",
            ),
            Decimal(
                value="3863.64",
            ),
            Decimal(
                value="386.36",
            ),
        )

    @pytest.mark.parametrize(
        argnames="field",
        argvalues=("cost_price_total", "base_price_total"),
    )
    def test_without_vat_takes_the_total_from_either_field(
        self,
        field: str,
    ) -> None:
        assert rounded(
            prices=prices_of(
                item=make_item(
                    fields={"quantity": "6", field: "324.00"},
                ),
            ),
        ) == (
            Decimal(
                value="324.00",
            ),
            Decimal(
                value="54.00",
            ),
            Decimal(
                value="324.00",
            ),
            Decimal(
                value="54.00",
            ),
        )

    def test_with_vat_the_total_without_it_is_never_the_source(self) -> None:
        item = make_item(
            fields={"base_price_total": "100.00", "vat_percent": "20"},
        )
        assert rounded(
            prices=prices_of(
                item=item,
            ),
        ) == (None, None, None, None)

    def test_without_quantity_derives_only_totals(self) -> None:
        assert rounded(
            prices=line_prices(
                cost_total=Decimal(
                    value="120.00",
                ),
                vat_percent=Decimal(
                    value=20,
                ),
                quantity=None,
            ),
        ) == (
            Decimal(
                value="120.00",
            ),
            None,
            Decimal(
                value="100.00",
            ),
            None,
        )


class TestPrintedCostTotalField:
    @pytest.mark.parametrize(
        argnames=("items", "totals", "field"),
        argvalues=(
            ([{}], {"cost_total": None, "base_total": "1.00"}, "base_total"),
            ([{}], {"cost_total": "1.00", "base_total": None}, "cost_total"),
            (
                [{"vat_percent": "20"}],
                {"cost_total": None, "base_total": "1.00"},
                "cost_total",
            ),
        ),
    )
    def test_printed_total_without_vat_may_be_read_as_without_vat(
        self,
        items: list[dict[str, Any]],
        totals: dict[str, str | None],
        field: str,
    ) -> None:
        invoice = InvoiceExtraction.model_validate(
            obj={
                "supplier": {"name": None, "inn": None},
                "invoice_number": None,
                "invoice_date": None,
                "items": [
                    make_item(
                        fields=item,
                    ).model_dump(
                        mode="json",
                    )
                    for item in items
                ],
                "totals": totals,
            },
        )
        assert (
            printed_cost_total_field(
                invoice=invoice,
            )
            == field
        )


class TestCheckReadPrices:
    @pytest.mark.parametrize(
        argnames="fields",
        argvalues=REAL_LINES,
    )
    def test_real_invoice_fits_rounding(
        self,
        fields: dict[str, Any],
    ) -> None:
        assert (
            read_messages(
                fields=fields,
            )
            == []
        )

    def test_price_from_a_rounded_total_of_a_small_quantity_fits(self) -> None:
        # 33.33 × 0.2 = 6.666 is printed as 6.67, which gives back 33.35
        assert (
            read_messages(
                fields={
                    "quantity": "0.2",
                    "cost_price": "33.33",
                    "cost_price_total": "6.67",
                },
            )
            == []
        )

    @pytest.mark.parametrize(
        argnames=("fields", "message"),
        argvalues=(
            (
                {
                    "quantity": "2.5",
                    "cost_price": "52.00",
                    "cost_price_total": "125.00",
                },
                "цена за единицу: в накладной 52.00, по сумме строки 50.00",
            ),
            (
                {
                    "cost_price_total": "120.00",
                    "base_price_total": "99.00",
                    "vat_percent": "20",
                },
                "сумма без НДС: в накладной 99.00, по сумме строки 100.00",
            ),
            (
                {
                    "quantity": "2",
                    "cost_price_total": "120.00",
                    "base_price": "55.00",
                    "vat_percent": "20",
                },
                "цена без НДС: в накладной 55.00, по сумме строки 50.00",
            ),
            (
                {"cost_price_total": "100.00", "base_price_total": "90.00"},
                "сумма без НДС: в накладной 90.00, по сумме строки 100.00",
            ),
        ),
    )
    def test_misread_values_are_warnings(
        self,
        fields: dict[str, Any],
        message: str,
    ) -> None:
        assert read_messages(
            fields=fields,
        ) == [message]


class TestCheckTotals:
    def check(
        self,
        cost_total: str | None,
        base_total: str | None,
        lines: list[dict[str, Any]],
    ) -> list[str]:
        items = [
            make_item(
                fields=fields,
            )
            for fields in lines
        ]
        issues = check_totals(
            cost_total=None
            if cost_total is None
            else Decimal(
                value=cost_total,
            ),
            base_total=None
            if base_total is None
            else Decimal(
                value=base_total,
            ),
            prices=[
                prices_of(
                    item=item,
                )
                for item in items
            ],
            with_vat=any(
                (item.vat_percent for item in items),
            ),
        )
        assert all(
            (not issue.blocking for issue in issues),
        )
        return [issue.message for issue in issues]

    def test_real_invoice_fits_rounding(self) -> None:
        assert (
            self.check(
                cost_total="6230.00",
                base_total="5663.64",
                lines=REAL_LINES,
            )
            == []
        )

    def test_mismatches_are_warnings(self) -> None:
        assert self.check(
            cost_total="35.00",
            base_total="31.00",
            lines=[
                {"cost_price_total": "12.00", "vat_percent": "20"},
                {"cost_price_total": "24.00", "vat_percent": "20"},
            ],
        ) == [
            "итог к оплате: в накладной 35.00, по строкам 36.00",
            "итог без НДС: в накладной 31.00, по строкам 30.00",
        ]

    def test_without_vat_the_total_is_checked_once(self) -> None:
        assert self.check(
            cost_total="35.00",
            base_total="35.00",
            lines=[{"cost_price_total": "30.00"}],
        ) == ["итог к оплате: в накладной 35.00, по строкам 30.00"]

    def test_missing_total_is_a_warning(self) -> None:
        assert self.check(
            cost_total=None,
            base_total=None,
            lines=[{"cost_price_total": "10.00"}],
        ) == ["итог в накладной не указан, посчитанный итог сверить не с чем"]
