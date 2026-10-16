from decimal import Decimal

import pytest

from pricing import markup_for_price, normalize_name, retail_price, retail_price_total


class TestRetailPrice:
    @pytest.mark.parametrize(
        argnames=("cost_price", "markup_pct", "expected"),
        argvalues=[
            ("425.00", "35", "574"),
            ("54.00", "30", "70"),
            ("170.00", "32.5", "225"),
            ("51.00", "50", "77"),
            ("100.00", "0", "100"),
        ],
    )
    def test_rounds_retail_price_to_ruble(
        self,
        cost_price: str,
        markup_pct: str,
        expected: str,
    ) -> None:
        cost = Decimal(
            value=cost_price,
        )
        markup = Decimal(
            value=markup_pct,
        )

        result = retail_price(
            cost_price=cost,
            markup_pct=markup,
        )

        assert result == Decimal(
            value=expected,
        )


class TestMarkupForPrice:
    @pytest.mark.parametrize(
        argnames=("cost_price", "price", "expected"),
        argvalues=[
            ("425.00", "575", "35.29"),
            ("54.00", "70", "29.63"),
            ("100.00", "100", "0.00"),
            ("386.36", "485", "25.53"),
        ],
    )
    def test_returns_markup_that_reproduces_retail_price(
        self,
        cost_price: str,
        price: str,
        expected: str,
    ) -> None:
        cost = Decimal(
            value=cost_price,
        )
        shelf_price = Decimal(
            value=price,
        )

        markup = markup_for_price(
            cost_price=cost,
            price=shelf_price,
        )

        assert markup == Decimal(
            value=expected,
        )
        assert (
            retail_price(
                cost_price=cost,
                markup_pct=markup,
            )
            == shelf_price
        )


class TestRetailPriceTotal:
    def test_rounds_line_total_to_kopecks(self) -> None:
        price = Decimal(
            value=861,
        )
        quantity = Decimal(
            value="0.800",
        )

        result = retail_price_total(
            retail_price=price,
            quantity=quantity,
        )

        assert result == Decimal(
            value="688.80",
        )


class TestNormalizeName:
    @pytest.mark.parametrize(
        argnames=("name", "expected"),
        argvalues=[
            ("соль", "соль"),
            ("  СОЛЬ  ", "соль"),
            (
                'Хлеб"Ижорский"из рж.и пш.муки 0,65',
                "хлеб ижорский из рж.и пш.муки 0,65",
            ),
            (
                "хлеб «Ижорский»  из рж. и пш. муки 0,65",
                "хлеб ижорский из рж.и пш.муки 0,65",
            ),
            ("Плетёнка с маком", "плетенка с маком"),
            ("плетенка с маком", "плетенка с маком"),
            ("Молоко 3,2% 1л", "молоко 3,2%1л"),
            ("Молоко 2,5% 1л", "молоко 2,5%1л"),
            ("", ""),
            ("   ", ""),
        ],
    )
    def test_returns_normalized_name(self, name: str, expected: str) -> None:
        result = normalize_name(
            name=name,
        )

        assert result == expected
