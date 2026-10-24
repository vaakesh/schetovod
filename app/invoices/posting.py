from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, HTTPException, status

from core.enums import InvoiceStatus, LedgerKind
from invoices.calculations import issue_text, sum_known, to_kopecks
from invoices.models import Invoice, InvoiceItem
from invoices.planning import InvoicePlanner, PlannedLine, ProductKey
from invoices.queries import get_draft_invoice
from invoices.repository import InvoiceRepositoryDep
from invoices.schemas import ConfirmedInvoice, NewSupplier
from ledger.models import LedgerEntry, RevaluationItem
from ledger.repository import LedgerRepositoryDep
from ledger.rules import check_date
from products.models import Product, ProductAlias
from products.pricing import (
    reprice,
    revaluation_amount,
)
from products.repository import ProductRepositoryDep
from suppliers.models import Supplier
from suppliers.repository import SupplierRepositoryDep


class InvoicePostingService:
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
        self.planner = InvoicePlanner(
            invoices=invoices,
            suppliers=suppliers,
            products=products,
        )

    async def confirm_invoice(
        self,
        invoice_id: int,
        occurred_on: date,
    ) -> ConfirmedInvoice:
        """writes the catalog changes, the lines and the inflow at retail prices"""
        # taken before the plan, so a concurrent confirmation of this invoice or of its copy
        # waits and then sees the posted one instead of hitting the unique keys
        await self.ledger.lock()
        draft_invoice = await get_draft_invoice(
            invoices=self.invoices,
            invoice_id=invoice_id,
        )
        # the day the goods came, it may be earlier than the confirmation
        await check_date(
            ledger=self.ledger,
            on=occurred_on,
            stock=True,
            cash=False,
        )
        plan = await self.planner.plan(
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
                    issue_text(
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
            reprice(
                product=product,
                price=line.retail_price,
            )
        products[line.key] = product
        return product


InvoicePostingServiceDep = Annotated[
    InvoicePostingService,
    Depends(
        dependency=InvoicePostingService,
    ),
]


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
