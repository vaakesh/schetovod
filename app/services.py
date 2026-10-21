from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from itertools import groupby
from typing import Annotated, NoReturn

from fastapi import Depends, HTTPException, status
from pydantic import JsonValue

from config import today
from enums import InvoiceSort, InvoiceStatus, LedgerKind
from models import (
    Invoice,
    InvoiceItem,
    InvoicePayment,
    LedgerEntry,
    Product,
    ProductAlias,
    RevaluationItem,
    Supplier,
)
from normalize import (
    LinePrices,
    check_read_prices,
    check_totals,
    line_prices,
    printed_cost_total_field,
    source_total_field,
    sum_known,
    to_kopecks,
)
from pricing import (
    MAX_MARKUP_PCT,
    SIMILAR_NAME_RATIO,
    markup_for_price,
    name_similarity,
    normalize_name,
    retail_price,
    retail_price_total,
    revaluation_amount,
)
from repositories import (
    InvoiceRepositoryDep,
    LedgerRepository,
    LedgerRepositoryDep,
    LedgerRow,
    ProductRepositoryDep,
    ProductRow,
    SupplierRepositoryDep,
)
from schemas import (
    MAX_LINE_NO,
    CashCountCreate,
    CashNote,
    CashOutCreate,
    Catalog,
    CatalogProduct,
    ConfirmedInvoice,
    DraftForm,
    DraftLine,
    DraftTotals,
    FormLine,
    InvoiceDraft,
    InvoiceExtraction,
    InvoiceItemExtraction,
    InvoiceList,
    InvoiceListItem,
    Issue,
    LedgerBalance,
    LedgerEntryOut,
    LedgerPage,
    LedgerPosted,
    LedgerReport,
    NewSupplier,
    OutflowCreate,
    PaymentCreate,
    PaymentOut,
    PeriodReport,
    PostedInvoice,
    PostedLine,
    PriceTagMark,
    ProductEdit,
    ProductSummary,
    ReportDay,
    ReportInvoice,
    RevaluationCreate,
    RevaluationLineOut,
    SaleCreate,
    SimilarProduct,
    StocktakeCreate,
    SupplierCandidate,
    SupplierDebt,
    SupplierEdit,
    SupplierRef,
    SupplierSummary,
    format_invoice_date,
)

CANDIDATES_LIMIT = 5
SIMILAR_LIMIT = 3
# the issue code of a line with a close catalog product
SIMILAR_PRODUCT = "similar_product"
# the issue code of a line that changes the shelf price of its product
PRICE_CHANGED = "price_changed"

# an existing product by id or a new one by its name key, lines with one key are one product
type ProductKey = tuple[str, int | str]


@dataclass
class PlannedLine:
    """a form line with what is derived from it and from the catalog"""

    # stable invoice line number, independent of the current array position
    position: int
    form: FormLine
    prices: LinePrices
    # rounded the way it is stored, the retail price is derived from it
    cost_price: Decimal | None
    alias: str | None
    # None for a product that is created on confirmation
    product: Product | None
    # the line name already leads to the product, there is no alias to add
    linked: bool
    key: ProductKey | None
    markup_pct: Decimal | None = None
    retail_price: Decimal | None = None
    retail_price_total: Decimal | None = None
    # the cost with VAT of the last delivery of the product when this line has another one
    previous_cost_price: Decimal | None = None
    # the shelf price of the product when this line changes it
    previous_retail_price: Decimal | None = None
    similar: list[SimilarProduct] = field(
        default_factory=list,
    )


@dataclass
class DraftPlan:
    """everything the draft shows and the confirmation writes"""

    form: DraftForm
    extraction: InvoiceExtraction
    # None while the supplier is new or not chosen
    supplier: Supplier | None
    lines: list[PlannedLine]
    candidates: list[SupplierCandidate]
    # the supplier is settled, so a line without a product is a new product indeed
    catalog_known: bool = False
    issues: list[Issue] = field(
        default_factory=list,
    )

    @property
    def ready(self) -> bool:
        return not any(issue.blocking for issue in self.issues)


