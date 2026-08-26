import unittest
from collections.abc import AsyncIterator, Collection
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db import get_session
from enums import InvoiceStatus, LedgerKind
from main import app
from models import (
    Invoice,
    InvoiceItem,
    LedgerEntry,
    Product,
    ProductAlias,
    Supplier,
)
from pricing import normalize_name
from repositories import (
    InvoiceRepository,
    InvoiceRow,
    LedgerRepository,
    ProductRepository,
    ProductRow,
    SupplierRepository,
)
from schemas import (
    DraftForm,
    DraftTotals,
    InvoiceDraft,
    InvoiceExtraction,
)
from services import InvoiceService

INN = "7701234560"


def invoice_payload() -> dict[str, Any]:
    return {
        "supplier": {"name": "ООО «Поставщик»", "inn": INN},
        "invoice_number": "00042/А",
        "invoice_date": "12-08-2026",
        "items": [
            {
                "line_no": "1",
                "name": "Сахар-песок 1 кг",
                "quantity": "2.500",
                "unit": "кг",
                "base_price": "50.00",
                "base_price_total": "125.00",
                "cost_price": "50.00",
                "cost_price_total": "125.00",
                "vat_percent": None,
            },
            {
                "line_no": "2",
                "name": "Соль",
                "quantity": "1",
                "unit": "шт",
                "base_price": None,
                "base_price_total": "30.00",
                "cost_price": None,
                "cost_price_total": None,
                "vat_percent": None,
            },
        ],
        "totals": {"base_total": "155.00", "cost_total": None},
    }


class FakeStore:
    """the database for one test, the fake repositories share it"""

    def __init__(self) -> None:
        self.invoices: dict[int, Invoice] = {}
        self.suppliers: dict[int, Supplier] = {}
        self.products: dict[int, Product] = {}
        self.aliases: list[ProductAlias] = []
        self.items: list[InvoiceItem] = []
        self.entries: list[LedgerEntry] = []
        self.commits = 0
        self.locks = 0
        # the order of the ledger locks and the draft reads
        self.events: list[str] = []
        self.last_id = 0

    def new_id(self) -> int:
        self.last_id += 1
        return self.last_id

    def add_supplier(
        self,
        name: str,
        inn: str | None,
    ) -> Supplier:
        supplier = Supplier(
            id=self.new_id(),
            name=name,
            inn=inn,
        )
        self.suppliers[supplier.id] = supplier
        return supplier

    def add_product(
        self,
        supplier: Supplier,
        name: str,
        markup_pct: str,
        retail_price: str,
    ) -> Product:
        product = Product(
            id=self.new_id(),
            supplier_id=supplier.id,
            name=name,
            markup_pct=Decimal(
                value=markup_pct,
            ),
        )
        self.products[product.id] = product
        self.aliases.append(
            ProductAlias(
                id=self.new_id(),
                product_id=product.id,
                supplier_id=supplier.id,
                alias_normalized=normalize_name(
                    name=name,
                ),
                alias_raw=name,
            ),
        )
        return product


class FakeInvoices:
    def __init__(
        self,
        store: FakeStore,
    ) -> None:
        self.store = store

    async def create(
        self,
        invoice: Invoice,
    ) -> Invoice:
        invoice.id = self.store.new_id()
        # the server default is applied on insert, there is none here
        invoice.created_at = datetime.now(
            tz=UTC,
        )
        self.store.invoices[invoice.id] = invoice
        return invoice

    async def get_draft(
        self,
        invoice_id: int,
    ) -> Invoice | None:
        self.store.events.append(
            "get_draft",
        )
        invoice = self.store.invoices.get(
            invoice_id,
        )
        if invoice is None or invoice.status != InvoiceStatus.DRAFT:
            return None
        return invoice

    async def find_confirmed(
        self,
        supplier_id: int,
        invoice_number: str,
        invoice_date: date,
    ) -> Invoice | None:
        for invoice in self.store.invoices.values():
            if (
                invoice.status == InvoiceStatus.CONFIRMED
                and invoice.supplier_id == supplier_id
                and invoice.invoice_number == invoice_number
                and invoice.invoice_date == invoice_date
            ):
                return invoice
        return None

    async def search(
        self,
        status: InvoiceStatus | None,
        query: str | None,
        limit: int,
        offset: int,
    ) -> list[InvoiceRow]:
        rows = []
        for invoice in sorted(
            self.store.invoices.values(),
            key=lambda invoice: -invoice.id,
        ):
            supplier = None
            if invoice.supplier_id is not None:
                supplier = self.store.suppliers.get(
                    invoice.supplier_id,
                )
            name = supplier.name if supplier else invoice.extracted["supplier"]["name"]
            if status is not None and invoice.status != status:
                continue
            texts = (name or "", invoice.invoice_number or "")
            if query and not any(query.lower() in text.lower() for text in texts):
                continue
            entry = await FakeLedger(
                store=self.store,
            ).get_for_invoice(
                invoice_id=invoice.id,
            )
            lines = (
                invoice.corrections["lines"]
                if invoice.corrections
                else invoice.extracted["items"]
            )
            rows.append(
                InvoiceRow(
                    invoice=invoice,
                    supplier_name=name,
                    retail_total=entry.amount if entry else None,
                    lines=len(
                        lines,
                    ),
                ),
            )
        return rows[offset : offset + limit]

    async def get_confirmed(
        self,
        invoice_id: int,
    ) -> Invoice | None:
        invoice = self.store.invoices.get(
            invoice_id,
        )
        if (
            invoice is None
            or invoice.status != InvoiceStatus.CONFIRMED
            or invoice.supplier_id is None
        ):
            return None
        # what selectinload brings in the real repository
        invoice.supplier = self.store.suppliers[invoice.supplier_id]
        items = [item for item in self.store.items if item.invoice_id == invoice.id]
        for item in items:
            item.product = self.store.products[item.product_id]
        invoice.items = items
        return invoice

    async def flush(self) -> None:
        pass

    async def add_items(
        self,
        items: list[InvoiceItem],
    ) -> None:
        self.store.items += items

    async def commit(self) -> None:
        self.store.commits += 1


