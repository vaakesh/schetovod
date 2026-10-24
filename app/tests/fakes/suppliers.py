from collections.abc import Collection

from suppliers.models import Supplier
from tests.fakes.store import FakeStore


class FakeSuppliers:
    def __init__(
        self,
        store: FakeStore,
    ) -> None:
        self.store = store

    async def commit(self) -> None:
        self.store.commits += 1

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

    async def list_all(self) -> list[Supplier]:
        return sorted(
            self.store.suppliers.values(),
            key=lambda supplier: (supplier.name, supplier.id),
        )

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
                    (
                        supplier,
                        len(
                            matched,
                        ),
                    ),
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
