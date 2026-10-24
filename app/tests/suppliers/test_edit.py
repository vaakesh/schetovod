from typing import Any

from tests.fakes import INN
from tests.helpers import InvoiceApi


class TestSupplierEdit(InvoiceApi):
    def edit(
        self,
        supplier_id: int,
        short_name: str | None,
    ) -> Any:
        return self.client.put(
            url=f"/supplier/{supplier_id}",
            json={
                "name": "ООО «Поставщик»",
                "short_name": short_name,
                "inn": INN,
            },
        )

    def test_sets_and_clears_the_short_name(self) -> None:
        supplier, _, _ = self.known_supplier()

        response = self.edit(
            supplier_id=supplier.id,
            short_name="Поставщик",
        )

        assert response.status_code == 200, response.text
        assert response.json() == {
            "id": supplier.id,
            "name": "ООО «Поставщик»",
            "short_name": "Поставщик",
            "inn": INN,
        }
        assert supplier.short_name == "Поставщик"
        assert self.store.commits == 1

        response = self.edit(
            supplier_id=supplier.id,
            short_name=None,
        )

        assert response.status_code == 200, response.text
        assert supplier.short_name is None

    def test_blank_short_name_is_rejected(self) -> None:
        supplier, _, _ = self.known_supplier()

        response = self.edit(
            supplier_id=supplier.id,
            short_name="   ",
        )

        assert response.status_code == 422, response.text
        assert supplier.short_name is None

    def test_returns_404_for_an_unknown_supplier(self) -> None:
        response = self.edit(
            supplier_id=999,
            short_name="Поставщик",
        )

        assert response.status_code == 404, response.text