class FakeSuppliers:
    def __init__(
        self,
        store: FakeStore,
    ) -> None:
        self.store = store

    async def get(
        self,
        supplier_id: int,
    ) -> Supplier | None:
        return self.store.suppliers.get(
            supplier_id,
        )

    async def get_by_inn(
        self,
        inn: str,
    ) -> Supplier | None:
        for supplier in self.store.suppliers.values():
            if supplier.inn == inn:
                return supplier
        return None

    async def search_by_name(
        self,
        name: str,
        only_without_inn: bool,
        limit: int,
    ) -> list[Supplier]:
        return [
            supplier
            for supplier in self.store.suppliers.values()
            if name.lower() in supplier.name.lower()
            and not (only_without_inn and supplier.inn is not None)
        ][:limit]

    async def search(
        self,
        query: str | None,
        limit: int,
    ) -> list[Supplier]:
        found = [
            supplier
            for supplier in self.store.suppliers.values()
            if not query
            or query.lower() in supplier.name.lower()
            or (
                query.isdigit()
                and supplier.inn is not None
                and supplier.inn.startswith(
                    query,
                )
            )
        ]
        found.sort(
            key=lambda supplier: (supplier.name, supplier.id),
        )
        return found[:limit]

    async def rank_by_aliases(
        self,
        aliases: Collection[str],
        only_without_inn: bool,
        limit: int,
    ) -> list[tuple[Supplier, int]]:
        ranked = []
        for supplier in self.store.suppliers.values():
            if only_without_inn and supplier.inn is not None:
                continue
            matched = {
                alias.alias_normalized
                for alias in self.store.aliases
                if alias.supplier_id == supplier.id
                and alias.alias_normalized in aliases
            }
            if matched:
                ranked.append(
                    (supplier, len(matched)),
                )
        ranked.sort(
            key=lambda row: -row[1],
        )
        return ranked[:limit]

    async def create(
        self,
        supplier: Supplier,
    ) -> Supplier:
        supplier.id = self.store.new_id()
        self.store.suppliers[supplier.id] = supplier
        return supplier


class FakeProducts:
    def __init__(
        self,
        store: FakeStore,
    ) -> None:
        self.store = store

    async def get(
        self,
        product_id: int,
    ) -> Product | None:
        return self.store.products.get(
            product_id,
        )

    async def create(
        self,
        product: Product,
    ) -> Product:
        product.id = self.store.new_id()
        self.store.products[product.id] = product
        return product

    async def add_alias(
        self,
        alias: ProductAlias,
    ) -> ProductAlias:
        alias.id = self.store.new_id()
        self.store.aliases.append(
            alias,
        )
        return alias

    async def find_by_aliases(
        self,
        supplier_id: int,
        aliases: Collection[str],
    ) -> dict[str, Product]:
        return {
            alias.alias_normalized: self.store.products[alias.product_id]
            for alias in self.store.aliases
            if alias.supplier_id == supplier_id and alias.alias_normalized in aliases
        }

    async def aliases_of(
        self,
        supplier_id: int,
    ) -> list[tuple[str, Product]]:
        return [
            (alias.alias_normalized, self.store.products[alias.product_id])
            for alias in self.store.aliases
            if alias.supplier_id == supplier_id
        ]

    async def search(
        self,
        supplier_id: int,
        query: str | None,
        key: str | None,
        limit: int,
    ) -> list[ProductRow]:
        found = [
            product
            for product in self.store.products.values()
            if product.supplier_id == supplier_id
            and (
                not query
                or query.lower() in product.name.lower()
                or any(
                    key is not None and key in alias.alias_normalized
                    for alias in self.store.aliases
                    if alias.product_id == product.id
                )
            )
        ]
        found.sort(
            key=lambda product: (product.name, product.id),
        )
        return [
            ProductRow(
                product=product,
                # items are appended as invoices are posted, the last one is the newest
                last_item=next(
                    (
                        item
                        for item in reversed(self.store.items)
                        if item.product_id == product.id
                    ),
                    None,
                ),
            )
            for product in found[:limit]
        ]


