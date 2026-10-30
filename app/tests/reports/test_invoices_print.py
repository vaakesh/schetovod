from typing import Any

from tests.helpers import InvoiceApi


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
