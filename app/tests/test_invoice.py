from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db import get_session
from enums import InvoiceStatus, LedgerKind
from main import app
from models import (
    ProductAlias,
)
from pricing import normalize_name
from schemas import (
    DraftForm,
    DraftTotals,
    InvoiceDraft,
    InvoiceExtraction,
)
from services import InvoiceService
from tests.fakes import INN, FakeStore, invoice_payload
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
            target=InvoiceService,
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
        assert service.ledger.session is session
        receive_invoice.assert_awaited_once_with(
            service,
            invoice=invoice,
            extracted=payload,
        )


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


class TestRecognizeImage(InvoiceApi):
    @pytest.fixture(
        autouse=True,
    )
    def enable_recognition(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            target=settings,
            name="include_api_openai",
            value=True,
        )

    def test_turned_off_recognition_does_not_call_openai(self) -> None:
        settings.include_api_openai = False

        response, extract = self.post_images(
            files=[
                ("files", ("page.jpg", b"page", "image/jpeg")),
            ],
            extracted=invoice_payload(),
        )

        assert response.status_code == 503
        extract.assert_not_awaited()

    def post_images(
        self,
        files: list[tuple[str, tuple[str, bytes, str]]],
        extracted: dict[str, Any],
    ) -> tuple[Any, AsyncMock]:
        extract = AsyncMock(
            return_value=extracted,
        )
        with patch(
            target="main.extract_invoice",
            new=extract,
        ):
            response = self.client.post(
                url="/invoice/image",
                files=files,
            )
        return response, extract

    def test_recognized_invoice_becomes_a_draft(self) -> None:
        response, extract = self.post_images(
            files=[
                ("files", ("page1.jpg", b"first", "image/jpeg")),
                ("files", ("page2.png", b"second", "image/png")),
            ],
            extracted=invoice_payload(),
        )

        assert response.status_code == 200, response.text
        call = extract.await_args
        assert call is not None
        images = call.kwargs["images"]
        assert [(image.content, image.media_type) for image in images] == [
            (b"first", "image/jpeg"),
            (b"second", "image/png"),
        ]
        draft = response.json()
        assert self.store.invoices[draft["id"]].extracted == invoice_payload()

    def test_rejects_a_file_that_is_not_an_image(self) -> None:
        response, extract = self.post_images(
            files=[
                ("files", ("invoice.pdf", b"%PDF", "application/pdf")),
            ],
            extracted=invoice_payload(),
        )

        assert response.status_code == 422
        extract.assert_not_awaited()

    def test_malformed_recognition_is_reported_by_field(self) -> None:
        payload = invoice_payload()
        payload["invoice_date"] = "12.08.2026"

        response, _ = self.post_images(
            files=[
                ("files", ("page.jpg", b"page", "image/jpeg")),
            ],
            extracted=payload,
        )

        assert response.status_code == 422
        assert [error["loc"] for error in response.json()["detail"]] == [
            ["body", "invoice_date"]
        ]
        assert self.store.invoices == {}


