from typing import Any

import pytest
from fastapi.testclient import TestClient

from models import Product, Supplier
from tests.fakes import INN, FakeStore, invoice_payload


class InvoiceApi:
    @pytest.fixture(
        autouse=True,
    )
    def setup_api(
        self,
        store: FakeStore,
        client: TestClient,
    ) -> None:
        self.store = store
        self.client = client

    def upload(
        self,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self.client.post(
            url="/invoice",
            json=payload or invoice_payload(),
        )
        assert response.status_code == 200
        return response.json()

    def save(
        self,
        draft: dict[str, Any],
        form: dict[str, Any],
    ) -> dict[str, Any]:
        response = self.client.put(
            url=f"/invoice/{draft['id']}",
            json=form,
        )
        assert response.status_code == 200, response.text
        return response.json()

    def blocking(
        self,
        draft: dict[str, Any],
    ) -> list[tuple[int | None, str]]:
        return [
            (issue["line"], issue["message"])
            for issue in draft["issues"]
            if issue["blocking"]
        ]

    def known_supplier(self) -> tuple[Supplier, Product, Product]:
        supplier = self.store.add_supplier(
            name="ООО «Поставщик»",
            inn=INN,
        )
        sugar = self.store.add_product(
            supplier=supplier,
            name="Сахар-песок 1 кг",
            markup_pct="30",
            # the prices the uploaded invoice gives, so it does not revalue
            retail_price="65",
        )
        salt = self.store.add_product(
            supplier=supplier,
            name="Соль",
            markup_pct="20",
            retail_price="36",
        )
        return supplier, sugar, salt