class InvoiceService:
    def __init__(
        self,
        invoices: InvoiceRepositoryDep,
        suppliers: SupplierRepositoryDep,
        products: ProductRepositoryDep,
        ledger: LedgerRepositoryDep,
    ) -> None:
        self.invoices = invoices
        self.suppliers = suppliers
        self.products = products
        self.ledger = ledger

    async def receive_invoice(
        self,
        invoice: InvoiceExtraction,
        extracted: dict[str, JsonValue],
    ) -> InvoiceDraft:
        # only an exact inn match is trusted, a name may belong to someone else
        supplier = None
        if invoice.supplier.inn is not None:
            supplier = await self.suppliers.get_by_inn(
                inn=invoice.supplier.inn,
            )
        draft_invoice = await self.invoices.create(
            invoice=Invoice(
                supplier_id=supplier.id if supplier else None,
                invoice_number=invoice.invoice_number,
                invoice_date=invoice.invoice_date,
                status=InvoiceStatus.DRAFT,
                extracted=extracted,
                form=None,
            ),
        )
        draft = await self._draft(
            draft_invoice=draft_invoice,
        )
        await self.invoices.commit()
        return draft

    async def list_invoices(
        self,
        status: InvoiceStatus | None,
        unpaid: bool,
        query: str | None,
        sort: InvoiceSort,
        limit: int,
        offset: int,
    ) -> InvoiceList:
        # one row more tells whether there is another page
        rows = await self.invoices.search(
            status=status,
            unpaid=unpaid,
            query=query,
            sort=sort,
            limit=limit + 1,
            offset=offset,
        )
        return InvoiceList(
            items=[
                InvoiceListItem(
                    id=row.invoice.id,
                    status=row.invoice.status,
                    invoice_number=row.invoice.invoice_number,
                    invoice_date=row.invoice.invoice_date,
                    supplier_name=row.supplier_name,
                    retail_total=row.retail_total,
                    debt=(
                        None if row.cost_total is None else row.cost_total - row.paid
                    ),
                    lines=row.lines,
                    created_at=row.invoice.created_at,
                )
                for row in rows[:limit]
            ],
            has_more=len(rows) > limit,
        )

    async def get_posted(
        self,
        invoice_id: int,
    ) -> PostedInvoice:
        invoice = await self.invoices.get_confirmed(
            invoice_id=invoice_id,
        )
        entry = await self.ledger.get_for_invoice(
            invoice_id=invoice_id,
        )
        if invoice is None or entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Проведённая накладная не найдена",
            )
        supplier = invoice.supplier
        if (
            supplier is None
            or invoice.invoice_number is None
            or invoice.invoice_date is None
        ):
            raise RuntimeError(
                "a confirmed invoice has a supplier, a number and a date",
            )
        items = sorted(
            invoice.items,
            key=lambda item: item.id,
        )
        cost_total = sum(
            (item.cost_price_total for item in items),
            start=Decimal(
                value=0,
            ),
        )
        payments = await self.invoices.payments_of(
            invoice_id=invoice.id,
        )
        paid = sum(
            (payment.amount for payment in payments),
            start=Decimal(
                value=0,
            ),
        )
        return PostedInvoice(
            id=invoice.id,
            invoice_number=invoice.invoice_number,
            invoice_date=invoice.invoice_date,
            supplier=_supplier_summary(
                supplier=supplier,
            ),
            lines=[
                PostedLine(
                    line_no=item.line_no,
                    name=item.name,
                    product_name=item.product.name,
                    quantity=item.quantity,
                    unit=item.unit,
                    vat_percent=item.vat_percent,
                    base_price=item.base_price,
                    cost_price=item.cost_price,
                    cost_price_total=item.cost_price_total,
                    markup_pct=item.markup_pct,
                    retail_price=item.retail_price,
                    retail_price_total=retail_price_total(
                        retail_price=item.retail_price,
                        quantity=item.quantity,
                    ),
                )
                for item in items
            ],
            cost_total=cost_total,
            retail_total=entry.amount,
            ledger_entry_id=entry.id,
            paid=paid,
            debt=cost_total - paid,
            payments=[
                PaymentOut(
                    id=payment.id,
                    paid_on=payment.paid_on,
                    amount=payment.amount,
                    comment=payment.comment,
                )
                for payment in payments
            ],
        )

    async def add_payment(
        self,
        invoice_id: int,
        payload: PaymentCreate,
    ) -> PostedInvoice:
        """a part or the rest of what is owed to the supplier, the till is not touched"""
        invoice = await self.invoices.lock_confirmed(
            invoice_id=invoice_id,
        )
        if invoice is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Проведённая накладная не найдена",
            )
        if payload.paid_on > today():
            _invalid(
                detail="Дата оплаты не может быть в будущем",
            )
        cost_totals = await self.invoices.cost_totals(
            invoice_ids=[
                invoice.id,
            ],
        )
        paid_totals = await self.invoices.paid_totals(
            invoice_ids=[
                invoice.id,
            ],
            on=None,
        )
        zero = Decimal(
            value=0,
        )
        debt = cost_totals.get(
            invoice.id,
            zero,
        ) - paid_totals.get(
            invoice.id,
            zero,
        )
        if payload.amount > debt:
            _invalid(
                detail=f"Оплата больше долга по накладной, осталось {debt} ₽",
            )
        await self.invoices.add_payment(
            payment=InvoicePayment(
                invoice_id=invoice.id,
                paid_on=payload.paid_on,
                amount=payload.amount,
                comment=payload.comment,
            ),
        )
        await self.invoices.commit()
        return await self.get_posted(
            invoice_id=invoice.id,
        )

    async def delete_payment(
        self,
        invoice_id: int,
        payment_id: int,
    ) -> PostedInvoice:
        """a payment entered by mistake, nothing else depends on it"""
        payment = await self.invoices.get_payment(
            invoice_id=invoice_id,
            payment_id=payment_id,
        )
        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Оплата не найдена",
            )
        await self.invoices.delete_payment(
            payment=payment,
        )
        await self.invoices.commit()
        return await self.get_posted(
            invoice_id=invoice_id,
        )

    async def get_draft(
        self,
        invoice_id: int,
    ) -> InvoiceDraft:
        return await self._draft(
            draft_invoice=await self._get_draft(
                invoice_id=invoice_id,
            ),
        )

    async def save_form(
        self,
        invoice_id: int,
        form: DraftForm,
    ) -> InvoiceDraft:
        draft_invoice = await self._get_draft(
            invoice_id=invoice_id,
        )
        extraction = InvoiceExtraction.model_validate(
            obj=draft_invoice.extracted,
        )
        numbered_items = _numbered_extraction(
            extraction=extraction,
        )
        _number_form_lines(
            form=form,
            source_max=max(
                numbered_items,
                default=0,
            ),
        )
        draft_invoice.form = form.model_dump(
            mode="json",
        )
        # the columns behind the checks and the uniqueness of confirmed invoices follow the form
        draft_invoice.invoice_number = form.invoice_number
        draft_invoice.invoice_date = form.invoice_date
        supplier = None
        if isinstance(
            form.supplier,
            SupplierRef,
        ):
            supplier = await self.suppliers.get(
                supplier_id=form.supplier.id,
            )
        draft_invoice.supplier_id = supplier.id if supplier else None
        draft = await self._draft(
            draft_invoice=draft_invoice,
        )
        await self.invoices.commit()
        return draft

    async def confirm_invoice(
        self,
        invoice_id: int,
        occurred_on: date,
    ) -> ConfirmedInvoice:
        """writes the catalog changes, the lines and the inflow at retail prices"""
        # taken before the plan, so a concurrent confirmation of this invoice or of its copy
        # waits and then sees the posted one instead of hitting the unique keys
        await self.ledger.lock()
        draft_invoice = await self._get_draft(
            invoice_id=invoice_id,
        )
        # the day the goods came, it may be earlier than the confirmation
        await _check_date(
            ledger=self.ledger,
            on=occurred_on,
            stock=True,
            cash=False,
        )
        plan = await self._plan(
            draft_invoice=draft_invoice,
        )
        retail_total = sum_known(
            values=(line.retail_price_total for line in plan.lines),
        )
        if not plan.ready or retail_total is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Провести нельзя: "
                + "; ".join(
                    _issue_text(
                        issue=issue,
                    )
                    for issue in plan.issues
                    if issue.blocking
                ),
            )

        supplier = plan.supplier
        if supplier is None:
            if not isinstance(
                plan.form.supplier,
                NewSupplier,
            ):
                raise RuntimeError(
                    "a ready draft has a supplier",
                )
            supplier = await self.suppliers.create(
                supplier=Supplier(
                    name=plan.form.supplier.name,
                    inn=plan.form.supplier.inn,
                ),
            )
        draft_invoice.supplier_id = supplier.id
        draft_invoice.invoice_number = plan.form.invoice_number
        draft_invoice.invoice_date = plan.form.invoice_date

        products: dict[ProductKey, Product] = {}
        added_aliases: set[str] = set()
        items: list[InvoiceItem] = []
        # with the shelf price before this invoice, the product gets the new one below
        revalued: list[tuple[PlannedLine, Product, InvoiceItem, Decimal]] = []
        for line in plan.lines:
            if line.alias is None or line.form.name is None:
                raise RuntimeError(
                    "a ready draft has a name for every line",
                )
            product = await self._posted_product(
                supplier=supplier,
                line=line,
                products=products,
            )
            if not line.linked and line.alias not in added_aliases:
                await self.products.add_alias(
                    alias=ProductAlias(
                        product_id=product.id,
                        supplier_id=supplier.id,
                        alias_normalized=line.alias,
                        alias_raw=line.form.name,
                    ),
                )
                added_aliases.add(
                    line.alias,
                )
            item = _invoice_item(
                draft_invoice=draft_invoice,
                line=line,
                product=product,
            )
            items.append(
                item,
            )
            if line.form.revalue_quantity is not None:
                # planned before any line of the invoice updated the product
                if line.previous_retail_price is None:
                    raise RuntimeError(
                        "a ready draft revalues only a changed price",
                    )
                revalued.append(
                    (line, product, item, line.previous_retail_price),
                )

        # the ledger entry may only point to a confirmed invoice, so the status goes first
        draft_invoice.status = InvoiceStatus.CONFIRMED
        await self.invoices.flush()
        await self.invoices.add_items(
            items=items,
        )
        entry = await self.ledger.create(
            entry=LedgerEntry(
                kind=LedgerKind.INVOICE,
                occurred_on=occurred_on,
                amount=retail_total,
                invoice_id=draft_invoice.id,
                invoice_status=InvoiceStatus.CONFIRMED,
            ),
        )
        revaluation = await self._revalue(
            revalued=revalued,
            invoice_number=plan.form.invoice_number,
            occurred_on=occurred_on,
        )
        balance = await self.ledger.balance()
        await self.invoices.commit()
        return ConfirmedInvoice(
            id=draft_invoice.id,
            ledger_entry_id=entry.id,
            retail_total=retail_total,
            revaluation=revaluation,
            balance=balance,
        )

    async def _revalue(
        self,
        revalued: list[tuple[PlannedLine, Product, InvoiceItem, Decimal]],
        invoice_number: str | None,
        occurred_on: date,
    ) -> Decimal | None:
        """the old stock of the lines takes the new price, one entry for the invoice"""
        items = []
        for line, product, item, old_price in revalued:
            if line.form.revalue_quantity is None or line.retail_price is None:
                raise RuntimeError(
                    "a revalued line has a quantity and a price",
                )
            items.append(
                RevaluationItem(
                    product_id=product.id,
                    invoice_item_id=item.id,
                    quantity=line.form.revalue_quantity,
                    old_price=old_price,
                    new_price=line.retail_price,
                ),
            )
        if not items:
            return None
        amount = sum(
            (
                revaluation_amount(
                    quantity=item.quantity,
                    old_price=item.old_price,
                    new_price=item.new_price,
                )
                for item in items
            ),
            start=Decimal(
                value=0,
            ),
        )
        entry = await self.ledger.create(
            entry=LedgerEntry(
                kind=LedgerKind.REVALUATION,
                occurred_on=occurred_on,
                amount=amount,
                comment=f"по накладной № {invoice_number}",
            ),
        )
        for item in items:
            item.ledger_entry_id = entry.id
        await self.ledger.add_revaluation_items(
            items=items,
        )
        return amount

    async def decline_invoice(
        self,
        invoice_id: int,
    ) -> None:
        draft_invoice = await self._get_draft(
            invoice_id=invoice_id,
        )
        draft_invoice.status = InvoiceStatus.DECLINED
        await self.invoices.commit()

    async def _get_draft(
        self,
        invoice_id: int,
    ) -> Invoice:
        draft_invoice = await self.invoices.get_draft(
            invoice_id=invoice_id,
        )
        if draft_invoice is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Черновик накладной не найден",
            )
        return draft_invoice

    async def _posted_product(
        self,
        supplier: Supplier,
        line: PlannedLine,
        products: dict[ProductKey, Product],
    ) -> Product:
        """the product of a line as it is posted, created or with the new markup and price"""
        if (
            line.key is None
            or line.markup_pct is None
            or line.retail_price is None
            or line.form.name is None
        ):
            raise RuntimeError(
                "a ready draft has a product for every line",
            )
        product = line.product or products.get(
            line.key,
        )
        if product is None:
            product = await self.products.create(
                product=Product(
                    supplier_id=supplier.id,
                    name=line.form.name,
                    markup_pct=line.markup_pct,
                    retail_price=line.retail_price,
                    has_price_tag=False,
                ),
            )
        else:
            if product.markup_pct != line.markup_pct:
                product.markup_pct = line.markup_pct
            # a new cost alone keeps the tag, only a new shelf price resets it
            _reprice(
                product=product,
                price=line.retail_price,
            )
        products[line.key] = product
        return product

    async def _draft(
        self,
        draft_invoice: Invoice,
    ) -> InvoiceDraft:
        plan = await self._plan(
            draft_invoice=draft_invoice,
        )
        return InvoiceDraft(
            id=draft_invoice.id,
            ready=plan.ready,
            issues=plan.issues,
            form=plan.form,
            lines=[
                _draft_line(
                    line=line,
                    catalog_known=plan.catalog_known,
                )
                for line in plan.lines
            ],
            totals=DraftTotals(
                base_total=sum_known(
                    values=(
                        to_kopecks(
                            value=line.prices.base_price_total,
                        )
                        for line in plan.lines
                    ),
                ),
                cost_total=sum_known(
                    values=(line.prices.cost_price_total for line in plan.lines),
                ),
                retail_total=sum_known(
                    values=(line.retail_price_total for line in plan.lines),
                ),
            ),
            supplier=None
            if plan.supplier is None
            else _supplier_summary(
                supplier=plan.supplier,
            ),
            supplier_candidates=plan.candidates,
            extraction=plan.extraction,
        )

    async def _plan(
        self,
        draft_invoice: Invoice,
    ) -> DraftPlan:
        extraction = InvoiceExtraction.model_validate(
            obj=draft_invoice.extracted,
        )
        numbered_items = _numbered_extraction(
            extraction=extraction,
        )
        if draft_invoice.form is None:
            form = await self._initial_form(
                draft_invoice=draft_invoice,
                extraction=extraction,
                numbered_items=numbered_items,
            )
        else:
            form = DraftForm.model_validate(
                obj=draft_invoice.form,
            )
        _number_form_lines(
            form=form,
            source_max=max(
                numbered_items,
                default=0,
            ),
        )
        plan = DraftPlan(
            form=form,
            extraction=extraction,
            supplier=None,
            lines=[],
            candidates=[],
        )
        aliases = [
            normalize_name(
                name=line.name,
            )
            if line.name is not None
            else None
            for line in form.lines
        ]
        known_aliases = {alias for alias in aliases if alias is not None}

        if form.invoice_number is None:
            _block(
                plan=plan,
                message="номер накладной не указан",
            )
        if form.invoice_date is None:
            _block(
                plan=plan,
                message="дата накладной не указана",
            )
        if isinstance(
            form.supplier,
            SupplierRef,
        ):
            plan.supplier = await self.suppliers.get(
                supplier_id=form.supplier.id,
            )
            if plan.supplier is None:
                _block(
                    plan=plan,
                    message=f"продавца с id {form.supplier.id} нет",
                )
            plan.catalog_known = plan.supplier is not None
        elif isinstance(
            form.supplier,
            NewSupplier,
        ):
            if form.supplier.inn is not None and await self.suppliers.get_by_inn(
                inn=form.supplier.inn,
            ):
                _block(
                    plan=plan,
                    message=f"продавец с ИНН {form.supplier.inn} уже есть, выберите его",
                )
            else:
                # a new supplier has no products yet
                plan.catalog_known = True
                plan.candidates = await self._suggest_suppliers(
                    name=form.supplier.name,
                    inn=form.supplier.inn,
                    aliases=known_aliases,
                )
                if plan.candidates:
                    plan.issues.append(
                        Issue(
                            line=None,
                            message="похожий продавец уже есть в базе, проверьте, не он ли это",
                            blocking=False,
                        ),
                    )
        else:
            _block(
                plan=plan,
                message="продавец не выбран",
            )
            plan.candidates = await self._suggest_suppliers(
                name=extraction.supplier.name,
                inn=extraction.supplier.inn,
                aliases=known_aliases,
            )
        if not form.lines:
            _block(
                plan=plan,
                message="в накладной нет строк",
            )

        known: dict[str, Product] = {}
        if plan.supplier is not None:
            known = await self.products.find_by_aliases(
                supplier_id=plan.supplier.id,
                aliases=known_aliases,
            )
        for form_line, alias in zip(
            form.lines,
            aliases,
            strict=True,
        ):
            if form_line.line_no is None:
                raise RuntimeError(
                    "every planned line has a number",
                )
            plan.lines.append(
                await self._plan_line(
                    plan=plan,
                    position=form_line.line_no,
                    form_line=form_line,
                    alias=alias,
                    known=known,
                ),
            )
        await self._find_similar(
            plan=plan,
        )
        await self._compare_costs(
            plan=plan,
        )
        _price_lines(
            plan=plan,
        )
        _check_revaluation(
            plan=plan,
        )

        for line in plan.lines:
            read = numbered_items.get(
                line.position,
            )
            if read is None:
                continue
            # the stable number keeps the source row when preceding rows are removed
            if read.name == line.form.name:
                plan.issues.extend(
                    check_read_prices(
                        line=line.position,
                        read=read,
                        prices=line.prices,
                        quantity=line.form.quantity,
                    ),
                )
        plan.issues.extend(
            check_totals(
                cost_total=form.totals.cost_total,
                base_total=form.totals.base_total,
                prices=[line.prices for line in plan.lines],
                with_vat=any(line.vat_percent for line in form.lines),
            ),
        )

        if (
            plan.supplier is not None
            and form.invoice_number is not None
            and form.invoice_date is not None
        ):
            same = await self.invoices.find_confirmed(
                supplier_id=plan.supplier.id,
                invoice_number=form.invoice_number,
                invoice_date=form.invoice_date,
            )
            if same is not None:
                _block(
                    plan=plan,
                    message=f"эта накладная уже проведена под номером {same.id}",
                )
        return plan

    async def _find_similar(
        self,
        plan: DraftPlan,
    ) -> None:
        """supplier products with a close name for the lines that found none"""
        lines = [
            line
            for line in plan.lines
            if line.product is None
            and line.form.product_id is None
            and line.alias is not None
        ]
        # a new supplier has no catalog yet
        if plan.supplier is None or not lines:
            return
        catalog = await self.products.aliases_of(
            supplier_id=plan.supplier.id,
        )
        for line in lines:
            # a product is as close as the closest of its spellings
            best: dict[int, tuple[float, Product]] = {}
            for alias, product in catalog:
                ratio = name_similarity(
                    key=line.alias or "",
                    other=alias,
                )
                closest = best.get(
                    product.id,
                )
                if ratio >= SIMILAR_NAME_RATIO and (
                    closest is None or ratio > closest[0]
                ):
                    best[product.id] = (ratio, product)
            ranked = sorted(
                best.values(),
                key=lambda match: (-match[0], match[1].name),
            )[:SIMILAR_LIMIT]
            line.similar = [
                SimilarProduct(
                    id=product.id,
                    name=product.name,
                    similarity=int(ratio * 100),
                )
                for ratio, product in ranked
            ]
            if line.similar:
                closest = line.similar[0]
                plan.issues.append(
                    Issue(
                        line=line.position,
                        message=(
                            f"похож на товар «{closest.name}» ({closest.similarity}%), "
                            "проверьте, не он ли это"
                        ),
                        blocking=False,
                        code=SIMILAR_PRODUCT,
                    ),
                )

    async def _compare_costs(
        self,
        plan: DraftPlan,
    ) -> None:
        """a line of a known product shows the cost of its last delivery when the cost changed"""
        costs = await self.products.last_cost_prices(
            product_ids={
                line.product.id for line in plan.lines if line.product is not None
            },
        )
        for line in plan.lines:
            if line.product is None or line.cost_price is None:
                continue
            previous = costs.get(
                line.product.id,
            )
            if previous is not None and previous != line.cost_price:
                line.previous_cost_price = previous

    async def _plan_line(
        self,
        plan: DraftPlan,
        position: int,
        form_line: FormLine,
        alias: str | None,
        known: dict[str, Product],
    ) -> PlannedLine:
        prices = line_prices(
            cost_total=form_line.cost_price_total,
            vat_percent=form_line.vat_percent,
            quantity=form_line.quantity,
        )
        for value, message in (
            (form_line.name, "название не указано"),
            (form_line.quantity, "количество не указано"),
            (form_line.cost_price_total, "сумма по строке не указана"),
        ):
            if value is None:
                _block(
                    plan=plan,
                    message=message,
                    line=position,
                )

        product = None
        linked = False
        if form_line.product_id is not None:
            product = await self.products.get(
                product_id=form_line.product_id,
            )
            if (
                product is None
                or plan.supplier is None
                or product.supplier_id != plan.supplier.id
            ):
                product = None
                _block(
                    plan=plan,
                    message=f"у продавца нет товара с id {form_line.product_id}",
                    line=position,
                )
            elif alias is not None and alias in known:
                linked = known[alias].id == product.id
                if not linked:
                    _block(
                        plan=plan,
                        message=f"это название уже относится к товару «{known[alias].name}»",
                        line=position,
                    )
        elif alias is not None and alias in known:
            product = known[alias]
            linked = True

        key: ProductKey | None = None
        if product is not None:
            key = ("product", product.id)
        elif alias is not None and form_line.product_id is None:
            key = ("new", alias)
        return PlannedLine(
            position=position,
            form=form_line,
            prices=prices,
            cost_price=to_kopecks(
                value=prices.cost_price,
            ),
            alias=alias,
            product=product,
            linked=linked,
            key=key,
        )

    async def _initial_form(
        self,
        draft_invoice: Invoice,
        extraction: InvoiceExtraction,
        numbered_items: dict[int, InvoiceItemExtraction],
    ) -> DraftForm:
        """the form as the model read it, before the user saves it"""
        supplier_id = draft_invoice.supplier_id
        # a supplier added since the upload is picked up while the draft is untouched
        if supplier_id is None and extraction.supplier.inn is not None:
            supplier = await self.suppliers.get_by_inn(
                inn=extraction.supplier.inn,
            )
            supplier_id = supplier.id if supplier else None
        read = extraction.model_dump(
            mode="json",
        )
        supplier: dict[str, JsonValue] | None = None
        if supplier_id is not None:
            supplier = {"id": supplier_id}
        elif read["supplier"]["name"] is not None:
            # not found by inn, so the supplier the model read is offered as a new one
            supplier = read["supplier"]
        return DraftForm.model_validate(
            obj={
                "invoice_number": read["invoice_number"],
                "invoice_date": read["invoice_date"],
                "supplier": supplier,
                "totals": {
                    "cost_total": read["totals"][
                        printed_cost_total_field(
                            invoice=extraction,
                        )
                    ],
                    "base_total": read["totals"]["base_total"],
                },
                "lines": [
                    {
                        "line_no": line_no,
                        "name": read_item["name"],
                        "quantity": read_item["quantity"],
                        "unit": read_item["unit"],
                        "vat_percent": read_item["vat_percent"],
                        "cost_price_total": read_item[
                            source_total_field(
                                item=item,
                            )
                        ],
                        "product_id": None,
                        "retail_price": None,
                    }
                    for (line_no, item), read_item in zip(
                        numbered_items.items(),
                        read["items"],
                        strict=True,
                    )
                ],
            },
        )

    async def _suggest_suppliers(
        self,
        name: str | None,
        inn: str | None,
        aliases: set[str],
    ) -> list[SupplierCandidate]:
        # with an inn that nobody has, a supplier with another inn is someone else
        only_without_inn = inn is not None
        ranked = await self.suppliers.rank_by_aliases(
            aliases=aliases,
            only_without_inn=only_without_inn,
            limit=CANDIDATES_LIMIT,
        )
        candidates = [
            _candidate(
                supplier=supplier,
                matched_lines=matched_lines,
            )
            for supplier, matched_lines in ranked
        ]
        if name is not None:
            seen = {candidate.id for candidate in candidates}
            by_name = await self.suppliers.search_by_name(
                name=name,
                only_without_inn=only_without_inn,
                limit=CANDIDATES_LIMIT,
            )
            candidates.extend(
                _candidate(
                    supplier=supplier,
                    matched_lines=0,
                )
                for supplier in by_name
                if supplier.id not in seen
            )
        return candidates[:CANDIDATES_LIMIT]


