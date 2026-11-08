from datetime import date
from itertools import pairwise
from typing import Any

import pymupdf
import pytest

from reports.pdf import report_pdf
from reports.schemas import PeriodReport


def document(
    day: int = 12,
    cash_movements: tuple[tuple[str, str], ...] = (
        ("cash_in", "200.00"),
        ("cash_out", "-50.00"),
        ("cash_count", "0.00"),
        ("sale", "100.00"),
    ),
    stock_movements: tuple[tuple[str, str], ...] = (
        ("sale", "-300.00"),
        ("stock_in", "100.00"),
        ("stocktake", "0.00"),
        ("write_off", "-20.00"),
        ("revaluation", "10.00"),
        ("invoice", "397.00"),
    ),
    cash_after: str = "1250.00",
    balance_after: str = "5187.00",
    comments: dict[str, str] | None = None,
) -> pymupdf.Document:
    movement_comments = comments or {}
    report_day = date(
        year=2026,
        month=10,
        day=day,
    )
    report = PeriodReport.model_validate(
        obj={
            "date_from": report_day,
            "date_to": report_day,
            "opening": "5000.00",
            "cash_opening": "1000.00",
            "days": [
                {
                    "day": report_day,
                    "invoices": [],
                    "opening": "5000.00",
                    "cash_opening": "1000.00",
                    "stock_movements": [
                        {
                            "kind": kind,
                            "amount": amount,
                            "comment": movement_comments.get(
                                kind,
                            ),
                        }
                        for kind, amount in stock_movements
                    ],
                    "cash_movements": [
                        {
                            "kind": kind,
                            "amount": amount,
                            "comment": movement_comments.get(
                                kind,
                            ),
                        }
                        for kind, amount in cash_movements
                    ],
                    "sales_cash": "100.00",
                    "sales_card": "200.00",
                    "cash_moves": "150.00",
                    "cash_notes": [
                        {"kind": "cash_in", "cash": "200.00", "comment": "размен"},
                    ],
                    "cash_after": cash_after,
                    "balance_after": balance_after,
                },
            ],
            "paid_in_period": "0.00",
            "debts": [],
        },
    )
    return pymupdf.open(
        stream=report_pdf(
            report=report,
        ),
        filetype="pdf",
    )


def column_spans(
    page: pymupdf.Page,
    title: str,
) -> list[dict[str, Any]]:
    header, *_ = page.search_for(
        text=title,
    )
    return [
        span
        for block in page.get_text(
            option="dict",
        )["blocks"]
        if block["type"] == 0
        for line in block["lines"]
        for span in line["spans"]
        if span["bbox"][1] > header.y1
        and abs(
            span["bbox"][2] - header.x1,
        )
        < 0.1
    ]


