from typing import Any

import pytest

from tests.fakes import FakeStore
from tests.helpers import InvoiceApi


class TestSupplierSearch(InvoiceApi):
    @pytest.fixture(
        autouse=True,
    )
    def suppliers(self, store: FakeStore) -> None:
        self.petrov = store.add_supplier(
            name="ИП Петров",
            inn="471909695290",
        )
        self.dvor = store.add_supplier(
            name="ООО «Молочный двор»",
            inn="7707083893",
        )
        self.market = store.add_supplier(
            name="Агроторг",
            inn=None,
        )

    def search(
        self,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        response = self.client.get(
            url="/supplier",
            params=params,
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_finds_by_a_part_of_the_name_in_any_case(self) -> None:
        assert self.search(
            params={"q": " молочный "},
        ) == [
            {
                "id": self.dvor.id,
                "name": "ООО «Молочный двор»",
                "short_name": None,
                "inn": "7707083893",
            },
        ]

    def test_finds_by_the_start_of_the_inn(self) -> None:
        response = self.client.get(
            url="/supplier",
            params={"q": "4719"},
        )

        assert response.status_code == 200
        assert response.json() == [
            {
                "id": self.petrov.id,
                "name": "ИП Петров",
                "short_name": None,
                "inn": "471909695290",
            }
        ]

    def test_without_a_query_lists_everyone_by_name(self) -> None:
        assert self.search(
            params={},
        ) == [
            {"id": self.market.id, "name": "Агроторг", "short_name": None, "inn": None},
            {
                "id": self.petrov.id,
                "name": "ИП Петров",
                "short_name": None,
                "inn": "471909695290",
            },
            {
                "id": self.dvor.id,
                "name": "ООО «Молочный двор»",
                "short_name": None,
                "inn": "7707083893",
            },
        ]

    def test_limits_number_of_suppliers(self) -> None:
        assert self.search(
            params={"limit": 2},
        ) == [
            {"id": self.market.id, "name": "Агроторг", "short_name": None, "inn": None},
            {
                "id": self.petrov.id,
                "name": "ИП Петров",
                "short_name": None,
                "inn": "471909695290",
            },
        ]
