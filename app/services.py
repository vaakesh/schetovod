from dataclasses import dataclass, field
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, HTTPException, status
from pydantic import JsonValue

from enums import InvoiceStatus, LedgerKind
from models import (
    Invoice,
    InvoiceItem,
    LedgerEntry,
    Product,
    ProductAlias,
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
)
from repositories import (
    InvoiceRepositoryDep,
    LedgerRepositoryDep,
    ProductRepositoryDep,
    SupplierRepositoryDep,
)
from schemas import (
    ConfirmedInvoice,
    DraftForm,
    DraftLine,
    DraftTotals,
    FormLine,
    InvoiceDraft,
    InvoiceExtraction,
    InvoiceList,
    InvoiceListItem,
    Issue,
    NewSupplier,
    PostedInvoice,
    PostedLine,
    ProductSummary,
    SimilarProduct,
    SupplierCandidate,
    SupplierRef,
    SupplierSummary,
)

CANDIDATES_LIMIT = 5
SIMILAR_LIMIT = 3
# the issue code of a line with a close catalog product
SIMILAR_PRODUCT = "similar_product"

# an existing product by id or a new one by its name key, lines with one key are one product
type ProductKey = tuple[str, int | str]


@dataclass
class PlannedLine:
    """a form line with what is derived from it and from the catalog"""

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
                corrections={},
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
        query: str | None,
        limit: int,
        offset: int,
    ) -> InvoiceList:
        # one row more tells whether there is another page
        rows = await self.invoices.search(
            status=status,
            query=query,
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
            key=lambda item: item.line_no,
        )
        return PostedInvoice(
            id=invoice.id,
            invoice_number=invoice.invoice_number,
            invoice_date=invoice.invoice_date,
            supplier=SupplierSummary(
                id=supplier.id,
                name=supplier.name,
                inn=supplier.inn,
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
            cost_total=sum(
                (item.cost_price_total for item in items),
                start=Decimal(
                    value=0,
                ),
            ),
            retail_total=entry.amount,
            ledger_entry_id=entry.id,
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
        draft_invoice.corrections = form.model_dump(
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
    ) -> ConfirmedInvoice:
        """writes the catalog changes, the lines and the inflow at retail prices"""
        # taken before the plan, so a concurrent confirmation of this invoice or of its copy
        # waits and then sees the posted one instead of hitting the unique keys
        await self.ledger.lock()
        draft_invoice = await self._get_draft(
            invoice_id=invoice_id,
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
        # the ledger entry may only point to a confirmed invoice, so the status goes first
        draft_invoice.status = InvoiceStatus.CONFIRMED
        await self.invoices.flush()
        await self.invoices.add_items(
            items=items,
        )
        entry = await self.ledger.create(
            entry=LedgerEntry(
                kind=LedgerKind.INVOICE,
                amount=retail_total,
                invoice_id=draft_invoice.id,
                invoice_status=InvoiceStatus.CONFIRMED,
            ),
        )
        balance = await self.ledger.balance()
        await self.invoices.commit()
        return ConfirmedInvoice(
            id=draft_invoice.id,
            ledger_entry_id=entry.id,
            retail_total=retail_total,
            balance=balance,
        )

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
                ),
            )
        else:
            if product.markup_pct != line.markup_pct:
                product.markup_pct = line.markup_pct
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
            else SupplierSummary(
                id=plan.supplier.id,
                name=plan.supplier.name,
                inn=plan.supplier.inn,
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
        if not draft_invoice.corrections:
            form = await self._initial_form(
                draft_invoice=draft_invoice,
                extraction=extraction,
            )
        else:
            form = DraftForm.model_validate(
                obj=draft_invoice.corrections,
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
        for position, (form_line, alias) in enumerate(
            zip(
                form.lines,
                aliases,
                strict=True,
            ),
            start=1,
        ):
            plan.lines.append(
                await self._plan_line(
                    plan=plan,
                    position=position,
                    form_line=form_line,
                    alias=alias,
                    known=known,
                ),
            )
        await self._find_similar(
            plan=plan,
        )
        _price_lines(
            plan=plan,
        )

        for line in plan.lines:
            if line.position > len(extraction.items):
                continue
            read = extraction.items[line.position - 1]
            # the line is the one the model read, not added or moved by the user
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
                    for item, read_item in zip(
                        extraction.items,
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


def _candidate(
    supplier: Supplier,
    matched_lines: int,
) -> SupplierCandidate:
    return SupplierCandidate(
        id=supplier.id,
        name=supplier.name,
        inn=supplier.inn,
        matched_lines=matched_lines,
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
            ProductSummary(
                id=row.product.id,
                name=row.product.name,
                markup_pct=row.product.markup_pct,
                unit=row.last_item.unit if row.last_item else None,
                vat_percent=row.last_item.vat_percent if row.last_item else None,
                cost_price=row.last_item.cost_price if row.last_item else None,
                retail_price=row.last_item.retail_price if row.last_item else None,
            )
            for row in rows
        ]

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
            SupplierSummary(
                id=supplier.id,
                name=supplier.name,
                inn=supplier.inn,
            )
            for supplier in suppliers
        ]


InvoiceServiceDep = Annotated[
    InvoiceService,
    Depends(
        dependency=InvoiceService,
    ),
]
SupplierServiceDep = Annotated[
    SupplierService,
    Depends(
        dependency=SupplierService,
    ),
]
