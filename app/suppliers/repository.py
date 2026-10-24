from collections.abc import Collection
from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, or_, select

from core.db import SessionDep
from products.models import ProductAlias
from suppliers.models import Supplier


class SupplierRepository:
    def __init__(
        self,
        session: SessionDep,
    ) -> None:
        self.session = session

    async def get(
        self,
        supplier_id: int,
    ) -> Supplier | None:
        return await self.session.get(
            entity=Supplier,
            ident=supplier_id,
        )

    async def get_by_inn(
        self,
        inn: str,
    ) -> Supplier | None:
        return await self.session.scalar(
            statement=select(
                Supplier,
            ).where(
                Supplier.inn == inn,
            ),
        )

    async def search_by_name(
        self,
        name: str,
        only_without_inn: bool,
        limit: int,
    ) -> list[Supplier]:
        statement = (
            select(
                Supplier,
            )
            .where(
                Supplier.name.icontains(
                    other=name,
                    autoescape=True,
                ),
            )
            .order_by(
                Supplier.id,
            )
            .limit(
                limit=limit,
            )
        )
        if only_without_inn:
            statement = statement.where(
                Supplier.inn.is_(
                    other=None,
                ),
            )
        result = await self.session.scalars(
            statement=statement,
        )
        return list(
            result,
        )

    async def search(
        self,
        query: str | None,
        limit: int,
    ) -> list[Supplier]:
        """suppliers by a part of the name or the start of the inn, all of them without a query"""
        statement = (
            select(
                Supplier,
            )
            .order_by(
                Supplier.name,
                Supplier.id,
            )
            .limit(
                limit=limit,
            )
        )
        if query:
            by_name = Supplier.name.icontains(
                other=query,
                autoescape=True,
            )
            if query.isdigit():
                statement = statement.where(
                    or_(
                        by_name,
                        Supplier.inn.startswith(
                            other=query,
                            autoescape=True,
                        ),
                    ),
                )
            else:
                statement = statement.where(
                    by_name,
                )
        result = await self.session.scalars(
            statement=statement,
        )
        return list(
            result,
        )

    async def list_all(self) -> list[Supplier]:
        result = await self.session.scalars(
            statement=select(
                Supplier,
            ).order_by(
                Supplier.name,
                Supplier.id,
            ),
        )
        return list(
            result,
        )

    async def commit(self) -> None:
        await self.session.commit()

    async def rank_by_aliases(
        self,
        aliases: Collection[str],
        only_without_inn: bool,
        limit: int,
    ) -> list[tuple[Supplier, int]]:
        """suppliers that have products with these names, most matches first"""
        if not aliases:
            return []
        matched = func.count(
            ProductAlias.alias_normalized.distinct(),
        )
        statement = (
            select(
                Supplier,
                matched,
            )
            .join(
                target=ProductAlias,
                onclause=ProductAlias.supplier_id == Supplier.id,
            )
            .where(
                ProductAlias.alias_normalized.in_(
                    other=aliases,
                ),
            )
            .group_by(
                Supplier.id,
            )
            .order_by(
                matched.desc(),
                Supplier.id,
            )
            .limit(
                limit=limit,
            )
        )
        if only_without_inn:
            statement = statement.where(
                Supplier.inn.is_(
                    other=None,
                ),
            )
        result = await self.session.execute(
            statement=statement,
        )
        return list(
            result.tuples(),
        )

    async def create(
        self,
        supplier: Supplier,
    ) -> Supplier:
        self.session.add(
            instance=supplier,
        )
        await self.session.flush()
        return supplier


SupplierRepositoryDep = Annotated[
    SupplierRepository,
    Depends(
        dependency=SupplierRepository,
    ),
]
