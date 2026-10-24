from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

from invoices.drafts import InvoiceDraftService
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from invoices.extraction import InvoiceExtraction
from invoices.schemas import DraftForm, DraftTotals, InvoiceDraft
from main import app
from tests.fakes import INN, invoice_payload
from tests.helpers import InvoiceApi


class TestReceiveInvoice(InvoiceApi):
    def test_initial_form_is_built_from_the_extraction(self) -> None:
        draft = self.upload()

        assert draft["form"] == {
            "invoice_number": "00042/А",
            "invoice_date": "12-08-2026",
            # not found by inn, offered as a new one
            "supplier": {"name": "ООО «Поставщик»", "inn": INN},
            # without VAT the only printed total is the total to pay
            "totals": {"cost_total": "155.00", "base_total": "155.00"},
            "lines": [
                {
                    "line_no": 1,
                    "name": "Сахар-песок 1 кг",
                    "quantity": "2.500",
                    "unit": "кг",
                    "vat_percent": None,
                    "cost_price_total": "125.00",
                    "product_id": None,
                    "retail_price": None,
                    "revalue_quantity": None,
                },
                {
                    "line_no": 2,
                    "name": "Соль",
                    "quantity": "1",
                    "unit": "шт",
                    "vat_percent": None,
                    # without VAT the total may be read into either field
                    "cost_price_total": "30.00",
                    "product_id": None,
                    "retail_price": None,
                    "revalue_quantity": None,
                },
            ],
        }
        assert draft["extraction"] == invoice_payload()
        invoice = self.store.invoices[draft["id"]]
        assert invoice.form is None
        assert invoice.extracted == invoice_payload()
        assert self.store.commits == 1

    def test_unknown_supplier_is_offered_as_a_new_one(self) -> None:
        draft = self.upload()

        assert self.blocking(
            draft=draft,
        ) == [
            (1, "новый товар, укажите розничную цену"),
            (2, "новый товар, укажите розничную цену"),
        ]
        assert draft["supplier"] is None
        # nothing is written until the invoice is confirmed
        assert (self.store.suppliers, self.store.invoices[draft["id"]].supplier_id) == (
            {},
            None,
        )

    def test_supplier_without_a_name_is_not_chosen(self) -> None:
        payload = invoice_payload()
        payload["supplier"] = {"name": None, "inn": INN}

        draft = self.upload(
            payload=payload,
        )

        assert draft["form"]["supplier"] is None
        # the products may still be found once the supplier is chosen
        assert self.blocking(
            draft=draft,
        ) == [(None, "продавец не выбран")]
        assert [line["new_product"] for line in draft["lines"]] == [False, False]

    def test_new_supplier_alike_an_existing_one_is_a_warning(self) -> None:
        existing = self.store.add_supplier(
            name="ООО «Поставщик»",
            inn=None,
        )

        draft = self.upload()

        assert [candidate["id"] for candidate in draft["supplier_candidates"]] == [
            existing.id
        ]
        assert {
            "line": None,
            "message": "похожий продавец уже есть в базе, проверьте, не он ли это",
            "blocking": False,
            "code": None,
        } in draft["issues"]

    def test_new_supplier_has_only_new_products(self) -> None:
        draft = self.upload()
        form = draft["form"]
        form["supplier"] = {"name": "ООО «Поставщик»", "inn": None}

        draft = self.save(
            draft=draft,
            form=form,
        )

        assert self.blocking(
            draft=draft,
        ) == [
            (1, "новый товар, укажите розничную цену"),
            (2, "новый товар, укажите розничную цену"),
        ]
        assert [line["new_product"] for line in draft["lines"]] == [True, True]

    def test_known_supplier_and_products_make_it_ready(self) -> None:
        supplier, sugar, salt = self.known_supplier()

        draft = self.upload()

        assert draft["ready"], draft["issues"]
        assert draft["form"]["supplier"] == {"id": supplier.id}
        assert draft["supplier"] == {
            "id": supplier.id,
            "name": supplier.name,
            "short_name": None,
            "inn": supplier.inn,
        }
        assert [
            (line["product_id"], line["markup_pct"], line["retail_price"])
            for line in draft["lines"]
        ] == [(sugar.id, "30", "65"), (salt.id, "20", "36")]
        assert draft["totals"] == {
            "base_total": "155.00",
            "cost_total": "155.00",
            "retail_total": "198.50",
        }
        assert self.store.invoices[draft["id"]].supplier_id == supplier.id

    def test_suggests_suppliers_by_product_names_and_name(self) -> None:
        by_aliases = self.store.add_supplier(
            name="ИП Петров",
            inn=None,
        )
        self.store.add_product(
            supplier=by_aliases,
            name="Соль",
            markup_pct="20",
            retail_price="36",
        )
        by_name = self.store.add_supplier(
            name="ООО «Поставщик»",
            inn=None,
        )
        # another inn is someone else
        self.store.add_supplier(
            name="ООО «Поставщик» и сыновья",
            inn="7702222222",
        )

        draft = self.upload()

        assert [
            (candidate["id"], candidate["matched_lines"])
            for candidate in draft["supplier_candidates"]
        ] == [(by_aliases.id, 1), (by_name.id, 0)]

    def test_untouched_draft_picks_up_a_supplier_added_later(self) -> None:
        draft = self.upload()
        supplier, _, _ = self.known_supplier()

        response = self.client.get(
            url=f"/invoice/{draft['id']}",
        )

        assert response.status_code == 200
        assert response.json()["form"]["supplier"] == {"id": supplier.id}
        assert response.json()["ready"]

    def test_injects_service_repositories_and_session(self) -> None:
        app.dependency_overrides.clear()
        session = AsyncMock(
            spec=AsyncSession,
        )

        async def override_session() -> AsyncIterator[AsyncSession]:
            yield session

        app.dependency_overrides[get_session] = override_session
        payload = invoice_payload()
        invoice = InvoiceExtraction.model_validate(
            obj=payload,
        )
        result = InvoiceDraft(
            id=42,
            ready=False,
            issues=[],
            form=DraftForm.model_validate(
                obj={
                    "invoice_number": None,
                    "invoice_date": None,
                    "supplier": None,
                    "totals": {"cost_total": None, "base_total": None},
                    "lines": [],
                },
            ),
            lines=[],
            totals=DraftTotals(
                base_total=None,
                cost_total=None,
                retail_total=None,
            ),
            supplier=None,
            supplier_candidates=[],
            extraction=invoice,
        )

        with patch.object(
            target=InvoiceDraftService,
            attribute="receive_invoice",
            autospec=True,
            return_value=result,
        ) as receive_invoice:
            response = self.client.post(
                url="/invoice",
                json=payload,
            )

        assert response.status_code == 200
        assert response.json() == {
            "id": 42,
            "ready": False,
            "issues": [],
            "form": {
                "invoice_number": None,
                "invoice_date": None,
                "supplier": None,
                "totals": {"cost_total": None, "base_total": None},
                "lines": [],
            },
            "lines": [],
            "totals": {
                "base_total": None,
                "cost_total": None,
                "retail_total": None,
            },
            "supplier": None,
            "supplier_candidates": [],
            "extraction": payload,
        }
        await_args = receive_invoice.await_args
        assert await_args is not None
        service = await_args.args[0]
        assert service.invoices.session is session
        assert service.suppliers.session is session
        assert service.products.session is session
        receive_invoice.assert_awaited_once_with(
            service,
            invoice=invoice,
            extracted=payload,
        )
