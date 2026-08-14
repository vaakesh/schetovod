import unittest
from collections.abc import AsyncIterator, Collection
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from enums import InvoiceStatus
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
            lines = invoice.extracted["items"]
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
