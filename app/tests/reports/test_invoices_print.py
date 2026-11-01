import re
from datetime import date
from decimal import Decimal
from typing import Any

from reports.pdf import invoices_pdf
from reports.schemas import PrintedInvoice, PrintedLine
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
