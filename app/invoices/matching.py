from __future__ import annotations

from typing import TYPE_CHECKING

from invoices.schemas import Issue, SimilarProduct, SupplierCandidate
from products.models import Product
from products.pricing import SIMILAR_NAME_RATIO, name_similarity
from products.repository import ProductRepository
from suppliers.models import Supplier
from suppliers.repository import SupplierRepository

if TYPE_CHECKING:
    from invoices.planning import DraftPlan


CANDIDATES_LIMIT = 5
SIMILAR_LIMIT = 3
SIMILAR_PRODUCT = "similar_product"


async def find_similar(
    products: ProductRepository,
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
    catalog = await products.aliases_of(
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
            if ratio >= SIMILAR_NAME_RATIO and (closest is None or ratio > closest[0]):
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


async def suggest_suppliers(
    suppliers: SupplierRepository,
    name: str | None,
    inn: str | None,
    aliases: set[str],
) -> list[SupplierCandidate]:
    # with an inn that nobody has, a supplier with another inn is someone else
    only_without_inn = inn is not None
    ranked = await suppliers.rank_by_aliases(
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
        by_name = await suppliers.search_by_name(
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