def _numbered_extraction(
    extraction: InvoiceExtraction,
) -> dict[int, InvoiceItemExtraction]:
    last_number = max(
        (item.line_no for item in extraction.items if item.line_no is not None),
        default=0,
    )
    numbered: dict[int, InvoiceItemExtraction] = {}
    for item in extraction.items:
        number = item.line_no
        if number is None:
            last_number += 1
            number = last_number
        if number > MAX_LINE_NO:
            _invalid(
                detail="Нет свободного номера позиции в допустимом диапазоне",
            )
        if number in numbered:
            _invalid(
                detail=f"Номер позиции {number} повторяется в накладной",
            )
        numbered[number] = item
    return numbered


def _number_form_lines(
    form: DraftForm,
    source_max: int,
) -> None:
    used: set[int] = set()
    for line in form.lines:
        if line.line_no is None:
            continue
        if line.line_no in used:
            _invalid(
                detail=f"Номер позиции {line.line_no} повторяется в накладной",
            )
        used.add(
            line.line_no,
        )
    # legacy forms without any numbers keep their current positions
    legacy = not used
    last_number = max(
        source_max,
        max(
            used,
            default=0,
        ),
    )
    for position, line in enumerate(
        iterable=form.lines,
        start=1,
    ):
        if line.line_no is not None:
            continue
        if legacy:
            number = position
        else:
            last_number += 1
            number = last_number
        if number > MAX_LINE_NO:
            _invalid(
                detail="Нет свободного номера позиции в допустимом диапазоне",
            )
        line.line_no = number


