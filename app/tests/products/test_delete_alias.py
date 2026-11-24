from httpx2 import Response

from products.models import ProductAlias
from tests.fakes import invoice_payload
from tests.helpers import InvoiceApi


class TestDeleteProductAlias(InvoiceApi):
    def delete(
        self,
        product_id: int,
        alias_id: int,
    ) -> Response:
        return self.client.delete(
            url=f"/product/{product_id}/aliases/{alias_id}",
        )

    def test_removes_wrong_match_and_allows_relinking_with_history_intact(self) -> None:
        supplier, _, _ = self.known_supplier()
        wrong = self.store.add_product(
            supplier=supplier,
            name="Чечил",
            markup_pct="30",
            retail_price="65",
        )
        correct = self.store.add_product(
            supplier=supplier,
            name="Фисьель",
            markup_pct="30",
            retail_price="65",
        )
        payload = invoice_payload()
        payload["items"][0]["name"] = "Фисьель 150 г"
        original = self.upload(
            payload=payload,
        )
        form = original["form"]
        form["lines"][0]["product_id"] = wrong.id
        original = self.save(
            draft=original,
            form=form,
        )
        posted = self.confirm(
            draft=original,
        )
        assert posted.status_code == 200, posted.text
        alias = self.store.aliases[-1]
        assert (alias.product_id, alias.alias_raw) == (wrong.id, "Фисьель 150 г")
        reversed_invoice = self.client.post(
            url=f"/invoice/{original['id']}/reverse",
            json={"copy_to_draft": False},
        )
        assert reversed_invoice.status_code == 200, reversed_invoice.text
        payload["invoice_number"] = "00043/А"
        following = self.upload(
            payload=payload,
        )
        assert following["lines"][0]["product_id"] == wrong.id

        removed = self.delete(
            product_id=wrong.id,
            alias_id=alias.id,
        )

        assert removed.status_code == 204
        assert removed.content == b""
        search = self.client.get(
            url=f"/supplier/{supplier.id}/products",
            params={"q": "Фисьель"},
        )
        assert search.status_code == 200, search.text
        assert [product["id"] for product in search.json()] == [correct.id]
        updated = self.client.get(
            url=f"/invoice/{following['id']}",
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["lines"][0]["product_id"] is None

        form = updated.json()["form"]
        form["lines"][0]["product_id"] = correct.id
        fixed = self.save(
            draft=following,
            form=form,
        )
        posted_again = self.confirm(
            draft=fixed,
        )
        assert posted_again.status_code == 200, posted_again.text
        assert (
            self.store.aliases[-1].product_id,
            self.store.aliases[-1].alias_raw,
        ) == (
            correct.id,
            "Фисьель 150 г",
        )
        assert (self.store.items[0].product_id, self.store.items[0].name) == (
            wrong.id,
            "Фисьель 150 г",
        )
        history = self.client.get(
            url=f"/invoice/{original['id']}/confirmed",
        )
        assert history.status_code == 200, history.text
        assert history.json()["status"] == "reversed"
        assert history.json()["lines"][0]["product_name"] == "Чечил"

    def test_rejects_another_products_alias(self) -> None:
        supplier, sugar, salt = self.known_supplier()
        alias = ProductAlias(
            id=self.store.new_id(),
            product_id=salt.id,
            supplier_id=supplier.id,
            alias_normalized="соль мелкая",
            alias_raw="Соль мелкая",
        )
        self.store.aliases.append(
            alias,
        )

        response = self.delete(
            product_id=sugar.id,
            alias_id=alias.id,
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "Название у этого товара не найдено"}
        assert alias in self.store.aliases

    def test_protects_primary_name_even_if_its_casing_differs(self) -> None:
        _, sugar, _ = self.known_supplier()
        alias = self.store.aliases[0]
        sugar.name = "САХАР-ПЕСОК 1 КГ"

        response = self.delete(
            product_id=sugar.id,
            alias_id=alias.id,
        )

        assert response.status_code == 409
        assert response.json() == {"detail": "Основное название товара удалить нельзя"}
        assert alias in self.store.aliases

    def test_returns_no_content_on_repeat(self) -> None:
        supplier, sugar, _ = self.known_supplier()
        alias = ProductAlias(
            id=self.store.new_id(),
            product_id=sugar.id,
            supplier_id=supplier.id,
            alias_normalized="песок",
            alias_raw="Песок",
        )
        self.store.aliases.append(
            alias,
        )
        first = self.delete(
            product_id=sugar.id,
            alias_id=alias.id,
        )
        assert first.status_code == 204

        repeated = self.delete(
            product_id=sugar.id,
            alias_id=alias.id,
        )

        assert repeated.status_code == 204
        assert repeated.content == b""
        assert alias not in self.store.aliases
