import unittest
from decimal import Decimal

from pricing import markup_for_price, normalize_name, retail_price, retail_price_total


class PricingTests(unittest.TestCase):
    def test_retail_price_rounds_to_ruble(self) -> None:
        for cost_price, markup_pct, expected in (
            ("425.00", "35", "574"),  # 573.75
            ("54.00", "30", "70"),  # 70.20
            ("170.00", "32.5", "225"),  # 225.25
            ("51.00", "50", "77"),  # 76.50, half rounds up
            ("100.00", "0", "100"),
        ):
            with self.subTest(
                cost_price=cost_price,
                markup_pct=markup_pct,
            ):
                self.assertEqual(
                    first=retail_price(
                        cost_price=Decimal(
                            value=cost_price,
                        ),
                        markup_pct=Decimal(
                            value=markup_pct,
                        ),
                    ),
                    second=Decimal(
                        value=expected,
                    ),
                )

    def test_markup_for_price_gives_back_the_same_price(self) -> None:
        for cost_price, price, expected in (
            ("425.00", "575", "35.29"),
            ("54.00", "70", "29.63"),
            ("100.00", "100", "0.00"),
            ("386.36", "485", "25.53"),
        ):
            with self.subTest(
                cost_price=cost_price,
                price=price,
            ):
                markup_pct = markup_for_price(
                    cost_price=Decimal(
                        value=cost_price,
                    ),
                    price=Decimal(
                        value=price,
                    ),
                )
                self.assertEqual(
                    first=markup_pct,
                    second=Decimal(
                        value=expected,
                    ),
                )
                self.assertEqual(
                    first=retail_price(
                        cost_price=Decimal(
                            value=cost_price,
                        ),
                        markup_pct=markup_pct,
                    ),
                    second=Decimal(
                        value=price,
                    ),
                )

    def test_retail_price_total_rounds_to_kopecks(self) -> None:
        self.assertEqual(
            first=retail_price_total(
                retail_price=Decimal(
                    value=861,
                ),
                quantity=Decimal(
                    value="0.800",
                ),
            ),
            second=Decimal(
                value="688.80",
            ),
        )

    def test_normalize_name_ignores_spacing_quotes_and_case(self) -> None:
        self.assertEqual(
            first=normalize_name(
                name='Хлеб"Ижорский"из рж.и пш.муки 0,65',
            ),
            second=normalize_name(
                name="хлеб «Ижорский»  из рж. и пш. муки 0,65",
            ),
        )

    def test_normalize_name_keeps_numbers_apart(self) -> None:
        self.assertNotEqual(
            first=normalize_name(
                name="Молоко 3,2% 1л",
            ),
            second=normalize_name(
                name="Молоко 2,5% 1л",
            ),
        )

    def test_normalize_name_treats_yo_as_ye(self) -> None:
        self.assertEqual(
            first=normalize_name(
                name="Плетёнка с маком",
            ),
            second=normalize_name(
                name="плетенка с маком",
            ),
        )


if __name__ == "__main__":
    unittest.main()