def _block(
    plan: DraftPlan,
    message: str,
    line: int | None = None,
) -> None:
    plan.issues.append(
        Issue(
            line=line,
            message=message,
        ),
    )


def _issue_text(issue: Issue) -> str:
    if issue.line is None:
        return issue.message
    return f"строка {issue.line}: {issue.message}"


def _price_lines(plan: DraftPlan) -> None:
    """one markup per product: from a price the user set, else the current one"""
    markups: dict[ProductKey, tuple[Decimal, int]] = {}
    # lines with a price that cannot be used, they already have their issue
    rejected: set[int] = set()
    for line in plan.lines:
        price = line.form.retail_price
        if price is None or line.key is None:
            continue
        if not line.cost_price:
            _block(
                plan=plan,
                message="нет закупочной цены, наценку посчитать не из чего",
                line=line.position,
            )
            rejected.add(
                line.position,
            )
            continue
        markup_pct = markup_for_price(
            cost_price=line.cost_price,
            price=Decimal(
                value=price,
            ),
        )
        # an unchanged price keeps the markup, rounding would shift it a little
        if (
            line.product is not None
            and retail_price(
                cost_price=line.cost_price,
                markup_pct=line.product.markup_pct,
            )
            == price
        ):
            markup_pct = line.product.markup_pct
        if not 0 <= markup_pct <= MAX_MARKUP_PCT:
            _block(
                plan=plan,
                message=(
                    f"при цене {price} и закупке {line.cost_price} наценка {markup_pct}%, "
                    f"а она должна быть от 0 до {MAX_MARKUP_PCT}%"
                ),
                line=line.position,
            )
            rejected.add(
                line.position,
            )
            continue
        other = markups.setdefault(
            line.key,
            (markup_pct, line.position),
        )
        if other[0] != markup_pct:
            _block(
                plan=plan,
                message=f"у этого товара уже задана другая цена в строке {other[1]}",
                line=line.position,
            )

    for line in plan.lines:
        if line.key is None or line.position in rejected:
            continue
        found = markups.get(
            line.key,
        )
        markup_pct = found[0] if found else None
        if markup_pct is None and line.product is not None:
            markup_pct = line.product.markup_pct
        if markup_pct is None:
            # until the supplier is settled the product may still be found
            if not plan.catalog_known:
                continue
            _block(
                plan=plan,
                message="новый товар, укажите розничную цену",
                line=line.position,
            )
            continue
        line.markup_pct = markup_pct
        if line.cost_price is not None:
            line.retail_price = retail_price(
                cost_price=line.cost_price,
                markup_pct=markup_pct,
            )
            if line.form.quantity is not None:
                line.retail_price_total = retail_price_total(
                    retail_price=line.retail_price,
                    quantity=line.form.quantity,
                )


