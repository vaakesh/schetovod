from typing import Any

import pytest

from tests.fakes import invoice_payload
from tests.helpers import InvoiceApi


class TestInvoiceExtractionValidation(InvoiceApi):
    def test_accepts_missing_values_and_empty_items(self) -> None:
        payload = {
            "supplier": {"name": None, "inn": None},
            "invoice_number": None,
            "invoice_date": None,
            "items": [],
            "totals": {"base_total": None, "cost_total": None},
        }
        draft = self.upload(
            payload=payload,
        )

        assert draft["extraction"] == payload
        assert self.blocking(
            draft=draft,
        ) == [
            (None, "номер накладной не указан"),
            (None, "дата накладной не указана"),
            (None, "продавец не выбран"),
            (None, "в накладной нет строк"),
        ]

    def test_accepts_null_in_every_item_field(self) -> None:
        payload = invoice_payload()
        payload["items"][0] = dict.fromkeys(
            payload["items"][0],
        )
        draft = self.upload(
            payload=payload,
        )

        assert draft["extraction"] == payload

    @pytest.mark.parametrize(
        argnames=("scope", "field"),
        argvalues=[
            ("root", "supplier"),
            ("root", "invoice_number"),
            ("root", "invoice_date"),
            ("root", "items"),
            ("root", "totals"),
            ("supplier", "name"),
            ("supplier", "inn"),
            ("item", "line_no"),
            ("item", "name"),
            ("item", "quantity"),
            ("item", "unit"),
            ("item", "base_price"),
            ("item", "base_price_total"),
            ("item", "cost_price"),
            ("item", "cost_price_total"),
            ("item", "vat_percent"),
            ("totals", "base_total"),
            ("totals", "cost_total"),
        ],
    )
    def test_returns_422_when_required_key_is_missing(
        self, scope: str, field: str
    ) -> None:
        payload = invoice_payload()
        target = self.scopes(
            payload=payload,
        )[scope]
        del target[field]
        prefix = {
            "root": ["body"],
            "supplier": ["body", "supplier"],
            "item": ["body", "items", 0],
            "totals": ["body", "totals"],
        }

        response = self.client.post(
            url="/invoice",
            json=payload,
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": [
                {
                    "type": "missing",
                    "loc": [*prefix[scope], field],
                    "msg": "Field required",
                    "input": target,
                },
            ],
        }
        assert self.store.invoices == {}

    @pytest.mark.parametrize(
        argnames=("scope", "location"),
        argvalues=[
            ("root", ["body", "unexpected"]),
            ("supplier", ["body", "supplier", "unexpected"]),
            ("item", ["body", "items", 0, "unexpected"]),
            ("totals", ["body", "totals", "unexpected"]),
        ],
    )
    def test_returns_422_when_extra_key_is_present(
        self,
        scope: str,
        location: list[str | int],
    ) -> None:
        payload = invoice_payload()
        self.scopes(
            payload=payload,
        )[scope]["unexpected"] = None

        response = self.client.post(
            url="/invoice",
            json=payload,
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": [
                {
                    "type": "extra_forbidden",
                    "loc": location,
                    "msg": "Extra inputs are not permitted",
                    "input": None,
                },
            ],
        }
        assert self.store.invoices == {}

    @pytest.mark.parametrize(
        argnames=("scope", "field", "value", "location"),
        argvalues=[
            ("root", "supplier", None, ["body", "supplier"]),
            ("root", "totals", None, ["body", "totals"]),
            ("root", "items", None, ["body", "items"]),
            ("root", "items", [None], ["body", "items", 0]),
            ("root", "items", {}, ["body", "items"]),
            ("root", "invoice_number", 42, ["body", "invoice_number"]),
            ("root", "invoice_number", "", ["body", "invoice_number"]),
            ("root", "invoice_date", "2026-08-12", ["body", "invoice_date"]),
            ("root", "invoice_date", "5-08-2026", ["body", "invoice_date"]),
            ("root", "invoice_date", "31-02-2026", ["body", "invoice_date"]),
            ("root", "invoice_date", "29-02-2025", ["body", "invoice_date"]),
            ("root", "invoice_date", 1786492800, ["body", "invoice_date"]),
            ("supplier", "inn", "770123456", ["body", "supplier", "inn"]),
            ("supplier", "inn", "77012345601", ["body", "supplier", "inn"]),
            ("supplier", "inn", "7701234560\n", ["body", "supplier", "inn"]),
            ("supplier", "inn", 7701234560, ["body", "supplier", "inn"]),
            ("supplier", "name", "   ", ["body", "supplier", "name"]),
            ("item", "line_no", "0", ["body", "items", 0, "line_no"]),
            ("item", "line_no", "-1", ["body", "items", 0, "line_no"]),
            ("item", "line_no", "1.5", ["body", "items", 0, "line_no"]),
            ("item", "line_no", "2147483648", ["body", "items", 0, "line_no"]),
            ("item", "line_no", 1, ["body", "items", 0, "line_no"]),
            ("item", "name", True, ["body", "items", 0, "name"]),
            ("item", "quantity", "0", ["body", "items", 0, "quantity"]),
            ("item", "quantity", "-1", ["body", "items", 0, "quantity"]),
            ("item", "quantity", "0.0001", ["body", "items", 0, "quantity"]),
            ("item", "quantity", "1000000000", ["body", "items", 0, "quantity"]),
            ("item", "quantity", 2.5, ["body", "items", 0, "quantity"]),
            ("item", "unit", "", ["body", "items", 0, "unit"]),
            ("item", "base_price", "-1", ["body", "items", 0, "base_price"]),
            ("item", "base_price", "50,00", ["body", "items", 0, "base_price"]),
            ("item", "base_price", "1 000.00", ["body", "items", 0, "base_price"]),
            ("item", "base_price", "1e2", ["body", "items", 0, "base_price"]),
            ("item", "base_price", "NaN", ["body", "items", 0, "base_price"]),
            ("item", "base_price", "Infinity", ["body", "items", 0, "base_price"]),
            ("item", "base_price", "0.001", ["body", "items", 0, "base_price"]),
            ("item", "base_price", "1000000000000", ["body", "items", 0, "base_price"]),
            ("item", "cost_price", True, ["body", "items", 0, "cost_price"]),
            ("item", "cost_price_total", 125, ["body", "items", 0, "cost_price_total"]),
            ("item", "vat_percent", "-1", ["body", "items", 0, "vat_percent"]),
            ("item", "vat_percent", "100.01", ["body", "items", 0, "vat_percent"]),
            ("item", "vat_percent", "0.001", ["body", "items", 0, "vat_percent"]),
            ("totals", "base_total", "-1", ["body", "totals", "base_total"]),
            ("totals", "cost_total", "NaN", ["body", "totals", "cost_total"]),
        ],
    )
    def test_rejects_invalid_values(
        self,
        scope: str,
        field: str,
        value: Any,
        location: list[str | int],
    ) -> None:
        payload = invoice_payload()
        self.scopes(
            payload=payload,
        )[scope][field] = value
        response = self.client.post(
            url="/invoice",
            json=payload,
        )

        assert response.status_code == 422
        assert [error["loc"] for error in response.json()["detail"]] == [location]
        assert self.store.invoices == {}

    def test_accepts_boundaries_and_preserves_decimal_places(self) -> None:
        payload = invoice_payload()
        payload["supplier"]["inn"] = "001234567890"
        payload["invoice_date"] = "29-02-2024"
        payload["items"][0].update(
            line_no="2147483647",
            quantity="999999999.999",
            base_price="999999999999.99",
            base_price_total="0",
            cost_price="0.00",
            cost_price_total="0.000",
            vat_percent="100.00",
        )

        draft = self.upload(
            payload=payload,
        )

        assert draft["extraction"] == payload

    def test_rejects_malformed_json(self) -> None:
        response = self.client.post(
            url="/invoice",
            content="{",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422

    def scopes(
        self,
        payload: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        return {
            "root": payload,
            "supplier": payload["supplier"],
            "item": payload["items"][0],
            "totals": payload["totals"],
        }