class TestSaveForm(InvoiceApi):
    def test_new_supplier_and_prices_make_it_ready_without_catalog_writes(self) -> None:
        draft = self.upload()
        form = draft["form"]
        form["supplier"] = {"name": "ООО «Поставщик»", "inn": INN}
        form["lines"][0]["retail_price"] = 65
        form["lines"][1]["retail_price"] = 40

        draft = self.save(
            draft=draft,
            form=form,
        )

        assert draft["ready"], draft["issues"]
        assert [
            (line["new_product"], line["markup_pct"], line["retail_price"])
            for line in draft["lines"]
        ] == [(True, "30.00", "65"), (True, "33.33", "40")]
        assert draft["form"] == form
        assert (self.store.suppliers, self.store.products, self.store.aliases) == (
            {},
            {},
            [],
        )
        invoice = self.store.invoices[draft["id"]]
        assert invoice.form == form
        assert invoice.extracted == invoice_payload()

    def test_header_columns_follow_the_form(self) -> None:
        supplier, _, _ = self.known_supplier()
        draft = self.upload()
        form = draft["form"]
        form["invoice_number"] = "43"
        form["invoice_date"] = "13-08-2026"

        self.save(
            draft=draft,
            form=form,
        )
        invoice = self.store.invoices[draft["id"]]
        assert (invoice.invoice_number, invoice.invoice_date, invoice.supplier_id) == (
            "43",
            date(
                year=2026,
                month=8,
                day=13,
            ),
            supplier.id,
        )

        form["supplier"] = {"name": "Другой", "inn": None}
        self.save(
            draft=draft,
            form=form,
        )
        assert invoice.supplier_id is None

    def test_edited_lines_are_recalculated(self) -> None:
        self.known_supplier()
        draft = self.upload()
        form = draft["form"]
        form["lines"][0]["cost_price_total"] = "150.00"
        form["lines"][1]["vat_percent"] = "20"

        draft = self.save(
            draft=draft,
            form=form,
        )

        assert [
            (
                line["cost_price"],
                line["base_price_total"],
                line["retail_price"],
            )
            for line in draft["lines"]
        ] == [("60.00", "150.00", "78"), ("30.00", "25.00", "36")]
        # what the model read disagrees now, which is only worth a look
        assert draft["ready"]
        assert [issue["message"] for issue in draft["issues"]] == [
            (
                "цена на полке меняется с 65 на 78 ₽, укажите, сколько старого товара "
                "осталось, чтобы переоценить"
            ),
            "сумма без НДС: в накладной 125.00, по сумме строки 150.00",
            "цена за единицу: в накладной 50.00, по сумме строки 60.00",
            "цена без НДС: в накладной 50.00, по сумме строки 60.00",
            "сумма без НДС: в накладной 30.00, по сумме строки 25.00",
            "итог к оплате: в накладной 155.00, по строкам 180.00",
            "итог без НДС: в накладной 155.00, по строкам 175.00",
        ]

    def test_lines_may_be_added_and_removed(self) -> None:
        self.known_supplier()
        draft = self.upload()
        form = draft["form"]
        form["lines"] = [
            form["lines"][1],
            form["lines"][1] | {"name": "Перец", "retail_price": 50},
        ]
        form["totals"] = {"cost_total": "60.00", "base_total": None}

        draft = self.save(
            draft=draft,
            form=form,
        )

        assert draft["issues"] == []
        assert [
            (line["product_name"], line["new_product"]) for line in draft["lines"]
        ] == [("Соль", False), ("Перец", True)]

    def test_spelling_of_a_known_product(self) -> None:
        _, sugar, _ = self.known_supplier()
        draft = self.upload()
        form = draft["form"]
        form["lines"][0]["name"] = "Сахар 1кг"
        form["lines"][0]["product_id"] = sugar.id

        draft = self.save(
            draft=draft,
            form=form,
        )

        assert (
            draft["lines"][0]["product_id"],
            draft["lines"][0]["product_name"],
            draft["lines"][0]["retail_price"],
        ) == (sugar.id, "Сахар-песок 1 кг", "65")
        assert draft["ready"]

    @pytest.mark.parametrize(
        argnames=("change", "problems", "expected_supplier_id"),
        argvalues=[
            ({"supplier": {"id": 999}}, [(None, "продавца с id 999 нет")], None),
            (
                {"supplier": {"name": "Двойник", "inn": INN}},
                [(None, f"продавец с ИНН {INN} уже есть, выберите его")],
                None,
            ),
            ({"invoice_number": None}, [(None, "номер накладной не указан")], 1),
            ({"line": {"quantity": None}}, [(1, "количество не указано")], 1),
            ({"line": {"name": None}}, [(1, "название не указано")], 1),
            (
                {"line": {"name": "Новинка"}},
                [(1, "новый товар, укажите розничную цену")],
                1,
            ),
            ({"line": {"product_id": 7}}, [(1, "у продавца нет товара с id 7")], 1),
            (
                {"line": {"product_id": 4}},
                [(1, "это название уже относится к товару «Сахар-песок 1 кг»")],
                1,
            ),
            (
                {"line": {"retail_price": 40}},
                [
                    (
                        1,
                        (
                            "при цене 40 и закупке 50.00 наценка -20.00%, "
                            "а она должна быть от 0 до 999.99%"
                        ),
                    ),
                ],
                1,
            ),
            (
                {"line": {"cost_price_total": "0.00", "retail_price": 40}},
                [(1, "нет закупочной цены, наценку посчитать не из чего")],
                1,
            ),
            (
                {
                    "second": {"name": "Сахар-песок 1 кг", "retail_price": 70},
                    "line": {"retail_price": 66},
                },
                [(2, "у этого товара уже задана другая цена в строке 1")],
                1,
            ),
        ],
    )
    def test_reports_blocking_problem_and_keeps_draft_unready(
        self,
        change: dict[str, Any],
        problems: list[tuple[int | None, str]],
        expected_supplier_id: int | None,
    ) -> None:
        self.known_supplier()

        stranger = self.store.add_supplier(
            name="Чужой",
            inn=None,
        )

        self.store.add_product(
            supplier=stranger,
            name="Чужой товар",
            markup_pct="10",
            retail_price="100",
        )

        draft = self.upload()

        form = draft["form"] | {
            key: value for key, value in change.items() if key not in ("line", "second")
        }
        form["lines"] = [
            form["lines"][0]
            | change.get(
                "line",
                {},
            ),
            form["lines"][1]
            | change.get(
                "second",
                {},
            ),
        ]
        saved = self.save(
            draft=draft,
            form=form,
        )

        assert (
            self.blocking(
                draft=saved,
            )
            == problems
        )
        assert not saved["ready"]

        assert self.store.invoices[draft["id"]].supplier_id == expected_supplier_id

    @pytest.mark.parametrize(
        argnames=("scope", "change", "location"),
        argvalues=[
            ("line", {"cost_price": "50.00"}, ["body", "lines", 0, "cost_price"]),
            ("root", {"lines": [{"name": "Без остальных полей"}]}, None),
            ("root", {"supplier": {"id": 0}}, None),
            (
                "root",
                {"supplier": {"id": 1, "name": "И то и другое", "inn": None}},
                None,
            ),
            ("root", {"invoice_date": "2026-08-12"}, ["body", "invoice_date"]),
            ("line", {"retail_price": 0}, ["body", "lines", 0, "retail_price"]),
            ("line", {"quantity": 2}, ["body", "lines", 0, "quantity"]),
            ("root", {"status": "confirmed"}, ["body", "status"]),
        ],
    )
    def test_returns_422_when_form_is_invalid(
        self,
        scope: str,
        change: dict[str, Any],
        location: list[str | int] | None,
    ) -> None:
        draft = self.upload()
        form = draft["form"]
        if scope == "line":
            form["lines"][0].update(
                change,
            )
        else:
            form.update(
                change,
            )

        response = self.client.put(
            url=f"/invoice/{draft['id']}",
            json=form,
        )

        assert response.status_code == 422
        errors = response.json()["detail"]
        assert errors
        if location is not None:
            assert [error["loc"] for error in errors] == [location]
        assert self.store.invoices[draft["id"]].form is None

    @pytest.mark.parametrize(
        argnames="method",
        argvalues=("GET", "PUT"),
    )
    def test_returns_404_when_invoice_is_no_longer_a_draft(
        self,
        method: str,
    ) -> None:
        draft = self.upload()

        self.store.invoices[draft["id"]].status = InvoiceStatus.DECLINED

        response = self.client.request(
            method=method,
            url=f"/invoice/{draft['id']}",
            json=draft["form"] if method == "PUT" else None,
        )

        assert response.status_code == 404