def _check_revaluation(plan: DraftPlan) -> None:
    """a changed shelf price asks for the old stock, one count per product"""
    for line in plan.lines:
        if (
            line.product is not None
            and line.retail_price is not None
            and line.retail_price != line.product.retail_price
        ):
            line.previous_retail_price = line.product.retail_price

    counted: dict[ProductKey, int] = {}
    for line in plan.lines:
        quantity = line.form.revalue_quantity
        if quantity is None:
            continue
        if line.previous_retail_price is None or line.retail_price is None:
            _block(
                plan=plan,
                message="цена на полке не меняется, переоценивать нечего",
                line=line.position,
            )
            continue
        if line.key is not None:
            other = counted.setdefault(
                line.key,
                line.position,
            )
            if other != line.position:
                _block(
                    plan=plan,
                    message=f"переоценка этого товара уже указана в строке {other}",
                    line=line.position,
                )
                continue
        if not revaluation_amount(
            quantity=quantity,
            old_price=line.previous_retail_price,
            new_price=line.retail_price,
        ):
            _block(
                plan=plan,
                message="переоценка выходит меньше копейки, проверьте количество",
                line=line.position,
            )

    # the warning stays until the old stock of the product is counted in any of its lines
    warned: set[ProductKey] = set()
    for line in plan.lines:
        if (
            line.previous_retail_price is None
            or line.retail_price is None
            or line.key is None
            or line.key in counted
            or line.key in warned
        ):
            continue
        warned.add(
            line.key,
        )
        plan.issues.append(
            Issue(
                line=line.position,
                message=(
                    f"цена на полке меняется с {line.previous_retail_price:.0f} "
                    f"на {line.retail_price:.0f} ₽, укажите, сколько старого товара "
                    "осталось, чтобы переоценить"
                ),
                blocking=False,
                code=PRICE_CHANGED,
            ),
        )


def _candidate(
    supplier: Supplier,
    matched_lines: int,
) -> SupplierCandidate:
    return SupplierCandidate(
        id=supplier.id,
        name=supplier.name,
        short_name=supplier.short_name,
        inn=supplier.inn,
        matched_lines=matched_lines,
    )


def _reprice(product: Product, price: Decimal) -> None:
    """a new shelf price makes the hanging tag wrong, it has to be printed again"""
    if product.retail_price != price:
        product.retail_price = price
        product.has_price_tag = False


def _supplier_summary(supplier: Supplier) -> SupplierSummary:
    return SupplierSummary(
        id=supplier.id,
        name=supplier.name,
        short_name=supplier.short_name,
        inn=supplier.inn,
    )


def _product_summary(row: ProductRow) -> ProductSummary:
    return ProductSummary(
        id=row.product.id,
        name=row.product.name,
        markup_pct=row.product.markup_pct,
        unit=row.last_item.unit if row.last_item else None,
        vat_percent=row.last_item.vat_percent if row.last_item else None,
        cost_price=row.last_item.cost_price if row.last_item else None,
        # the shelf price, a revaluation may have changed it after the last invoice
        retail_price=row.product.retail_price,
    )


def _draft_line(
    line: PlannedLine,
    catalog_known: bool,
) -> DraftLine:
    return DraftLine(
        line=line.position,
        cost_price=line.cost_price,
        base_price=to_kopecks(
            value=line.prices.base_price,
        ),
        base_price_total=to_kopecks(
            value=line.prices.base_price_total,
        ),
        product_id=line.product.id if line.product else None,
        product_name=line.product.name if line.product else line.form.name,
        new_product=catalog_known and line.product is None and line.key is not None,
        markup_pct=line.markup_pct,
        retail_price=line.retail_price,
        retail_price_total=line.retail_price_total,
        previous_cost_price=line.previous_cost_price,
        previous_retail_price=line.previous_retail_price,
        similar=line.similar,
    )


def _invoice_item(
    draft_invoice: Invoice,
    line: PlannedLine,
    product: Product,
) -> InvoiceItem:
    """the line as it is posted"""
    if (
        line.form.name is None
        or line.form.quantity is None
        or line.cost_price is None
        or line.prices.cost_price_total is None
        or line.markup_pct is None
        or line.retail_price is None
    ):
        raise RuntimeError(
            "a ready draft has every line priced",
        )
    return InvoiceItem(
        invoice_id=draft_invoice.id,
        product_id=product.id,
        supplier_id=draft_invoice.supplier_id,
        line_no=line.position,
        name=line.form.name,
        quantity=line.form.quantity,
        unit=line.form.unit,
        vat_percent=line.form.vat_percent,
        base_price=to_kopecks(
            value=line.prices.base_price,
        ),
        cost_price=line.cost_price,
        cost_price_total=line.prices.cost_price_total,
        markup_pct=line.markup_pct,
        retail_price=line.retail_price,
    )


