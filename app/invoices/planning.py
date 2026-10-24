from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from invoices.calculations import (
    LinePrices,
    block,
    check_read_prices,
    check_revaluation,
    check_totals,
    line_prices,
    price_lines,
    to_kopecks,
)
from invoices.extraction import InvoiceExtraction
from invoices.forms import initial_form, number_form_lines, numbered_extraction
from invoices.matching import find_similar, suggest_suppliers
from invoices.models import Invoice
from invoices.repository import InvoiceRepository
from invoices.schemas import (
    DraftForm,
    FormLine,
    Issue,
    NewSupplier,
    SimilarProduct,
    SupplierCandidate,
    SupplierRef,
)
from products.models import Product
from products.pricing import normalize_name
from products.repository import ProductRepository
from suppliers.models import Supplier
from suppliers.repository import SupplierRepository

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


class InvoicePlanner:
    def __init__(
        self,
        invoices: InvoiceRepository,
        suppliers: SupplierRepository,
        products: ProductRepository,
    ) -> None:
        self.invoices = invoices
        self.suppliers = suppliers
        self.products = products

    async def plan(
        self,
        draft_invoice: Invoice,
    ) -> DraftPlan:
        extraction = InvoiceExtraction.model_validate(
            obj=draft_invoice.extracted,
        )
        numbered_items = numbered_extraction(
            extraction=extraction,
        )
        if draft_invoice.form is None:
            form = await initial_form(
                suppliers=self.suppliers,
                draft_invoice=draft_invoice,
                extraction=extraction,
                numbered_items=numbered_items,
            )
        else:
            form = DraftForm.model_validate(
                obj=draft_invoice.form,
            )
        number_form_lines(
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
            block(
                plan=plan,
                message="номер накладной не указан",
            )
        if form.invoice_date is None:
            block(
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
                block(
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
                block(
                    plan=plan,
                    message=f"продавец с ИНН {form.supplier.inn} уже есть, выберите его",
                )
            else:
                # a new supplier has no products yet
                plan.catalog_known = True
                plan.candidates = await suggest_suppliers(
                    suppliers=self.suppliers,
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
            block(
                plan=plan,
                message="продавец не выбран",
            )
            plan.candidates = await suggest_suppliers(
                suppliers=self.suppliers,
                name=extraction.supplier.name,
                inn=extraction.supplier.inn,
                aliases=known_aliases,
            )
        if not form.lines:
            block(
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
        await find_similar(
            products=self.products,
            plan=plan,
        )
        await self._compare_costs(
            plan=plan,
        )
        price_lines(
            plan=plan,
        )
        check_revaluation(
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
                block(
                    plan=plan,
                    message=f"эта накладная уже проведена под номером {same.id}",
                )
        return plan

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
                block(
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
                block(
                    plan=plan,
                    message=f"у продавца нет товара с id {form_line.product_id}",
                    line=position,
                )
            elif alias is not None and alias in known:
                linked = known[alias].id == product.id
                if not linked:
                    block(
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