class TestPeriodPdf:
    def test_movements_are_signed_and_only_the_balances_are_bold(self) -> None:
        with document() as pdf:
            page = pdf[0]
            cash = column_spans(
                page=page,
                title="Касса",
            )
            stock = column_spans(
                page=page,
                title="Товар",
            )
            text = page.get_text()

        assert [(span["text"], "Bold" in span["font"]) for span in cash] == [
            ("1 000,00", True),
            ("1 000,00", True),
            ("+200,00", False),
            ("внесение", False),
            ("−50,00", False),
            ("выдача", False),
            ("0,00", False),
            ("сверка кассы", False),
            ("+100,00", False),
            ("продажа", False),
            ("1 250,00", True),
            ("1 250,00", True),
        ]
        assert [(span["text"], "Bold" in span["font"]) for span in stock] == [
            ("5 000,00", True),
            ("5 000,00", True),
            ("−300,00", False),
            ("продажа", False),
            ("+100,00", False),
            ("приход товара", False),
            ("0,00", False),
            ("переучёт", False),
            ("−20,00", False),
            ("списание", False),
            ("+10,00", False),
            ("переоценка", False),
            ("+397,00", False),
            ("накладные", False),
            ("5 187,00", True),
            ("5 187,00", True),
        ]
        for spans in (cash, stock):
            for amount, label in zip(
                spans[2:-2:2],
                spans[3:-2:2],
                strict=True,
            ):
                assert label["bbox"][1] >= amount["bbox"][3]
                assert label["bbox"][2] == pytest.approx(
                    expected=amount["bbox"][2],
                    abs=0.1,
                )
                assert label["size"] < amount["size"]
                assert label["color"] == 0x555555
        assert cash[-2]["bbox"][1] == stock[-2]["bbox"][1]
        assert "Внес./выд." not in text
        assert "размен" not in text

    @pytest.mark.parametrize(
        argnames=("comments", "expected_cash", "expected_stock"),
        argvalues=[
            (
                {"cash_out": "пакеты", "write_off": "просрочка"},
                "выдача (пакеты)",
                "списание (просрочка)",
            ),
            (
                {"cash_out": "пакеты & чек", "write_off": "брак <1 & 2>"},
                "выдача (пакеты & чек)",
                "списание (брак <1 & 2>)",
            ),
        ],
    )
    def test_user_comments_are_printed_as_literal_text_in_parentheses(
        self,
        comments: dict[str, str],
        expected_cash: str,
        expected_stock: str,
    ) -> None:
        with document(
            cash_movements=(("cash_out", "-50.00"),),
            stock_movements=(("write_off", "-20.00"),),
            comments=comments,
        ) as pdf:
            cash = column_spans(
                page=pdf[0],
                title="Касса",
            )
            stock = column_spans(
                page=pdf[0],
                title="Товар",
            )

        assert [span["text"] for span in cash[2:-2]] == ["−50,00", expected_cash]
        assert [span["text"] for span in stock[2:-2]] == ["−20,00", expected_stock]

    def test_a_long_comment_wraps_under_its_amount_without_being_cut_off(self) -> None:
        with document(
            cash_movements=(("cash_out", "-50.00"),),
            stock_movements=(),
            comments={
                "cash_out": "оплата пакетов для покупателей и доставки товара",
            },
        ) as pdf:
            cash = column_spans(
                page=pdf[0],
                title="Касса",
            )

        assert cash[2]["text"] == "−50,00"
        assert (
            " ".join(
                (span["text"] for span in cash[3:-2]),
            )
            == "выдача (оплата пакетов для покупателей и доставки товара)"
        )
        assert cash[-3]["bbox"][3] <= cash[-2]["bbox"][1]

    @pytest.mark.parametrize(
        argnames=("day", "weekday"),
        argvalues=[
            (12, "пн"),
            (13, "вт"),
            (14, "ср"),
            (15, "чт"),
            (16, "пт"),
            (17, "сб"),
            (18, "вс"),
        ],
    )
    def test_weekday_is_on_the_line_below_the_date(
        self,
        day: int,
        weekday: str,
    ) -> None:
        with document(
            day=day,
        ) as pdf:
            page = pdf[0]
            [date_box] = page.search_for(
                text=f"{day:02d}.10.26",
            )
            [weekday_box] = [
                word
                for word in page.get_text(
                    option="words",
                )
                if word[4] == weekday
            ]

        assert weekday_box[0] == pytest.approx(
            expected=date_box.x0,
        )
        assert weekday_box[1] >= date_box.y1

    def test_movement_columns_are_wider_and_the_date_column_keeps_its_width(
        self,
    ) -> None:
        with document() as pdf:
            page = pdf[0]
            verticals = sorted(
                {
                    round(
                        item[1].x,
                        ndigits=3,
                    )
                    for drawing in page.get_drawings()
                    for item in drawing["items"]
                    if item[0] == "l" and item[1].x == item[2].x
                },
            )

        widths = [
            (right - left) * 25.4 / 72
            for left, right in pairwise(
                verticals,
            )
        ]

        assert widths == pytest.approx(
            expected=[15, 44, 22, 22, 22, 22, 22, 22, 40, 40],
            abs=0.001,
        )

    def test_a_day_without_visible_movements_still_prints_both_balances(self) -> None:
        with document(
            cash_movements=(),
            stock_movements=(),
            cash_after="1000.00",
            balance_after="5000.00",
        ) as pdf:
            cash = column_spans(
                page=pdf[0],
                title="Касса",
            )
            stock = column_spans(
                page=pdf[0],
                title="Товар",
            )

        assert [(span["text"], "Bold" in span["font"]) for span in cash] == [
            ("1 000,00", True),
            ("1 000,00", True),
            ("1 000,00", True),
            ("1 000,00", True),
        ]
        assert [(span["text"], "Bold" in span["font"]) for span in stock] == [
            ("5 000,00", True),
            ("5 000,00", True),
            ("5 000,00", True),
            ("5 000,00", True),
        ]

    def test_a_long_day_continues_on_next_pages_without_losing_movements(self) -> None:
        with document(
            cash_movements=(("cash_in", "1.00"),) * 180,
            stock_movements=(("write_off", "-2.00"),) * 110,
            cash_after="1180.00",
            balance_after="4780.00",
        ) as pdf:
            texts = [page.get_text() for page in pdf]
            text = "\n".join(
                texts,
            )

            assert pdf.page_count > 1

        assert (
            text.count(
                "+1,00",
            )
            == 180
        )
        assert (
            text.count(
                "−2,00",
            )
            == 110
        )
        assert (
            text.count(
                "1 180,00",
            )
            == 2
        )
        assert (
            text.count(
                "4 780,00",
            )
            == 2
        )
        assert all(
            (
                "Касса\nТовар" in page_text
                for page_text in texts
                if "+1,00" in page_text
            ),
        )
        assert all(
            (
                page_text.count(
                    "+1,00",
                )
                == page_text.splitlines().count(
                    "внесение",
                )
                and page_text.count(
                    "−2,00",
                )
                == page_text.splitlines().count(
                    "списание",
                )
                for page_text in texts
            ),
        )