class SupplierService:
    def __init__(
        self,
        suppliers: SupplierRepositoryDep,
        products: ProductRepositoryDep,
    ) -> None:
        self.suppliers = suppliers
        self.products = products

    async def search_products(
        self,
        supplier_id: int,
        query: str | None,
        limit: int,
    ) -> list[ProductSummary]:
        supplier = await self.suppliers.get(
            supplier_id=supplier_id,
        )
        if supplier is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Продавец не найден",
            )
        rows = await self.products.search(
            supplier_id=supplier_id,
            query=query,
            key=normalize_name(
                name=query,
            )
            if query
            else None,
            limit=limit,
        )
        return [
            _product_summary(
                row=row,
            )
            for row in rows
        ]

    async def edit_supplier(
        self,
        supplier_id: int,
        payload: SupplierEdit,
    ) -> SupplierSummary:
        supplier = await self.suppliers.get(
            supplier_id=supplier_id,
        )
        if supplier is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Продавец не найден",
            )
        if payload.inn is not None:
            existing = await self.suppliers.get_by_inn(
                inn=payload.inn,
            )
            if existing is not None and existing.id != supplier.id:
                _conflict(
                    detail=f"Поставщик с ИНН {payload.inn} уже существует",
                )
        supplier.name = payload.name
        supplier.short_name = payload.short_name
        supplier.inn = payload.inn
        await self.suppliers.commit()
        return _supplier_summary(
            supplier=supplier,
        )

    async def search(
        self,
        query: str | None,
        limit: int,
    ) -> list[SupplierSummary]:
        suppliers = await self.suppliers.search(
            query=query,
            limit=limit,
        )
        return [
            _supplier_summary(
                supplier=supplier,
            )
            for supplier in suppliers
        ]

    async def catalog(self) -> Catalog:
        suppliers = await self.suppliers.list_all()
        rows = await self.products.catalog()
        products = []
        for row in rows:
            name_key = normalize_name(
                name=row.product.name,
            )
            products.append(
                CatalogProduct(
                    **_product_summary(
                        row=row,
                    ).model_dump(),
                    supplier_id=row.product.supplier_id,
                    has_price_tag=row.product.has_price_tag,
                    spellings=[
                        alias.alias_raw
                        for alias in sorted(
                            row.aliases,
                            key=lambda alias: alias.id,
                        )
                        if alias.alias_normalized != name_key
                    ],
                ),
            )
        return Catalog(
            suppliers=[
                _supplier_summary(
                    supplier=supplier,
                )
                for supplier in suppliers
            ],
            products=products,
        )


