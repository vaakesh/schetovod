from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from invoices.posting import InvoicePostingService
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.enums import InvoiceStatus, LedgerKind
from invoices.schemas import ConfirmedInvoice
from main import app
from tests.fakes import INN, invoice_payload
from tests.helpers import InvoiceApi


class TestConfirm(InvoiceApi):
    def test_injects_posting_repositories_with_one_session(self) -> None:
        app.dependency_overrides.clear()
        session = AsyncMock(
            spec=AsyncSession,
        )

        async def override_session() -> AsyncIterator[AsyncSession]:
            yield session

        app.dependency_overrides[get_session] = override_session
        result = ConfirmedInvoice(
            id=42,
            ledger_entry_id=43,
            retail_total=Decimal(
                value="155.00",
            ),
            revaluation=None,
            balance=Decimal(
                value="155.00",
            ),
        )

        with patch.object(
            target=InvoicePostingService,
            attribute="confirm_invoice",
            autospec=True,
            return_value=result,
        ) as confirm_invoice:
            response = self.client.post(
                url="/invoice/42/confirm",
                json={"occurred_on": "16-10-2026"},
            )

        assert response.status_code == 200
        assert response.json() == {
            "id": 42,
            "ledger_entry_id": 43,
            "retail_total": "155.00",
            "revaluation": None,
            "balance": "155.00",
        }
        await_args = confirm_invoice.await_args
        assert await_args is not None
        service = await_args.args[0]
        assert service.invoices.session is session
        assert service.suppliers.session is session
        assert service.products.session is session
        assert service.ledger.session is session
        confirm_invoice.assert_awaited_once_with(
            service,
            invoice_id=42,
            occurred_on=date(
                year=2026,
                month=10,
                day=16,
            ),
        )

    def test_posts_with_new_supplier_products_and_aliases(self) -> None:
        payload = invoice_payload()
        # the same product twice, spelled differently
        payload["items"].append(
            payload["items"][0] | {"line_no": "3", "name": "САХАР-ПЕСОК  1 кг"},
        )
        payload["totals"] = {"base_total": None, "cost_total": "280.00"}
        draft = self.upload(
            payload=payload,
        )
        form = draft["form"]
        form["supplier"] = {"name": "ООО «Поставщик»", "inn": INN}
        form["lines"][0]["retail_price"] = 65
        form["lines"][1]["retail_price"] = 40
        self.save(
            draft=draft,
            form=form,
        )

        response = self.confirm(
            draft=draft,
        )

        assert response.status_code == 200, response.text
        [supplier] = self.store.suppliers.values()
        assert (supplier.name, supplier.inn) == ("ООО «Поставщик»", INN)
        sugar, salt = self.store.products.values()
        assert [
            (product.supplier_id, product.name, product.markup_pct)
            for product in (sugar, salt)
        ] == [
            (
                supplier.id,
                "Сахар-песок 1 кг",
                Decimal(
                    value="30.00",
                ),
            ),
            (
                supplier.id,
                "Соль",
                Decimal(
                    value="33.33",
                ),
            ),
        ]
        assert [
            (alias.product_id, alias.alias_raw) for alias in self.store.aliases
        ] == [(sugar.id, "Сахар-песок 1 кг"), (salt.id, "Соль")]
        assert [
            (
                item.line_no,
                item.product_id,
                str(
                    item.retail_price,
                ),
            )
            for item in self.store.items
        ] == [(1, sugar.id, "65"), (2, salt.id, "40"), (3, sugar.id, "65")]
        [entry] = self.store.entries
        assert (entry.kind, entry.amount, entry.invoice_status) == (
            LedgerKind.INVOICE,
            Decimal(
                value="365.00",
            ),
            InvoiceStatus.CONFIRMED,
        )
        invoice = self.store.invoices[draft["id"]]
        assert (invoice.status, invoice.supplier_id) == (
            InvoiceStatus.CONFIRMED,
            supplier.id,
        )
        assert response.json() == {
            "id": draft["id"],
            "ledger_entry_id": entry.id,
            "retail_total": "365.00",
            "revaluation": None,
            "balance": "365.00",
        }

    def test_known_products_keep_or_change_the_markup(self) -> None:
        _, sugar, salt = self.known_supplier()
        draft = self.upload()
        form = draft["form"]
        # the price it already has keeps the markup, a new price changes it
        form["lines"][0]["retail_price"] = 65
        form["lines"][1]["retail_price"] = 45
        self.save(
            draft=draft,
            form=form,
        )

        response = self.confirm(
            draft=draft,
        )

        assert response.status_code == 200, response.text
        assert (sugar.markup_pct, salt.markup_pct) == (
            Decimal(
                value=30,
            ),
            Decimal(
                value="50.00",
            ),
        )
        assert (
            len(
                self.store.aliases,
            )
            == 2
        )

    def test_spelling_of_a_known_product_adds_an_alias(self) -> None:
        _, sugar, _ = self.known_supplier()
        draft = self.upload()
        form = draft["form"]
        form["lines"][0]["name"] = "Сахар 1кг"
        form["lines"][0]["product_id"] = sugar.id
        self.save(
            draft=draft,
            form=form,
        )

        response = self.confirm(
            draft=draft,
        )

        assert response.status_code == 200, response.text
        assert (
            self.store.aliases[-1].product_id,
            self.store.aliases[-1].alias_raw,
        ) == (sugar.id, "Сахар 1кг")
        assert self.store.items[0].name == "Сахар 1кг"

    def test_not_ready_draft_is_not_posted(self) -> None:
        draft = self.upload()

        response = self.confirm(
            draft=draft,
        )

        assert response.status_code == 409
        assert response.json()["detail"] == (
            "Провести нельзя: строка 1: новый товар, укажите розничную цену; "
            "строка 2: новый товар, укажите розничную цену"
        )
        assert (self.store.items, self.store.entries, self.store.commits) == ([], [], 1)

    def test_ledger_is_locked_before_the_draft_is_read(self) -> None:
        self.known_supplier()
        draft = self.upload()
        self.store.events.clear()

        response = self.confirm(
            draft=draft,
        )

        assert response.status_code == 200, response.text
        assert self.store.events == ["lock", "get_draft"]

    def test_invoice_confirmed_before_is_blocking(self) -> None:
        self.known_supplier()
        first = self.upload()
        assert (
            self.confirm(
                draft=first,
            ).status_code
            == 200
        )

        second = self.upload()

        assert self.blocking(
            draft=second,
        ) == [(None, f"эта накладная уже проведена под номером {first['id']}")]
        assert (
            self.confirm(
                draft=second,
            ).status_code
            == 409
        )

    def test_declines_draft_without_writing_ledger_entries(self) -> None:
        draft = self.upload()

        response = self.client.post(
            url=f"/invoice/{draft['id']}/decline",
        )

        assert response.status_code == 204
        assert response.content == b""
        assert self.store.invoices[draft["id"]].status == InvoiceStatus.DECLINED
        assert self.store.entries == []

    @pytest.mark.parametrize(
        argnames="action",
        argvalues=["decline", "confirm"],
    )
    def test_returns_404_when_draft_was_already_declined(self, action: str) -> None:
        draft = self.upload()
        declined = self.client.post(
            url=f"/invoice/{draft['id']}/decline",
        )
        assert declined.status_code == 204

        # decline takes no body and ignores it
        response = self.client.post(
            url=f"/invoice/{draft['id']}/{action}",
            json={
                "occurred_on": "16-10-2026",
            },
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "Черновик накладной не найден"}
