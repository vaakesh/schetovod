import re
from datetime import date
from decimal import Decimal
from typing import Any

import pymupdf
import pytest

from reports.pdf import invoices_pdf
from reports.schemas import PrintedInvoice, PrintedLine
from tests.fakes import invoice_payload
from tests.helpers import InvoiceApi


def printed(
    day: int,
    lines: int = 1,
) -> PrintedInvoice:
    return PrintedInvoice(
        supplier_name="Поставщик",
        invoice_number="1",
        invoice_date=date(
            year=2026,
            month=10,
            day=day,
        ),
        lines=[
            PrintedLine(
                line_no=line_no,
                name="Товар",
                quantity=Decimal(
                    value=1,
                ),
                unit="шт",
                retail_price=Decimal(
                    value=100,
                ),
                retail_price_total=Decimal(
                    value=100,
                ),
            )
            for line_no in range(
                1,
                lines + 1,
            )
        ],
        retail_total=Decimal(
            value=100 * lines,
        ),
    )


def pages(
    invoices: list[PrintedInvoice],
) -> int:
    return len(
        re.findall(
            pattern=rb"/Type /Page\b",
            string=invoices_pdf(
                invoices=invoices,
            ),
        ),
    )


class TestPagesOfTheDates:
    @pytest.mark.parametrize(
        argnames=("day", "weekday"),
        argvalues=[
            (12, "ПОНЕДЕЛЬНИК"),
            (13, "ВТОРНИК"),
            (14, "СРЕДА"),
            (15, "ЧЕТВЕРГ"),
            (16, "ПЯТНИЦА"),
            (17, "СУББОТА"),
            (18, "ВОСКРЕСЕНЬЕ"),
        ],
    )
    def test_page_starts_with_a_large_bold_weekday(
        self,
        day: int,
        weekday: str,
    ) -> None:
        with pymupdf.open(
            stream=invoices_pdf(
                invoices=[
                    printed(
                        day=day,
                    ),
                    printed(
                        day=day,
                    ),
                ],
            ),
            filetype="pdf",
        ) as pdf:
            page = pdf[0]
            spans = [
                span
                for block in page.get_text(
                    option="dict",
                )["blocks"]
                if block["type"] == 0
                for line in block["lines"]
                for span in line["spans"]
                if span["text"] == weekday
            ]
            [heading] = spans
            [first_line, *_] = page.get_text(
                sort=True,
            ).splitlines()

        assert first_line == weekday
        assert heading["size"] == 18
        assert "Bold" in heading["font"]

    def test_weekday_repeats_on_continuations_and_changes_with_the_date(self) -> None:
        with pymupdf.open(
            stream=invoices_pdf(
                invoices=[
                    printed(
                        day=29,
                        lines=100,
                    ),
                    printed(
                        day=30,
                    ),
                ],
            ),
            filetype="pdf",
        ) as pdf:
            headings = [
                page.get_text(
                    sort=True,
                ).splitlines()[0]
                for page in pdf
            ]

        assert (
            len(
                headings,
            )
            > 2
        )
        assert set(
            headings[:-1],
        ) == {"ЧЕТВЕРГ"}
        assert headings[-1] == "ПЯТНИЦА"

    def test_invoices_of_one_date_share_a_page(self) -> None:
        assert (
            pages(
                invoices=[
                    printed(
                        day=29,
                    ),
                    printed(
                        day=29,
                    ),
                ],
            )
            == 1
        )

    def test_every_date_starts_on_a_new_page(self) -> None:
        assert (
            pages(
                invoices=[
                    printed(
                        day=29,
                    ),
                    printed(
                        day=29,
                    ),
                    printed(
                        day=30,
                    ),
                    printed(
                        day=31,
                    ),
                ],
            )
            == 3
        )

    def test_a_long_date_leaves_the_rest_of_its_last_page_empty(self) -> None:
        long_day = printed(
            day=29,
            lines=100,
        )
        alone = pages(
            invoices=[
                long_day,
            ],
        )

        assert alone > 1
        assert (
            pages(
                invoices=[
                    long_day,
                    printed(
                        day=30,
                    ),
                ],
            )
            == alone + 1
        )


class TestInvoicesPrint(InvoiceApi):
    def confirmed(self) -> dict[str, Any]:
        self.known_supplier()
        draft = self.upload()
        response = self.confirm(
            draft=draft,
        )
        assert response.status_code == 200, response.text
        return draft

    def test_pdf_opens_in_the_browser(self) -> None:
        draft = self.confirmed()

        response = self.client.get(
            url="/invoices/print.pdf",
            params={
                "ids": [
                    draft["id"],
                    draft["id"],
                ],
            },
        )

        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "application/pdf"
        assert (
            response.headers["content-disposition"]
            == 'inline; filename="nakladnaya_12-08-2026.pdf"'
        )
        assert response.content.startswith(
            b"%PDF",
        )

    def test_lines_follow_numeric_position_order_instead_of_names(self) -> None:
        self.known_supplier()
        payload = invoice_payload()
        payload["items"][0]["line_no"] = "10"
        payload["items"][1]["line_no"] = "2"
        draft = self.upload(
            payload=payload,
        )
        confirmed = self.confirm(
            draft=draft,
        )
        assert confirmed.status_code == 200, confirmed.text

        response = self.client.get(
            url="/invoices/print.pdf",
            params={"ids": [draft["id"]]},
        )

        assert response.status_code == 200, response.text
        with pymupdf.open(
            stream=response.content,
            filetype="pdf",
        ) as pdf:
            text = pdf[0].get_text()
        assert text.index(
            "Соль",
        ) < text.index(
            "Сахар-песок 1 кг",
        )

    def test_draft_is_not_printed(self) -> None:
        draft = self.upload()

        response = self.client.get(
            url="/invoices/print.pdf",
            params={
                "ids": [
                    draft["id"],
                ],
            },
        )

        assert response.status_code == 404

    def test_nothing_chosen_is_rejected(self) -> None:
        response = self.client.get(
            url="/invoices/print.pdf",
        )

        assert response.status_code == 422