class FakeLedger:
    def __init__(
        self,
        store: FakeStore,
    ) -> None:
        self.store = store

    async def commit(self) -> None:
        self.store.commits += 1

    async def lock(self) -> None:
        self.store.locks += 1
        self.store.events.append(
            "lock",
        )

    async def create(
        self,
        entry: LedgerEntry,
    ) -> LedgerEntry:
        entry.id = self.store.new_id()
        # the column default is applied on flush, there is none here
        if entry.occurred_at is None:
            entry.occurred_at = datetime.now(
                tz=UTC,
            )
        self.store.entries.append(
            entry,
        )
        return entry

    async def get_for_invoice(
        self,
        invoice_id: int,
    ) -> LedgerEntry | None:
        for entry in self.store.entries:
            if entry.invoice_id == invoice_id:
                return entry
        return None

    async def balance(
        self,
    ) -> Decimal:
        return sum(
            (entry.amount for entry in self.store.entries),
            start=Decimal(
                value=0,
            ),
        )


class InvoiceApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.store = FakeStore()
        app.dependency_overrides[InvoiceRepository] = lambda: FakeInvoices(
            store=self.store,
        )
        app.dependency_overrides[SupplierRepository] = lambda: FakeSuppliers(
            store=self.store,
        )
        app.dependency_overrides[ProductRepository] = lambda: FakeProducts(
            store=self.store,
        )
        app.dependency_overrides[LedgerRepository] = lambda: FakeLedger(
            store=self.store,
        )
        self.addCleanup(
            app.dependency_overrides.clear,
        )
        self.client = TestClient(
            app=app,
        )
        self.addCleanup(
            self.client.close,
        )

    def upload(
        self,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self.client.post(
            url="/invoice",
            json=payload or invoice_payload(),
        )
        self.assertEqual(
            first=response.status_code,
            second=200,
        )
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
        self.assertEqual(
            first=response.status_code,
            second=200,
            msg=response.text,
        )
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


class ReceiveInvoiceTests(InvoiceApiTestCase):
    def test_initial_form_is_built_from_the_extraction(self) -> None:
        draft = self.upload()

        self.assertEqual(
            first=draft["form"],
            second={
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
                    },
                ],
            },
        )
        self.assertEqual(
            first=draft["extraction"],
            second=invoice_payload(),
        )
        invoice = self.store.invoices[draft["id"]]
        self.assertEqual(
            first=invoice.corrections,
            second={},
        )
        self.assertEqual(
            first=invoice.extracted,
            second=invoice_payload(),
        )
        self.assertEqual(
            first=self.store.commits,
            second=1,
        )

    def test_unknown_supplier_is_offered_as_a_new_one(self) -> None:
        draft = self.upload()

        self.assertEqual(
            first=self.blocking(
                draft=draft,
            ),
            second=[
                (1, "новый товар, укажите розничную цену"),
                (2, "новый товар, укажите розничную цену"),
            ],
        )
        self.assertIsNone(
            obj=draft["supplier"],
        )
        # nothing is written until the invoice is confirmed
        self.assertEqual(
            first=(self.store.suppliers, self.store.invoices[draft["id"]].supplier_id),
            second=({}, None),
        )

    def test_supplier_without_a_name_is_not_chosen(self) -> None:
        payload = invoice_payload()
        payload["supplier"] = {"name": None, "inn": INN}

        draft = self.upload(
            payload=payload,
        )

        self.assertIsNone(
            obj=draft["form"]["supplier"],
        )
        # the products may still be found once the supplier is chosen
        self.assertEqual(
            first=self.blocking(
                draft=draft,
            ),
            second=[(None, "продавец не выбран")],
        )
        self.assertEqual(
            first=[line["new_product"] for line in draft["lines"]],
            second=[False, False],
        )

    def test_new_supplier_alike_an_existing_one_is_a_warning(self) -> None:
        existing = self.store.add_supplier(
            name="ООО «Поставщик»",
            inn=None,
        )

        draft = self.upload()

        self.assertEqual(
            first=[candidate["id"] for candidate in draft["supplier_candidates"]],
            second=[existing.id],
        )
        self.assertIn(
            member={
                "line": None,
                "message": "похожий продавец уже есть в базе, проверьте, не он ли это",
                "blocking": False,
                "code": None,
            },
            container=draft["issues"],
        )

    def test_new_supplier_has_only_new_products(self) -> None:
        draft = self.upload()
        form = draft["form"]
        form["supplier"] = {"name": "ООО «Поставщик»", "inn": None}

        draft = self.save(
            draft=draft,
            form=form,
        )

        self.assertEqual(
            first=self.blocking(
                draft=draft,
            ),
            second=[
                (1, "новый товар, укажите розничную цену"),
                (2, "новый товар, укажите розничную цену"),
            ],
        )
        self.assertEqual(
            first=[line["new_product"] for line in draft["lines"]],
            second=[True, True],
        )

    def test_known_supplier_and_products_make_it_ready(self) -> None:
        supplier, sugar, salt = self.known_supplier()

        draft = self.upload()

        self.assertTrue(
            expr=draft["ready"],
            msg=draft["issues"],
        )
        self.assertEqual(
            first=draft["form"]["supplier"],
            second={"id": supplier.id},
        )
        self.assertEqual(
            first=draft["supplier"],
            second={"id": supplier.id, "name": supplier.name, "inn": supplier.inn},
        )
        self.assertEqual(
            first=[
                (line["product_id"], line["markup_pct"], line["retail_price"])
                for line in draft["lines"]
            ],
            second=[(sugar.id, "30", "65"), (salt.id, "20", "36")],
        )
        self.assertEqual(
            first=draft["totals"],
            second={
                "base_total": "155.00",
                "cost_total": "155.00",
                "retail_total": "198.50",
            },
        )
        self.assertEqual(
            first=self.store.invoices[draft["id"]].supplier_id,
            second=supplier.id,
        )

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

        self.assertEqual(
            first=[
                (candidate["id"], candidate["matched_lines"])
                for candidate in draft["supplier_candidates"]
            ],
            second=[(by_aliases.id, 1), (by_name.id, 0)],
        )

    def test_untouched_draft_picks_up_a_supplier_added_later(self) -> None:
        draft = self.upload()
        supplier, _, _ = self.known_supplier()

        response = self.client.get(
            url=f"/invoice/{draft['id']}",
        )

        self.assertEqual(
            first=response.status_code,
            second=200,
        )
        self.assertEqual(
            first=response.json()["form"]["supplier"],
            second={"id": supplier.id},
        )
        self.assertTrue(
            expr=response.json()["ready"],
        )

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

        self.assertEqual(
            first=response.json()["id"],
            second=42,
        )
        await_args = receive_invoice.await_args
        assert await_args is not None
        service = await_args.args[0]
        for repository in (
            service.invoices,
            service.suppliers,
            service.products,
            service.ledger,
        ):
            self.assertIs(
                expr1=repository.session,
                expr2=session,
            )
        receive_invoice.assert_awaited_once_with(
            service,
            invoice=invoice,
            extracted=payload,
        )

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

        self.assertEqual(
            first=draft["extraction"],
            second=payload,
        )
        self.assertEqual(
            first=self.blocking(
                draft=draft,
            ),
            second=[
                (None, "номер накладной не указан"),
                (None, "дата накладной не указана"),
                (None, "продавец не выбран"),
                (None, "в накладной нет строк"),
            ],
        )

    def test_accepts_null_in_every_item_field(self) -> None:
        payload = invoice_payload()
        payload["items"][0] = dict.fromkeys(
            payload["items"][0],
        )
        draft = self.upload(
            payload=payload,
        )

        self.assertEqual(
            first=draft["extraction"],
            second=payload,
        )

    def test_requires_every_key_and_forbids_extra_keys(self) -> None:
        for scope in ("root", "supplier", "item", "totals"):
            for field in (*self.scopes(payload=invoice_payload())[scope], "unexpected"):
                with self.subTest(
                    scope=scope,
                    field=field,
                ):
                    payload = invoice_payload()
                    target = self.scopes(
                        payload=payload,
                    )[scope]
                    if field == "unexpected":
                        target[field] = None
                    else:
                        del target[field]

                    response = self.client.post(
                        url="/invoice",
                        json=payload,
                    )

                    self.assertEqual(
                        first=response.status_code,
                        second=422,
                    )
        self.assertEqual(
            first=self.store.invoices,
            second={},
        )

    def test_rejects_invalid_values(self) -> None:
        cases = [
            ("root", "supplier", None),
            ("root", "totals", None),
            ("root", "items", None),
            ("root", "items", [None]),
            ("root", "items", {}),
            ("root", "invoice_number", 42),
            ("root", "invoice_number", ""),
            ("root", "invoice_date", "2026-08-12"),
            ("root", "invoice_date", "5-08-2026"),
            ("root", "invoice_date", "31-02-2026"),
            ("root", "invoice_date", "29-02-2025"),
            ("root", "invoice_date", 1786492800),
            ("supplier", "inn", "770123456"),
            ("supplier", "inn", "77012345601"),
            ("supplier", "inn", "7701234560\n"),
            ("supplier", "inn", 7701234560),
            ("supplier", "name", "   "),
            ("item", "line_no", "0"),
            ("item", "line_no", "-1"),
            ("item", "line_no", "1.5"),
            ("item", "line_no", "2147483648"),
            ("item", "line_no", 1),
            ("item", "name", True),
            ("item", "quantity", "0"),
            ("item", "quantity", "-1"),
            ("item", "quantity", "0.0001"),
            ("item", "quantity", "1000000000"),
            ("item", "quantity", 2.5),
            ("item", "unit", ""),
            ("item", "base_price", "-1"),
            ("item", "base_price", "50,00"),
            ("item", "base_price", "1 000.00"),
            ("item", "base_price", "1e2"),
            ("item", "base_price", "NaN"),
            ("item", "base_price", "Infinity"),
            ("item", "base_price", "0.001"),
            ("item", "base_price", "1000000000000"),
            ("item", "cost_price", True),
            ("item", "cost_price_total", 125),
            ("item", "vat_percent", "-1"),
            ("item", "vat_percent", "100.01"),
            ("item", "vat_percent", "0.001"),
            ("totals", "base_total", "-1"),
            ("totals", "cost_total", "NaN"),
        ]
        for scope, field, value in cases:
            with self.subTest(
                scope=scope,
                field=field,
                value=value,
            ):
                payload = invoice_payload()
                self.scopes(
                    payload=payload,
                )[scope][field] = value
                response = self.client.post(
                    url="/invoice",
                    json=payload,
                )

                self.assertEqual(
                    first=response.status_code,
                    second=422,
                )

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

        self.assertEqual(
            first=draft["extraction"],
            second=payload,
        )

    def test_rejects_malformed_json(self) -> None:
        response = self.client.post(
            url="/invoice",
            content="{",
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(
            first=response.status_code,
            second=422,
        )

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


class RecognizeImageTests(InvoiceApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        enabled = patch.object(
            target=settings,
            attribute="include_api_openai",
            new=True,
        )
        enabled.start()
        self.addCleanup(
            enabled.stop,
        )

    def test_turned_off_recognition_does_not_call_openai(self) -> None:
        settings.include_api_openai = False

        response, extract = self.post_images(
            files=[
                ("files", ("page.jpg", b"page", "image/jpeg")),
            ],
            extracted=invoice_payload(),
        )

        self.assertEqual(
            first=response.status_code,
            second=503,
        )
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

        self.assertEqual(
            first=response.status_code,
            second=200,
            msg=response.text,
        )
        call = extract.await_args
        assert call is not None
        images = call.kwargs["images"]
        self.assertEqual(
            first=[(image.content, image.media_type) for image in images],
            second=[(b"first", "image/jpeg"), (b"second", "image/png")],
        )
        draft = response.json()
        self.assertEqual(
            first=self.store.invoices[draft["id"]].extracted,
            second=invoice_payload(),
        )

    def test_rejects_a_file_that_is_not_an_image(self) -> None:
        response, extract = self.post_images(
            files=[
                ("files", ("invoice.pdf", b"%PDF", "application/pdf")),
            ],
            extracted=invoice_payload(),
        )

        self.assertEqual(
            first=response.status_code,
            second=422,
        )
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

        self.assertEqual(
            first=response.status_code,
            second=422,
        )
        self.assertEqual(
            first=[error["loc"] for error in response.json()["detail"]],
            second=[["body", "invoice_date"]],
        )
        self.assertEqual(
            first=self.store.invoices,
            second={},
        )


class SaveFormTests(InvoiceApiTestCase):
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

        self.assertTrue(
            expr=draft["ready"],
            msg=draft["issues"],
        )
        self.assertEqual(
            first=[
                (line["new_product"], line["markup_pct"], line["retail_price"])
                for line in draft["lines"]
            ],
            second=[(True, "30.00", "65"), (True, "33.33", "40")],
        )
        self.assertEqual(
            first=draft["form"],
            second=form,
        )
        self.assertEqual(
            first=(self.store.suppliers, self.store.products, self.store.aliases),
            second=({}, {}, []),
        )
        invoice = self.store.invoices[draft["id"]]
        self.assertEqual(
            first=invoice.corrections,
            second=form,
        )
        self.assertEqual(
            first=invoice.extracted,
            second=invoice_payload(),
        )

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
        self.assertEqual(
            first=(invoice.invoice_number, invoice.invoice_date, invoice.supplier_id),
            second=(
                "43",
                date(
                    year=2026,
                    month=8,
                    day=13,
                ),
                supplier.id,
            ),
        )

        form["supplier"] = {"name": "Другой", "inn": None}
        self.save(
            draft=draft,
            form=form,
        )
        self.assertIsNone(
            obj=invoice.supplier_id,
        )

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

        self.assertEqual(
            first=[
                (
                    line["cost_price"],
                    line["base_price_total"],
                    line["retail_price"],
                )
                for line in draft["lines"]
            ],
            second=[("60.00", "150.00", "78"), ("30.00", "25.00", "36")],
        )
        # what the model read disagrees now, which is only worth a look
        self.assertTrue(
            expr=draft["ready"],
        )
        self.assertEqual(
            first=[issue["message"] for issue in draft["issues"]],
            second=[
                "сумма без НДС: в накладной 125.00, по сумме строки 150.00",
                "цена за единицу: в накладной 50.00, по сумме строки 60.00",
                "цена без НДС: в накладной 50.00, по сумме строки 60.00",
                "сумма без НДС: в накладной 30.00, по сумме строки 25.00",
                "итог к оплате: в накладной 155.00, по строкам 180.00",
                "итог без НДС: в накладной 155.00, по строкам 175.00",
            ],
        )

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

        self.assertEqual(
            first=draft["issues"],
            second=[],
        )
        self.assertEqual(
            first=[
                (line["product_name"], line["new_product"]) for line in draft["lines"]
            ],
            second=[("Соль", False), ("Перец", True)],
        )

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

        self.assertEqual(
            first=(
                draft["lines"][0]["product_id"],
                draft["lines"][0]["product_name"],
                draft["lines"][0]["retail_price"],
            ),
            second=(sugar.id, "Сахар-песок 1 кг", "65"),
        )
        self.assertTrue(
            expr=draft["ready"],
        )

    def test_blocking_problems(self) -> None:
        supplier, sugar, salt = self.known_supplier()
        stranger = self.store.add_supplier(
            name="Чужой",
            inn=None,
        )
        foreign = self.store.add_product(
            supplier=stranger,
            name="Чужой товар",
            markup_pct="10",
            retail_price="100",
        )
        cases = [
            (
                {"supplier": {"id": 999}},
                [(None, "продавца с id 999 нет")],
            ),
            (
                {"supplier": {"name": "Двойник", "inn": INN}},
                [(None, f"продавец с ИНН {INN} уже есть, выберите его")],
            ),
            (
                {"invoice_number": None},
                [(None, "номер накладной не указан")],
            ),
            (
                {"line": {"quantity": None}},
                [(1, "количество не указано")],
            ),
            (
                {"line": {"name": None}},
                [(1, "название не указано")],
            ),
            (
                {"line": {"name": "Новинка"}},
                [(1, "новый товар, укажите розничную цену")],
            ),
            (
                {"line": {"product_id": foreign.id}},
                [(1, f"у продавца нет товара с id {foreign.id}")],
            ),
            (
                {"line": {"product_id": salt.id}},
                [(1, f"это название уже относится к товару «{sugar.name}»")],
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
            ),
            (
                {"line": {"cost_price_total": "0.00", "retail_price": 40}},
                [(1, "нет закупочной цены, наценку посчитать не из чего")],
            ),
            (
                {
                    "second": {"name": "Сахар-песок 1 кг", "retail_price": 70},
                    "line": {"retail_price": 66},
                },
                [(2, "у этого товара уже задана другая цена в строке 1")],
            ),
        ]
        draft = self.upload()
        for change, problems in cases:
            with self.subTest(
                change=change,
            ):
                form = draft["form"] | {
                    key: value
                    for key, value in change.items()
                    if key not in ("line", "second")
                }
                form["lines"] = [
                    form["lines"][0] | change.get("line", {}),
                    form["lines"][1] | change.get("second", {}),
                ]
                saved = self.save(
                    draft=draft,
                    form=form,
                )

                self.assertEqual(
                    first=self.blocking(
                        draft=saved,
                    ),
                    second=problems,
                )
                self.assertFalse(
                    expr=saved["ready"],
                )
        self.assertEqual(
            first=supplier.id,
            second=self.store.invoices[draft["id"]].supplier_id,
        )

    def test_rejects_invalid_form(self) -> None:
        draft = self.upload()
        for change in (
            {"lines": [draft["form"]["lines"][0] | {"cost_price": "50.00"}]},
            {"lines": [{"name": "Без остальных полей"}]},
            {"supplier": {"id": 0}},
            {"supplier": {"id": 1, "name": "И то и другое", "inn": None}},
            {"invoice_date": "2026-08-12"},
            {"lines": [draft["form"]["lines"][0] | {"retail_price": 0}]},
            {"lines": [draft["form"]["lines"][0] | {"quantity": 2}]},
            {"status": "confirmed"},
        ):
            with self.subTest(
                change=change,
            ):
                response = self.client.put(
                    url=f"/invoice/{draft['id']}",
                    json=draft["form"] | change,
                )

                self.assertEqual(
                    first=response.status_code,
                    second=422,
                )
        self.assertEqual(
            first=self.store.invoices[draft["id"]].corrections,
            second={},
        )

    def test_only_drafts(self) -> None:
        draft = self.upload()
        self.store.invoices[draft["id"]].status = InvoiceStatus.DECLINED
        for method in ("GET", "PUT"):
            with self.subTest(
                method=method,
            ):
                response = self.client.request(
                    method=method,
                    url=f"/invoice/{draft['id']}",
                    json=draft["form"] if method == "PUT" else None,
                )

                self.assertEqual(
                    first=response.status_code,
                    second=404,
                )


class ConfirmTests(InvoiceApiTestCase):
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

        self.assertEqual(
            first=response.status_code,
            second=200,
            msg=response.text,
        )
        [supplier] = self.store.suppliers.values()
        self.assertEqual(
            first=(supplier.name, supplier.inn),
            second=("ООО «Поставщик»", INN),
        )
        sugar, salt = self.store.products.values()
        self.assertEqual(
            first=[
                (product.supplier_id, product.name, product.markup_pct)
                for product in (sugar, salt)
            ],
            second=[
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
            ],
        )
        self.assertEqual(
            first=[(alias.product_id, alias.alias_raw) for alias in self.store.aliases],
            second=[(sugar.id, "Сахар-песок 1 кг"), (salt.id, "Соль")],
        )
        self.assertEqual(
            first=[
                (item.line_no, item.product_id, str(item.retail_price))
                for item in self.store.items
            ],
            second=[(1, sugar.id, "65"), (2, salt.id, "40"), (3, sugar.id, "65")],
        )
        [entry] = self.store.entries
        self.assertEqual(
            first=(entry.kind, entry.amount, entry.invoice_status),
            second=(
                LedgerKind.INVOICE,
                Decimal(
                    value="365.00",
                ),
                InvoiceStatus.CONFIRMED,
            ),
        )
        invoice = self.store.invoices[draft["id"]]
        self.assertEqual(
            first=(invoice.status, invoice.supplier_id),
            second=(InvoiceStatus.CONFIRMED, supplier.id),
        )
        self.assertEqual(
            first=response.json(),
            second={
                "id": draft["id"],
                "ledger_entry_id": entry.id,
                "retail_total": "365.00",
                "balance": "365.00",
            },
        )

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

        self.assertEqual(
            first=response.status_code,
            second=200,
            msg=response.text,
        )
        self.assertEqual(
            first=(sugar.markup_pct, salt.markup_pct),
            second=(
                Decimal(
                    value=30,
                ),
                Decimal(
                    value="50.00",
                ),
            ),
        )
        self.assertEqual(
            first=len(self.store.aliases),
            second=2,
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

        self.assertEqual(
            first=response.status_code,
            second=200,
            msg=response.text,
        )
        self.assertEqual(
            first=(self.store.aliases[-1].product_id, self.store.aliases[-1].alias_raw),
            second=(sugar.id, "Сахар 1кг"),
        )
        self.assertEqual(
            first=self.store.items[0].name,
            second="Сахар 1кг",
        )

    def test_not_ready_draft_is_not_posted(self) -> None:
        draft = self.upload()

        response = self.confirm(
            draft=draft,
        )

        self.assertEqual(
            first=response.status_code,
            second=409,
        )
        self.assertEqual(
            first=response.json()["detail"],
            second=(
                "Провести нельзя: строка 1: новый товар, укажите розничную цену; "
                "строка 2: новый товар, укажите розничную цену"
            ),
        )
        self.assertEqual(
            first=(self.store.items, self.store.entries, self.store.commits),
            second=([], [], 1),
        )

    def test_ledger_is_locked_before_the_draft_is_read(self) -> None:
        self.known_supplier()
        draft = self.upload()
        self.store.events.clear()

        response = self.confirm(
            draft=draft,
        )

        self.assertEqual(
            first=response.status_code,
            second=200,
            msg=response.text,
        )
        self.assertEqual(
            first=self.store.events,
            second=["lock", "get_draft"],
        )

    def test_invoice_confirmed_before_is_blocking(self) -> None:
        self.known_supplier()
        first = self.upload()
        self.assertEqual(
            first=self.confirm(
                draft=first,
            ).status_code,
            second=200,
        )

        second = self.upload()

        self.assertEqual(
            first=self.blocking(
                draft=second,
            ),
            second=[(None, f"эта накладная уже проведена под номером {first['id']}")],
        )
        self.assertEqual(
            first=self.confirm(
                draft=second,
            ).status_code,
            second=409,
        )

    def test_decline(self) -> None:
        draft = self.upload()

        response = self.client.post(
            url=f"/invoice/{draft['id']}/decline",
        )

        self.assertEqual(
            first=response.status_code,
            second=204,
        )
        self.assertEqual(
            first=self.store.invoices[draft["id"]].status,
            second=InvoiceStatus.DECLINED,
        )
        for url in (
            f"/invoice/{draft['id']}/decline",
            f"/invoice/{draft['id']}/confirm",
        ):
            with self.subTest(
                url=url,
            ):
                self.assertEqual(
                    first=self.client.post(
                        url=url,
                    ).status_code,
                    second=404,
                )


class InvoiceListTests(InvoiceApiTestCase):
    def confirmed(self) -> dict[str, Any]:
        """an invoice of the known supplier, posted at the current markups"""
        self.known_supplier()
        draft = self.upload()
        response = self.client.post(
            url=f"/invoice/{draft['id']}/confirm",
        )
        self.assertEqual(
            first=response.status_code,
            second=200,
            msg=response.text,
        )
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

        self.assertEqual(
            first=[
                (
                    item["id"],
                    item["status"],
                    item["supplier_name"],
                    item["retail_total"],
                    item["lines"],
                )
                for item in everything["items"]
            ],
            second=[
                (draft["id"], "draft", "ИП Иванов", None, 2),
                (posted["id"], "confirmed", "ООО «Поставщик»", "198.50", 2),
            ],
        )
        self.assertEqual(
            first=[item["id"] for item in confirmed["items"]],
            second=[posted["id"]],
        )
        self.assertEqual(
            first=[item["id"] for item in found["items"]],
            second=[draft["id"]],
        )
        self.assertEqual(
            first=(
                [item["id"] for item in first_page["items"]],
                first_page["has_more"],
            ),
            second=([draft["id"]], True),
        )

    def test_posted_invoice_shows_the_lines_as_posted(self) -> None:
        draft = self.confirmed()

        response = self.client.get(
            url=f"/invoice/{draft['id']}/confirmed",
        )

        self.assertEqual(
            first=response.status_code,
            second=200,
            msg=response.text,
        )
        posted = response.json()
        self.assertEqual(
            first=(
                posted["invoice_number"],
                posted["invoice_date"],
                posted["supplier"]["name"],
                posted["cost_total"],
                posted["retail_total"],
                posted["ledger_entry_id"],
            ),
            second=(
                "00042/А",
                "12-08-2026",
                "ООО «Поставщик»",
                "155.00",
                "198.50",
                self.store.entries[0].id,
            ),
        )
        self.assertEqual(
            # compared as numbers, the database pads the scale and the fake store does not
            first=[
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
            ],
            second=[
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
            ],
        )
        self.assertEqual(
            first=self.store.locks,
            second=1,
        )

    def test_draft_is_not_a_posted_invoice(self) -> None:
        draft = self.upload()

        self.assertEqual(
            first=self.client.get(
                url=f"/invoice/{draft['id']}/confirmed",
            ).status_code,
            second=404,
        )


class SimilarProductTests(InvoiceApiTestCase):
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

        self.assertEqual(
            first=[line["similar"] for line in draft["lines"]],
            second=[
                [{"id": sugar.id, "name": "Сахар-песок 1 кг", "similarity": 96}],
                [],
            ],
        )
        self.assertEqual(
            first=self.similar_issues(
                draft=draft,
            ),
            second=[
                {
                    "line": 1,
                    "message": "похож на товар «Сахар-песок 1 кг» (96%), проверьте, не он ли это",
                    "blocking": False,
                    "code": "similar_product",
                },
            ],
        )
        # nothing is decided for the user, both lines are new until a price or a link is set
        self.assertEqual(
            first=self.blocking(
                draft=draft,
            ),
            second=[
                (1, "новый товар, укажите розничную цену"),
                (2, "новый товар, укажите розничную цену"),
            ],
        )

    def test_known_and_linked_lines_are_not_compared(self) -> None:
        _, _, salt = self.known_supplier()
        draft = self.upload()
        self.assertEqual(
            first=[line["similar"] for line in draft["lines"]],
            second=[[], []],
        )

        draft = self.upload_misread()
        form = draft["form"]
        form["lines"][0]["product_id"] = salt.id
        draft = self.save(
            draft=draft,
            form=form,
        )

        self.assertEqual(
            first=(draft["lines"][0]["similar"], self.similar_issues(draft=draft)),
            second=([], []),
        )

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

        self.assertEqual(
            first=response.status_code,
            second=200,
            msg=response.text,
        )
        self.assertIn(
            member=(sugar.id, "сахар-песк 1 кг"),
            container=[
                (alias.product_id, alias.alias_normalized)
                for alias in self.store.aliases
            ],
        )


class SupplierSearchTests(InvoiceApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.petrov = self.store.add_supplier(
            name="ИП Петров",
            inn="471909695290",
        )
        self.dvor = self.store.add_supplier(
            name="ООО «Молочный двор»",
            inn="7707083893",
        )
        self.market = self.store.add_supplier(
            name="Агроторг",
            inn=None,
        )

    def search(
        self,
        params: dict[str, Any],
    ) -> list[int]:
        response = self.client.get(
            url="/supplier",
            params=params,
        )
        self.assertEqual(
            first=response.status_code,
            second=200,
            msg=response.text,
        )
        return [supplier["id"] for supplier in response.json()]

    def test_finds_by_a_part_of_the_name_in_any_case(self) -> None:
        self.assertEqual(
            first=self.search(
                params={"q": " молочный "},
            ),
            second=[self.dvor.id],
        )

    def test_finds_by_the_start_of_the_inn(self) -> None:
        response = self.client.get(
            url="/supplier",
            params={"q": "4719"},
        )

        self.assertEqual(
            first=response.json(),
            second=[{"id": self.petrov.id, "name": "ИП Петров", "inn": "471909695290"}],
        )

    def test_without_a_query_lists_everyone_by_name(self) -> None:
        self.assertEqual(
            first=self.search(
                params={},
            ),
            second=[self.market.id, self.petrov.id, self.dvor.id],
        )

    def test_limit(self) -> None:
        self.assertEqual(
            first=self.search(
                params={"limit": 2},
            ),
            second=[self.market.id, self.petrov.id],
        )


class ProductSearchTests(InvoiceApiTestCase):
    def search(
        self,
        supplier_id: int,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        response = self.client.get(
            url=f"/supplier/{supplier_id}/products",
            params=params,
        )
        self.assertEqual(
            first=response.status_code,
            second=200,
            msg=response.text,
        )
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

        self.assertEqual(
            first=self.search(
                supplier_id=supplier.id,
                params={},
            ),
            second=[
                {
                    "id": sugar.id,
                    "name": "Сахар-песок 1 кг",
                    "markup_pct": "30",
                    "unit": None,
                    "vat_percent": None,
                    "cost_price": None,
                    "retail_price": None,
                },
                {
                    "id": salt.id,
                    "name": "Соль",
                    "markup_pct": "20",
                    "unit": None,
                    "vat_percent": None,
                    "cost_price": None,
                    "retail_price": None,
                },
            ],
        )

    def test_finds_by_a_part_of_the_name_or_of_another_spelling(self) -> None:
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

        for query in ("САХ", 'песок "русский"'):
            with self.subTest(
                query=query,
            ):
                self.assertEqual(
                    first=[
                        product["id"]
                        for product in self.search(
                            supplier_id=supplier.id,
                            params={"q": query},
                        )
                    ],
                    second=[sugar.id],
                )

    def test_shows_the_last_posted_line(self) -> None:
        supplier, sugar, _ = self.known_supplier()
        draft = self.upload()
        self.assertEqual(
            first=self.client.post(
                url=f"/invoice/{draft['id']}/confirm",
            ).status_code,
            second=200,
        )

        found = self.search(
            supplier_id=supplier.id,
            params={"q": "сахар"},
        )

        self.assertEqual(
            first=found[0],
            second={
                "id": sugar.id,
                "name": "Сахар-песок 1 кг",
                "markup_pct": "30",
                "unit": "кг",
                "vat_percent": None,
                "cost_price": "50.00",
                "retail_price": "65",
            },
        )

    def test_unknown_supplier(self) -> None:
        response = self.client.get(
            url="/supplier/999/products",
        )

        self.assertEqual(
            first=response.status_code,
            second=404,
        )


if __name__ == "__main__":
    unittest.main()