class LedgerService:
    def __init__(
        self,
        ledger: LedgerRepositoryDep,
        products: ProductRepositoryDep,
        invoices: InvoiceRepositoryDep,
    ) -> None:
        self.ledger = ledger
        self.products = products
        self.invoices = invoices

    async def history(
        self,
        limit: int,
        offset: int,
    ) -> LedgerPage:
        # one row more tells whether there is another page
        rows = await self.ledger.history(
            limit=limit + 1,
            offset=offset,
        )
        return LedgerPage(
            balance=await self.ledger.balance(),
            cash_balance=await self.ledger.cash_balance(),
            entries=[
                _ledger_entry_out(
                    row=row,
                )
                for row in rows[:limit]
            ],
            has_more=len(rows) > limit,
        )

    async def balance_on(
        self,
        on: date | None,
    ) -> LedgerBalance:
        return LedgerBalance(
            balance=await self.ledger.balance(
                on=on,
            ),
            cash_balance=await self.ledger.cash_balance(
                on=on,
            ),
            closed_on=await self.ledger.last_count_on(
                kind=LedgerKind.STOCKTAKE,
            ),
            cash_closed_on=await self.ledger.last_count_on(
                kind=LedgerKind.CASH_COUNT,
            ),
        )

    async def add_sale(
        self,
        payload: SaleCreate,
    ) -> LedgerPosted:
        """the stock goes down by the whole sale, the till gets the cash part only"""
        total = payload.cash + payload.card
        if not total:
            _invalid(
                detail="Укажите выручку наличными или безналом",
            )
        await self.ledger.lock()
        await _check_date(
            ledger=self.ledger,
            on=payload.occurred_on,
            stock=True,
            cash=payload.cash > 0,
        )
        return await self._post(
            entry=LedgerEntry(
                kind=LedgerKind.SALE,
                occurred_on=payload.occurred_on,
                amount=-total,
                cash=payload.cash,
                comment=payload.comment,
            ),
        )

    async def add_write_off(
        self,
        payload: OutflowCreate,
    ) -> LedgerPosted:
        """the stock goes down by the amount"""
        await self.ledger.lock()
        await _check_date(
            ledger=self.ledger,
            on=payload.occurred_on,
            stock=True,
            cash=False,
        )
        return await self._post(
            entry=LedgerEntry(
                kind=LedgerKind.WRITE_OFF,
                occurred_on=payload.occurred_on,
                amount=-payload.amount,
                comment=payload.comment,
            ),
        )

    async def add_cash_in(
        self,
        payload: OutflowCreate,
    ) -> LedgerPosted:
        """money put into the till"""
        await self.ledger.lock()
        await _check_date(
            ledger=self.ledger,
            on=payload.occurred_on,
            stock=False,
            cash=True,
        )
        return await self._post(
            entry=LedgerEntry(
                kind=LedgerKind.CASH_IN,
                occurred_on=payload.occurred_on,
                amount=0,
                cash=payload.amount,
                comment=payload.comment,
            ),
        )

    async def add_cash_out(
        self,
        payload: CashOutCreate,
    ) -> LedgerPosted:
        """money taken from the till, the comment says what for"""
        await self.ledger.lock()
        await _check_date(
            ledger=self.ledger,
            on=payload.occurred_on,
            stock=False,
            cash=True,
        )
        return await self._post(
            entry=LedgerEntry(
                kind=LedgerKind.CASH_OUT,
                occurred_on=payload.occurred_on,
                amount=0,
                cash=-payload.amount,
                comment=payload.comment,
            ),
        )

    async def add_stocktake(
        self,
        payload: StocktakeCreate,
    ) -> LedgerPosted:
        """the entry is the shortage or the surplus, after it the balance is the counted stock"""
        await self.ledger.lock()
        await _check_date(
            ledger=self.ledger,
            on=payload.occurred_on,
            stock=True,
            cash=False,
        )
        expected = await self.ledger.balance(
            on=payload.occurred_on,
        )
        return await self._post(
            entry=LedgerEntry(
                kind=LedgerKind.STOCKTAKE,
                occurred_on=payload.occurred_on,
                amount=payload.counted - expected,
                comment=payload.comment,
            ),
        )

    async def add_cash_count(
        self,
        payload: CashCountCreate,
    ) -> LedgerPosted:
        """the entry is the shortage or the surplus of the till, after it the cash is as counted"""
        await self.ledger.lock()
        await _check_date(
            ledger=self.ledger,
            on=payload.occurred_on,
            stock=False,
            cash=True,
        )
        expected = await self.ledger.cash_balance(
            on=payload.occurred_on,
        )
        return await self._post(
            entry=LedgerEntry(
                kind=LedgerKind.CASH_COUNT,
                occurred_on=payload.occurred_on,
                amount=0,
                cash=payload.counted - expected,
                comment=payload.comment,
            ),
        )

    async def add_revaluation(
        self,
        payload: RevaluationCreate,
    ) -> LedgerPosted:
        """the stock of the products on the shelf takes the new prices, the markups stay"""
        await self.ledger.lock()
        await _check_date(
            ledger=self.ledger,
            on=payload.occurred_on,
            stock=True,
            cash=False,
        )
        items: list[RevaluationItem] = []
        products: list[Product] = []
        for line in payload.lines:
            product = await self.products.get(
                product_id=line.product_id,
            )
            if product is None:
                _invalid(
                    detail=f"Товара с id {line.product_id} нет",
                )
            if product in products:
                _invalid(
                    detail=f"Товар «{product.name}» указан дважды",
                )
            new_price = Decimal(
                value=line.new_price,
            )
            if new_price == product.retail_price:
                _invalid(
                    detail=f"Цена товара «{product.name}» уже {line.new_price} ₽",
                )
            products.append(
                product,
            )
            items.append(
                RevaluationItem(
                    product_id=product.id,
                    invoice_item_id=None,
                    quantity=line.quantity,
                    old_price=product.retail_price,
                    new_price=new_price,
                ),
            )
        return await self._finish(
            entry=await self._post_revaluation(
                occurred_on=payload.occurred_on,
                comment=payload.comment,
                items=items,
                products=products,
            ),
        )

    async def edit_product(
        self,
        product_id: int,
        payload: ProductEdit,
    ) -> LedgerPosted | None:
        """a corrected name keeps the old one as a spelling, a new price revalues the old stock"""
        if payload.revaluation is not None:
            await self.ledger.lock()
            await _check_date(
                ledger=self.ledger,
                on=payload.revaluation.occurred_on,
                stock=True,
                cash=False,
            )
        product = await self.products.get(
            product_id=product_id,
        )
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Товар не найден",
            )
        new_price = Decimal(
            value=payload.retail_price,
        )
        if payload.revaluation is not None and new_price == product.retail_price:
            _invalid(
                detail=f"Цена уже {payload.retail_price} ₽, переоценивать нечего",
            )
        name = payload.name.strip()
        if name != product.name:
            await self._rename(
                product=product,
                name=name,
            )
        if payload.revaluation is None:
            _reprice(
                product=product,
                price=new_price,
            )
            await self.ledger.commit()
            return None
        return await self._finish(
            entry=await self._post_revaluation(
                occurred_on=payload.revaluation.occurred_on,
                comment=payload.revaluation.comment,
                items=[
                    RevaluationItem(
                        product_id=product.id,
                        invoice_item_id=None,
                        quantity=payload.revaluation.quantity,
                        old_price=product.retail_price,
                        new_price=new_price,
                    ),
                ],
                products=[
                    product,
                ],
            ),
        )

    async def mark_price_tag(
        self,
        product_id: int,
        payload: PriceTagMark,
    ) -> None:
        product = await self.products.get(
            product_id=product_id,
        )
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Товар не найден",
            )
        if product.retail_price != payload.retail_price:
            _conflict(
                detail="Цена товара изменилась, обновите страницу",
            )
        product.has_price_tag = payload.has_price_tag
        await self.ledger.commit()

    async def _rename(
        self,
        product: Product,
        name: str,
    ) -> None:
        """both spellings find the product on the next invoices"""
        key = normalize_name(
            name=name,
        )
        # the old spelling first, a name differing only in case or quotes has the same key
        spellings = {
            normalize_name(
                name=product.name,
            ): product.name,
            key: name,
        }
        known = await self.products.find_by_aliases(
            supplier_id=product.supplier_id,
            aliases=spellings.keys(),
        )
        other = known.get(
            key,
        )
        if other is not None and other.id != product.id:
            _conflict(
                detail=f"Название «{name}» уже у товара «{other.name}»",
            )
        for alias_key, spelling in spellings.items():
            if alias_key not in known:
                await self.products.add_alias(
                    alias=ProductAlias(
                        product_id=product.id,
                        supplier_id=product.supplier_id,
                        alias_normalized=alias_key,
                        alias_raw=spelling,
                    ),
                )
        product.name = name

    async def _post_revaluation(
        self,
        occurred_on: date,
        comment: str | None,
        items: list[RevaluationItem],
        products: list[Product],
    ) -> LedgerEntry:
        """the entry for the items, the products take the new prices"""
        amount = sum(
            (
                revaluation_amount(
                    quantity=item.quantity,
                    old_price=item.old_price,
                    new_price=item.new_price,
                )
                for item in items
            ),
            start=Decimal(
                value=0,
            ),
        )
        if not amount:
            _invalid(
                detail="Переоценка выходит меньше копейки, проверьте количество",
            )
        entry = await self.ledger.create(
            entry=LedgerEntry(
                kind=LedgerKind.REVALUATION,
                occurred_on=occurred_on,
                amount=amount,
                comment=comment,
            ),
        )
        for item, product in zip(
            items,
            products,
            strict=True,
        ):
            item.ledger_entry_id = entry.id
            _reprice(
                product=product,
                price=item.new_price,
            )
        await self.ledger.add_revaluation_items(
            items=items,
        )
        return entry

    async def revaluation_lines(
        self,
        entry_id: int,
    ) -> list[RevaluationLineOut]:
        """the products of a revaluation, a reversal shows the lines it cancels"""
        entry = await self.ledger.get(
            entry_id=entry_id,
        )
        if entry is None or entry.kind != LedgerKind.REVALUATION:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Переоценка не найдена",
            )
        items = await self.ledger.revaluation_items_of(
            entry_id=entry.reverses_id or entry.id,
        )
        # a reversal takes every line back
        sign = -1 if entry.reverses_id is not None else 1
        return [
            RevaluationLineOut(
                product_id=item.product_id,
                product_name=item.product.name,
                quantity=item.quantity,
                old_price=item.old_price,
                new_price=item.new_price,
                amount=sign
                * revaluation_amount(
                    quantity=item.quantity,
                    old_price=item.old_price,
                    new_price=item.new_price,
                ),
            )
            for item in items
        ]

    async def report(
        self,
        date_from: date,
        date_to: date,
    ) -> LedgerReport:
        if date_from > date_to:
            _invalid(
                detail="Начало периода позже его конца",
            )
        sums = await self.ledger.sums_by_kind(
            date_from=date_from,
            date_to=date_to,
        )
        cash_sums = await self.ledger.cash_sums_by_kind(
            date_from=date_from,
            date_to=date_to,
        )
        zero = Decimal(
            value=0,
        )
        day_before = date_from - timedelta(
            days=1,
        )
        sales = sums.get(
            LedgerKind.SALE,
            zero,
        )
        sales_cash = cash_sums.get(
            LedgerKind.SALE,
            zero,
        )
        rows = await self.ledger.history(
            limit=None,
            offset=0,
            date_from=date_from,
            date_to=date_to,
            newest_first=False,
        )
        return LedgerReport(
            date_from=date_from,
            date_to=date_to,
            opening=await self.ledger.balance(
                on=day_before,
            ),
            invoices=sums.get(
                LedgerKind.INVOICE,
                zero,
            ),
            sales=sales,
            write_offs=sums.get(
                LedgerKind.WRITE_OFF,
                zero,
            ),
            stocktakes=sums.get(
                LedgerKind.STOCKTAKE,
                zero,
            ),
            revaluations=sums.get(
                LedgerKind.REVALUATION,
                zero,
            ),
            closing=await self.ledger.balance(
                on=date_to,
            ),
            cash_opening=await self.ledger.cash_balance(
                on=day_before,
            ),
            sales_cash=sales_cash,
            # the sales are negative, they take the stock out
            sales_card=-sales - sales_cash,
            cash_ins=cash_sums.get(
                LedgerKind.CASH_IN,
                zero,
            ),
            cash_outs=cash_sums.get(
                LedgerKind.CASH_OUT,
                zero,
            ),
            cash_counts=cash_sums.get(
                LedgerKind.CASH_COUNT,
                zero,
            ),
            cash_closing=await self.ledger.cash_balance(
                on=date_to,
            ),
            entries=[
                _ledger_entry_out(
                    row=row,
                    short_names=True,
                )
                for row in rows
            ],
        )

    async def period_report(
        self,
        date_from: date,
        date_to: date,
    ) -> PeriodReport:
        """the period day by day with the invoices and what is owed for them"""
        if date_from > date_to:
            _invalid(
                detail="Начало периода позже его конца",
            )
        day_before = date_from - timedelta(
            days=1,
        )
        rows = await self.ledger.history(
            limit=None,
            offset=0,
            date_from=date_from,
            date_to=date_to,
            newest_first=False,
        )
        invoice_ids = [
            row.entry.invoice_id for row in rows if row.entry.invoice_id is not None
        ]
        cost_totals = await self.invoices.cost_totals(
            invoice_ids=invoice_ids,
        )
        paid_totals = await self.invoices.paid_totals(
            invoice_ids=invoice_ids,
            on=date_to,
        )
        return PeriodReport(
            date_from=date_from,
            date_to=date_to,
            opening=await self.ledger.balance(
                on=day_before,
            ),
            cash_opening=await self.ledger.cash_balance(
                on=day_before,
            ),
            days=[
                _report_day(
                    day=day,
                    rows=list(
                        day_rows,
                    ),
                    cost_totals=cost_totals,
                    paid_totals=paid_totals,
                )
                for day, day_rows in groupby(
                    rows,
                    key=lambda row: row.entry.occurred_on,
                )
            ],
            paid_in_period=await self.invoices.paid_between(
                date_from=date_from,
                date_to=date_to,
            ),
            debts=[
                SupplierDebt(
                    supplier_name=debt.supplier_short_name or debt.supplier_name,
                    invoice_number=debt.invoice.invoice_number or "",
                    invoice_date=debt.invoice.invoice_date,
                    cost_total=debt.cost_total,
                    paid=debt.paid,
                    debt=debt.cost_total - debt.paid,
                )
                for debt in await self.invoices.debts(
                    on=date_to,
                )
            ],
        )

    async def reverse(
        self,
        entry_id: int,
    ) -> LedgerPosted:
        """the ledger is never edited, a mistake is cancelled by an opposite entry on the same day"""
        await self.ledger.lock()
        entry = await self.ledger.get(
            entry_id=entry_id,
        )
        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Запись журнала не найдена",
            )
        if entry.kind == LedgerKind.INVOICE:
            _conflict(
                detail="Проведённую накладную нельзя сторнировать",
            )
        if entry.reverses_id is not None:
            _conflict(
                detail="Сторно нельзя сторнировать",
            )
        if await self.ledger.is_reversed(
            entry_id=entry.id,
        ):
            _conflict(
                detail="Запись уже сторнирована",
            )
        if _counts_stock(
            entry=entry,
        ) and await self.ledger.has_count_after(
            entry=entry,
            kind=LedgerKind.STOCKTAKE,
        ):
            _conflict(
                detail="После этой записи был переучёт, исправьте остаток новым переучётом",
            )
        if _counts_cash(
            entry=entry,
        ) and await self.ledger.has_count_after(
            entry=entry,
            kind=LedgerKind.CASH_COUNT,
        ):
            _conflict(
                detail="После этой записи была сверка кассы, исправьте кассу новой сверкой",
            )
        if entry.kind == LedgerKind.REVALUATION:
            for item in await self.ledger.revaluation_items_of(
                entry_id=entry.id,
            ):
                # a price changed again since then is left as it is
                if item.product.retail_price == item.new_price:
                    _reprice(
                        product=item.product,
                        price=item.old_price,
                    )
        return await self._post(
            entry=LedgerEntry(
                kind=entry.kind,
                occurred_on=entry.occurred_on,
                amount=-entry.amount,
                cash=-entry.cash,
                # reverses_id already says what it cancels
                comment=None,
                reverses_id=entry.id,
            ),
        )

    async def _post(
        self,
        entry: LedgerEntry,
    ) -> LedgerPosted:
        return await self._finish(
            entry=await self.ledger.create(
                entry=entry,
            ),
        )

    async def _finish(
        self,
        entry: LedgerEntry,
    ) -> LedgerPosted:
        """commits the created entry and reports the balances after it"""
        balance = await self.ledger.balance()
        cash_balance = await self.ledger.cash_balance()
        await self.ledger.commit()
        return LedgerPosted(
            id=entry.id,
            amount=entry.amount,
            cash=entry.cash,
            balance=balance,
            cash_balance=cash_balance,
        )