class TestConfirm(InvoiceApi):
    def confirm(
        self,
        draft: dict[str, Any],
    ) -> Any:
        return self.client.post(
            url=f"/invoice/{draft['id']}/confirm",
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

        response = self.client.post(
            url=f"/invoice/{draft['id']}/{action}",
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "Черновик накладной не найден"}


class TestRevaluationOnConfirm(InvoiceApi):
    def draft_with_prices(
        self,
        prices: list[int | None],
        quantities: list[str | None],
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """the invoice of the known supplier with the given shelf prices and old stock"""
        draft = self.upload(
            payload=payload,
        )
        form = draft["form"]
        for line, price, quantity in zip(
            form["lines"],
            prices,
            quantities,
            strict=True,
        ):
            line["retail_price"] = price
            line["revalue_quantity"] = quantity
        return self.save(
            draft=draft,
            form=form,
        )

    def confirm(
        self,
        draft: dict[str, Any],
    ) -> dict[str, Any]:
        response = self.client.post(
            url=f"/invoice/{draft['id']}/confirm",
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_changed_price_asks_for_the_old_stock(self) -> None:
        self.known_supplier()

        draft = self.draft_with_prices(
            prices=[70, None],
            quantities=[None, None],
        )

        assert draft["ready"]
        assert [line["previous_retail_price"] for line in draft["lines"]] == [
            "65",
            None,
        ]
        assert {
            "line": 1,
            "message": (
                "цена на полке меняется с 65 на 70 ₽, укажите, сколько старого товара "
                "осталось, чтобы переоценить"
            ),
            "blocking": False,
            "code": "price_changed",
        } in draft["issues"]

    def test_old_stock_is_revalued_with_the_invoice(self) -> None:
        _, sugar, salt = self.known_supplier()
        draft = self.draft_with_prices(
            prices=[70, None],
            quantities=["4", None],
        )
        assert [issue["code"] for issue in draft["issues"]] == []

        result = self.confirm(
            draft=draft,
        )

        # 2.5 kg at 70 and the salt at 36, then 4 kg on the shelf go up by 5
        assert (result["retail_total"], result["revaluation"], result["balance"]) == (
            "211.00",
            "20.00",
            "231.00",
        )
        _, entry = self.store.entries
        assert (entry.kind, entry.amount, entry.comment) == (
            LedgerKind.REVALUATION,
            Decimal(
                value="20.00",
            ),
            "по накладной № 00042/А",
        )
        [item] = self.store.revaluations
        assert (
            item.ledger_entry_id,
            item.product_id,
            item.invoice_item_id,
            item.quantity,
            item.old_price,
            item.new_price,
        ) == (
            entry.id,
            sugar.id,
            self.store.items[0].id,
            Decimal(
                value=4,
            ),
            Decimal(
                value=65,
            ),
            Decimal(
                value=70,
            ),
        )
        assert (sugar.retail_price, salt.retail_price) == (
            Decimal(
                value=70,
            ),
            Decimal(
                value=36,
            ),
        )

    def test_new_price_without_old_stock_only_moves_the_shelf_price(self) -> None:
        _, sugar, _ = self.known_supplier()

        result = self.confirm(
            draft=self.draft_with_prices(
                prices=[70, None],
                quantities=[None, None],
            ),
        )

        assert result["revaluation"] is None
        assert (
            [entry.kind for entry in self.store.entries],
            self.store.revaluations,
        ) == ([LedgerKind.INVOICE], [])
        assert sugar.retail_price == Decimal(
            value=70,
        )

    def test_new_product_gets_its_shelf_price(self) -> None:
        draft = self.upload()
        form = draft["form"]
        form["lines"][0]["retail_price"] = 65
        form["lines"][1]["retail_price"] = 40
        self.confirm(
            draft=self.save(
                draft=draft,
                form=form,
            ),
        )

        assert [product.retail_price for product in self.store.products.values()] == [
            65,
            40,
        ]

    @pytest.mark.parametrize(
        argnames=("prices", "quantities", "expected"),
        argvalues=[
            (
                [None, None, None],
                [None, "2", None],
                [(2, "цена на полке не меняется, переоценивать нечего")],
            ),
            (
                [70, None, None],
                ["4", None, "1"],
                [(3, "переоценка этого товара уже указана в строке 1")],
            ),
            (
                [66, None, None],
                ["0.001", None, None],
                [(1, "переоценка выходит меньше копейки, проверьте количество")],
            ),
        ],
    )
    def test_wrong_old_stock_is_blocking(
        self,
        prices: list[int | None],
        quantities: list[str | None],
        expected: list[tuple[int | None, str]],
    ) -> None:
        self.known_supplier()

        payload = invoice_payload()

        payload["items"].append(
            payload["items"][0] | {"line_no": "3"},
        )

        payload["totals"] = {"base_total": None, "cost_total": "280.00"}

        draft = self.draft_with_prices(
            prices=prices,
            quantities=quantities,
            payload=payload,
        )

        assert (
            self.blocking(
                draft=draft,
            )
            == expected
        )

    def test_draft_saved_before_the_revaluation_still_opens(self) -> None:
        self.known_supplier()
        draft = self.upload()
        form = draft["form"]
        for line in form["lines"]:
            del line["revalue_quantity"]
        self.store.invoices[draft["id"]].form = form

        response = self.client.get(
            url=f"/invoice/{draft['id']}",
        )

        assert response.status_code == 200, response.text
        assert response.json()["ready"]


class TestInvoiceList(InvoiceApi):
    def confirmed(self) -> dict[str, Any]:
        """an invoice of the known supplier, posted at the current markups"""
        self.known_supplier()
        draft = self.upload()
        response = self.client.post(
            url=f"/invoice/{draft['id']}/confirm",
        )
        assert response.status_code == 200, response.text
        return draft

    def test_lists_newest_first_with_filter_and_search(self) -> None:
        posted = self.confirmed()
        payload = invoice_payload()
        payload["supplier"] = {"name": "ИП Иванов", "inn": None}
        payload["invoice_number"] = "777"
        draft = self.upload(
            payload=payload,
        )

        everything = self.client.get(
            url="/invoice",
        ).json()
        confirmed = self.client.get(
            url="/invoice",
            params={"status": "confirmed"},
        ).json()
        found = self.client.get(
            url="/invoice",
            params={"q": "иванов"},
        ).json()
        first_page = self.client.get(
            url="/invoice",
            params={"limit": 1},
        ).json()

        assert [
            (
                item["id"],
                item["status"],
                item["supplier_name"],
                item["retail_total"],
                item["lines"],
            )
            for item in everything["items"]
        ] == [
            (draft["id"], "draft", "ИП Иванов", None, 2),
            (posted["id"], "confirmed", "ООО «Поставщик»", "198.50", 2),
        ]
        assert [item["id"] for item in confirmed["items"]] == [posted["id"]]
        assert [item["id"] for item in found["items"]] == [draft["id"]]
        assert (
            [item["id"] for item in first_page["items"]],
            first_page["has_more"],
        ) == ([draft["id"]], True)

    def test_posted_invoice_shows_the_lines_as_posted(self) -> None:
        draft = self.confirmed()

        response = self.client.get(
            url=f"/invoice/{draft['id']}/confirmed",
        )

        assert response.status_code == 200, response.text
        posted = response.json()
        assert (
            posted["invoice_number"],
            posted["invoice_date"],
            posted["supplier"]["name"],
            posted["cost_total"],
            posted["retail_total"],
            posted["ledger_entry_id"],
        ) == (
            "00042/А",
            "12-08-2026",
            "ООО «Поставщик»",
            "155.00",
            "198.50",
            self.store.entries[0].id,
        )
        assert [
            (
                line["line_no"],
                line["product_name"],
                Decimal(
                    value=line["retail_price"],
                ),
                Decimal(
                    value=line["retail_price_total"],
                ),
            )
            for line in posted["lines"]
        ] == [
            (
                1,
                "Сахар-песок 1 кг",
                Decimal(
                    value=65,
                ),
                Decimal(
                    value="162.50",
                ),
            ),
            (
                2,
                "Соль",
                Decimal(
                    value=36,
                ),
                Decimal(
                    value=36,
                ),
            ),
        ]
        assert self.store.locks == 1

    def test_draft_is_not_a_posted_invoice(self) -> None:
        draft = self.upload()

        assert (
            self.client.get(
                url=f"/invoice/{draft['id']}/confirmed",
            ).status_code
            == 404
        )


class TestSimilarProduct(InvoiceApi):
    def upload_misread(self) -> dict[str, Any]:
        """the sugar misread by a letter, the second line is nothing the supplier has"""
        payload = invoice_payload()
        payload["items"][0]["name"] = "Сахар-песк 1 кг"
        payload["items"][1]["name"] = "Перец"
        return self.upload(
            payload=payload,
        )

    def similar_issues(
        self,
        draft: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return [
            issue for issue in draft["issues"] if issue["code"] == "similar_product"
        ]

    def test_misread_name_suggests_the_product_as_a_warning(self) -> None:
        _, sugar, _ = self.known_supplier()
        # a close name at another supplier is not a candidate
        other = self.store.add_supplier(
            name="ИП Иванов",
            inn=None,
        )
        self.store.add_product(
            supplier=other,
            name="Перец молотый",
            markup_pct="10",
            retail_price="100",
        )

        draft = self.upload_misread()

        assert [line["similar"] for line in draft["lines"]] == [
            [{"id": sugar.id, "name": "Сахар-песок 1 кг", "similarity": 96}],
            [],
        ]
        assert self.similar_issues(
            draft=draft,
        ) == [
            {
                "line": 1,
                "message": "похож на товар «Сахар-песок 1 кг» (96%), проверьте, не он ли это",
                "blocking": False,
                "code": "similar_product",
            },
        ]
        # nothing is decided for the user, both lines are new until a price or a link is set
        assert self.blocking(
            draft=draft,
        ) == [
            (1, "новый товар, укажите розничную цену"),
            (2, "новый товар, укажите розничную цену"),
        ]

    def test_known_and_linked_lines_are_not_compared(self) -> None:
        _, _, salt = self.known_supplier()
        draft = self.upload()
        assert [line["similar"] for line in draft["lines"]] == [[], []]

        draft = self.upload_misread()
        form = draft["form"]
        form["lines"][0]["product_id"] = salt.id
        draft = self.save(
            draft=draft,
            form=form,
        )

        assert (
            draft["lines"][0]["similar"],
            self.similar_issues(
                draft=draft,
            ),
        ) == ([], [])

    def test_linking_the_suggestion_adds_the_spelling_when_posted(self) -> None:
        _, sugar, _ = self.known_supplier()
        draft = self.upload_misread()
        form = draft["form"]
        form["lines"][0]["product_id"] = draft["lines"][0]["similar"][0]["id"]
        form["lines"][1]["retail_price"] = 40
        self.save(
            draft=draft,
            form=form,
        )

        response = self.client.post(
            url=f"/invoice/{draft['id']}/confirm",
        )

        assert response.status_code == 200, response.text
        assert (sugar.id, "сахар-песк 1 кг") in [
            (alias.product_id, alias.alias_normalized) for alias in self.store.aliases
        ]


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
            {"id": self.dvor.id, "name": "ООО «Молочный двор»", "inn": "7707083893"},
        ]

    def test_finds_by_the_start_of_the_inn(self) -> None:
        response = self.client.get(
            url="/supplier",
            params={"q": "4719"},
        )

        assert response.status_code == 200
        assert response.json() == [
            {"id": self.petrov.id, "name": "ИП Петров", "inn": "471909695290"}
        ]

    def test_without_a_query_lists_everyone_by_name(self) -> None:
        assert self.search(
            params={},
        ) == [
            {"id": self.market.id, "name": "Агроторг", "inn": None},
            {"id": self.petrov.id, "name": "ИП Петров", "inn": "471909695290"},
            {"id": self.dvor.id, "name": "ООО «Молочный двор»", "inn": "7707083893"},
        ]

    def test_limits_number_of_suppliers(self) -> None:
        assert self.search(
            params={"limit": 2},
        ) == [
            {"id": self.market.id, "name": "Агроторг", "inn": None},
            {"id": self.petrov.id, "name": "ИП Петров", "inn": "471909695290"},
        ]


class TestProductSearch(InvoiceApi):
    def search(
        self,
        supplier_id: int,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        response = self.client.get(
            url=f"/supplier/{supplier_id}/products",
            params=params,
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_without_a_query_lists_the_supplier_products_by_name(self) -> None:
        supplier, sugar, salt = self.known_supplier()
        other = self.store.add_supplier(
            name="ИП Иванов",
            inn=None,
        )
        self.store.add_product(
            supplier=other,
            name="Сахар у другого",
            markup_pct="10",
            retail_price="100",
        )

        assert self.search(
            supplier_id=supplier.id,
            params={},
        ) == [
            {
                "id": sugar.id,
                "name": "Сахар-песок 1 кг",
                "markup_pct": "30",
                "unit": None,
                "vat_percent": None,
                "cost_price": None,
                # the shelf price is known before the product is ever posted
                "retail_price": "65",
            },
            {
                "id": salt.id,
                "name": "Соль",
                "markup_pct": "20",
                "unit": None,
                "vat_percent": None,
                "cost_price": None,
                "retail_price": "36",
            },
        ]

    @pytest.mark.parametrize(
        argnames="query",
        argvalues=("САХ", 'песок "русский"'),
    )
    def test_finds_by_a_part_of_the_name_or_of_another_spelling(
        self,
        query: str,
    ) -> None:
        supplier, sugar, _ = self.known_supplier()

        self.store.aliases.append(
            ProductAlias(
                id=self.store.new_id(),
                product_id=sugar.id,
                supplier_id=supplier.id,
                alias_normalized=normalize_name(
                    name="Песок «Русский» 1кг",
                ),
                alias_raw="Песок «Русский» 1кг",
            ),
        )

        assert [
            product["id"]
            for product in self.search(
                supplier_id=supplier.id,
                params={"q": query},
            )
        ] == [sugar.id]

    def test_shows_the_last_posted_line(self) -> None:
        supplier, sugar, _ = self.known_supplier()
        draft = self.upload()
        assert (
            self.client.post(
                url=f"/invoice/{draft['id']}/confirm",
            ).status_code
            == 200
        )

        found = self.search(
            supplier_id=supplier.id,
            params={"q": "сахар"},
        )

        assert found[0] == {
            "id": sugar.id,
            "name": "Сахар-песок 1 кг",
            "markup_pct": "30",
            "unit": "кг",
            "vat_percent": None,
            "cost_price": "50.00",
            "retail_price": "65",
        }

    def test_returns_404_when_supplier_does_not_exist(self) -> None:
        response = self.client.get(
            url="/supplier/999/products",
        )

        assert response.status_code == 404


class TestCatalog(InvoiceApi):
    def catalog(self) -> dict[str, Any]:
        response = self.client.get(
            url="/catalog",
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_empty_without_suppliers(self) -> None:
        assert self.catalog() == {"suppliers": [], "products": []}

    def test_lists_every_supplier_and_every_product_by_name(self) -> None:
        supplier, sugar, salt = self.known_supplier()
        other = self.store.add_supplier(
            name="Агроторг",
            inn=None,
        )
        flour = self.store.add_product(
            supplier=other,
            name="Мука",
            markup_pct="10",
            retail_price="90",
        )
        empty = self.store.add_supplier(
            name="ИП Петров",
            inn=None,
        )

        catalog = self.catalog()

        assert catalog["suppliers"] == [
            {"id": other.id, "name": "Агроторг", "inn": None},
            {"id": empty.id, "name": "ИП Петров", "inn": None},
            {"id": supplier.id, "name": "ООО «Поставщик»", "inn": INN},
        ]
        assert [
            (product["id"], product["supplier_id"]) for product in catalog["products"]
        ] == [
            (flour.id, other.id),
            (sugar.id, supplier.id),
            (salt.id, supplier.id),
        ]

    def test_shows_the_last_posted_line_and_other_spellings(self) -> None:
        supplier, sugar, _ = self.known_supplier()
        self.store.aliases.append(
            ProductAlias(
                id=self.store.new_id(),
                product_id=sugar.id,
                supplier_id=supplier.id,
                alias_normalized=normalize_name(
                    name="Песок «Русский» 1кг",
                ),
                alias_raw="Песок «Русский» 1кг",
            ),
        )
        draft = self.upload()
        assert (
            self.client.post(
                url=f"/invoice/{draft['id']}/confirm",
            ).status_code
            == 200
        )

        assert self.catalog()["products"][0] == {
            "id": sugar.id,
            "name": "Сахар-песок 1 кг",
            "markup_pct": "30",
            "unit": "кг",
            "vat_percent": None,
            "cost_price": "50.00",
            "retail_price": "65",
            "supplier_id": supplier.id,
            # the spelling that is the name itself is not repeated
            "spellings": ["Песок «Русский» 1кг"],
        }
