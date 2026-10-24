from typing import Any

from tests.fakes import invoice_payload
from tests.helpers import InvoiceApi


class TestPayments(InvoiceApi):
    def confirmed(self) -> int:
        self.known_supplier()
        draft = self.upload()
        response = self.confirm(
            draft=draft,
        )
        assert response.status_code == 200, response.text
        return draft["id"]

    def pay(
        self,
        invoice_id: int,
        amount: str,
        paid_on: str = "16-10-2026",
        expected: int = 200,
    ) -> dict[str, Any]:
        response = self.client.post(
            url=f"/invoice/{invoice_id}/payments",
            json={
                "paid_on": paid_on,
                "amount": amount,
                "comment": None,
            },
        )
        assert response.status_code == expected, response.text
        return response.json()

    def test_paid_in_parts(self) -> None:
        invoice_id = self.confirmed()

        unpaid = self.client.get(
            url=f"/invoice/{invoice_id}/confirmed",
        ).json()
        part = self.pay(
            invoice_id=invoice_id,
            amount="100.00",
            paid_on="15-10-2026",
        )
        rest = self.pay(
            invoice_id=invoice_id,
            amount="55.00",
        )

        assert (unpaid["cost_total"], unpaid["paid"], unpaid["debt"]) == (
            "155.00",
            "0",
            "155.00",
        )
        assert (part["paid"], part["debt"]) == ("100.00", "55.00")
        assert (rest["paid"], rest["debt"]) == ("155.00", "0.00")
        assert [
            (payment["paid_on"], payment["amount"]) for payment in rest["payments"]
        ] == [
            ("15-10-2026", "100.00"),
            ("16-10-2026", "55.00"),
        ]
        # paying does not touch the till
        assert all(entry.cash == 0 for entry in self.store.entries)

    def test_overpayment_is_rejected(self) -> None:
        invoice_id = self.confirmed()
        self.pay(
            invoice_id=invoice_id,
            amount="100.00",
        )

        response = self.pay(
            invoice_id=invoice_id,
            amount="55.01",
            expected=422,
        )

        assert (
            response["detail"] == "Оплата больше долга по накладной, осталось 55.00 ₽"
        )
        assert len(self.store.payments) == 1

    def test_future_date_is_rejected(self) -> None:
        invoice_id = self.confirmed()

        response = self.pay(
            invoice_id=invoice_id,
            amount="10.00",
            paid_on="17-10-2026",
            expected=422,
        )

        assert response["detail"] == "Дата оплаты не может быть в будущем"

    def test_draft_cannot_be_paid(self) -> None:
        draft = self.upload()

        self.pay(
            invoice_id=draft["id"],
            amount="10.00",
            expected=404,
        )

        assert self.store.payments == []

    def test_payment_is_deleted(self) -> None:
        invoice_id = self.confirmed()
        paid = self.pay(
            invoice_id=invoice_id,
            amount="100.00",
        )

        response = self.client.delete(
            url=f"/invoice/{invoice_id}/payments/{paid['payments'][0]['id']}",
        )
        missing = self.client.delete(
            url=f"/invoice/{invoice_id}/payments/{paid['payments'][0]['id']}",
        )

        assert response.status_code == 200, response.text
        assert (response.json()["debt"], response.json()["payments"]) == ("155.00", [])
        assert missing.status_code == 404

    def test_unpaid_filter_and_debt_sort(self) -> None:
        paid = self.confirmed()
        ids = [paid]
        for number in ("43", "44"):
            payload = invoice_payload()
            payload["invoice_number"] = number
            draft = self.upload(
                payload=payload,
            )
            response = self.confirm(
                draft=draft,
            )
            assert response.status_code == 200, response.text
            ids.append(
                draft["id"],
            )
        _, owes_more, owes_less = ids
        payload = invoice_payload()
        payload["invoice_number"] = "45"
        draft = self.upload(
            payload=payload,
        )
        for invoice_id, amount in (
            (paid, "155.00"),
            (owes_more, "100.00"),
            (owes_less, "150.00"),
        ):
            self.pay(
                invoice_id=invoice_id,
                amount=amount,
            )

        def listed(params: dict[str, str]) -> list[tuple[int, str | None]]:
            items = self.client.get(
                url="/invoice",
                params=params,
            ).json()["items"]
            return [(item["id"], item["debt"]) for item in items]

        assert listed(
            params={"unpaid": "true"},
        ) == [
            (owes_less, "5.00"),
            (owes_more, "55.00"),
        ]
        assert listed(
            params={"unpaid": "true", "sort": "debt"},
        ) == [
            (owes_more, "55.00"),
            (owes_less, "5.00"),
        ]
        # a paid invoice owes nothing, a draft owes nothing yet and goes last
        assert listed(
            params={"sort": "debt"},
        ) == [
            (owes_more, "55.00"),
            (owes_less, "5.00"),
            (paid, "0.00"),
            (draft["id"], None),
        ]

    def test_list_shows_the_debt(self) -> None:
        invoice_id = self.confirmed()
        self.upload()
        self.pay(
            invoice_id=invoice_id,
            amount="100.00",
        )

        items = self.client.get(
            url="/invoice",
        ).json()["items"]

        assert [(item["status"], item["debt"]) for item in items] == [
            ("draft", None),
            ("confirmed", "55.00"),
        ]