async def _check_date(
    ledger: LedgerRepository,
    on: date,
    stock: bool,
    cash: bool,
) -> None:
    """an entry is checked against the counts of what it changes"""
    if on > today():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Дата не может быть в будущем",
        )
    # a count fixes the balance, an entry before it would change what was counted
    for counted, kind, detail in (
        (stock, LedgerKind.STOCKTAKE, "Период закрыт переучётом от {closed}"),
        (cash, LedgerKind.CASH_COUNT, "Касса закрыта сверкой от {closed}"),
    ):
        if not counted:
            continue
        closed_on = await ledger.last_count_on(
            kind=kind,
        )
        if closed_on is not None and on < closed_on:
            _conflict(
                detail=detail.format(
                    closed=format_invoice_date(
                        value=closed_on,
                    ),
                ),
            )


def _conflict(detail: str) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=detail,
    )


def _invalid(detail: str) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=detail,
    )


def _counts_stock(entry: LedgerEntry) -> bool:
    """a stocktake depends on the entry"""
    return entry.amount != 0 or entry.kind == LedgerKind.STOCKTAKE


def _counts_cash(entry: LedgerEntry) -> bool:
    """a cash count depends on the entry"""
    return entry.cash != 0 or entry.kind == LedgerKind.CASH_COUNT


def _report_day(
    day: date,
    rows: list[LedgerRow],
    cost_totals: dict[int, Decimal],
    paid_totals: dict[int, Decimal],
) -> ReportDay:
    """the entries of one day in the ledger order, a reversal cancels its entry in the sums"""
    zero = Decimal(
        value=0,
    )
    invoices: list[ReportInvoice] = []
    sales = zero
    sales_cash = zero
    cash_moves = zero
    cash_notes: list[CashNote] = []
    for row in rows:
        entry = row.entry
        if entry.kind == LedgerKind.INVOICE and entry.invoice_id is not None:
            invoices.append(
                ReportInvoice(
                    supplier_name=_report_name(
                        row=row,
                    )
                    or "",
                    invoice_number=row.invoice_number or "",
                    cost_total=cost_totals.get(
                        entry.invoice_id,
                        zero,
                    ),
                    retail_total=entry.amount,
                    paid=paid_totals.get(
                        entry.invoice_id,
                        zero,
                    ),
                ),
            )
        elif entry.kind == LedgerKind.SALE:
            # a sale takes the stock out, its amount is negative
            sales -= entry.amount
            sales_cash += entry.cash
        elif entry.kind in (
            LedgerKind.CASH_IN,
            LedgerKind.CASH_OUT,
            LedgerKind.CASH_COUNT,
        ):
            cash_moves += entry.cash
            if entry.reverses_id is None and row.reversed_by_id is None:
                cash_notes.append(
                    CashNote(
                        kind=entry.kind,
                        cash=entry.cash,
                        comment=entry.comment,
                    ),
                )
    last = rows[-1]
    return ReportDay(
        day=day,
        invoices=invoices,
        sales_cash=sales_cash,
        sales_card=sales - sales_cash,
        cash_moves=cash_moves,
        cash_notes=cash_notes,
        cash_after=last.cash_after,
        balance_after=last.balance_after,
    )


def _report_name(row: LedgerRow) -> str | None:
    """the reports print the short name of the supplier when it has one"""
    return row.supplier_short_name or row.supplier_name


def _ledger_entry_out(
    row: LedgerRow,
    short_names: bool = False,
) -> LedgerEntryOut:
    return LedgerEntryOut(
        id=row.entry.id,
        occurred_on=row.entry.occurred_on,
        kind=row.entry.kind,
        amount=row.entry.amount,
        cash=row.entry.cash,
        balance_after=row.balance_after,
        cash_after=row.cash_after,
        comment=row.entry.comment,
        reverses_id=row.entry.reverses_id,
        reversed_by_id=row.reversed_by_id,
        invoice_id=row.entry.invoice_id,
        invoice_number=row.invoice_number,
        supplier_name=_report_name(
            row=row,
        )
        if short_names
        else row.supplier_name,
    )


InvoiceServiceDep = Annotated[
    InvoiceService,
    Depends(
        dependency=InvoiceService,
    ),
]
LedgerServiceDep = Annotated[
    LedgerService,
    Depends(
        dependency=LedgerService,
    ),
]
SupplierServiceDep = Annotated[
    SupplierService,
    Depends(
        dependency=SupplierService,
    ),
]
