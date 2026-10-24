from typing import Annotated

from fastapi import APIRouter, Query

from core.http import PageLimit, PageOffset
from core.schema_types import InvoiceDate
from ledger.revaluation import RevaluationServiceDep
from ledger.schemas import (
    CashCountCreate,
    CashOutCreate,
    LedgerBalance,
    LedgerPage,
    LedgerPosted,
    OutflowCreate,
    RevaluationCreate,
    RevaluationLineOut,
    SaleCreate,
    StocktakeCreate,
)
from ledger.service import LedgerServiceDep

router = APIRouter()


@router.get(
    path="/ledger",
    response_model=LedgerPage,
)
async def ledger_history(
    service: LedgerServiceDep,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> LedgerPage:
    return await service.history(
        limit=limit,
        offset=offset,
    )


@router.get(
    path="/ledger/balance",
    response_model=LedgerBalance,
)
async def ledger_balance(
    service: LedgerServiceDep,
    on: Annotated[
        InvoiceDate | None,
        Query(),
    ] = None,
) -> LedgerBalance:
    return await service.balance_on(
        on=on,
    )


@router.post(
    path="/ledger/sale",
    response_model=LedgerPosted,
)
async def add_sale(
    payload: SaleCreate,
    service: LedgerServiceDep,
) -> LedgerPosted:
    return await service.add_sale(
        payload=payload,
    )


@router.post(
    path="/ledger/write-off",
    response_model=LedgerPosted,
)
async def add_write_off(
    payload: OutflowCreate,
    service: LedgerServiceDep,
) -> LedgerPosted:
    return await service.add_write_off(
        payload=payload,
    )


@router.post(
    path="/ledger/cash-in",
    response_model=LedgerPosted,
)
async def add_cash_in(
    payload: OutflowCreate,
    service: LedgerServiceDep,
) -> LedgerPosted:
    return await service.add_cash_in(
        payload=payload,
    )


@router.post(
    path="/ledger/cash-out",
    response_model=LedgerPosted,
)
async def add_cash_out(
    payload: CashOutCreate,
    service: LedgerServiceDep,
) -> LedgerPosted:
    return await service.add_cash_out(
        payload=payload,
    )


@router.post(
    path="/ledger/cash-count",
    response_model=LedgerPosted,
)
async def add_cash_count(
    payload: CashCountCreate,
    service: LedgerServiceDep,
) -> LedgerPosted:
    return await service.add_cash_count(
        payload=payload,
    )


@router.post(
    path="/ledger/stocktake",
    response_model=LedgerPosted,
)
async def add_stocktake(
    payload: StocktakeCreate,
    service: LedgerServiceDep,
) -> LedgerPosted:
    return await service.add_stocktake(
        payload=payload,
    )


@router.post(
    path="/ledger/revaluation",
    response_model=LedgerPosted,
)
async def add_revaluation(
    payload: RevaluationCreate,
    service: RevaluationServiceDep,
) -> LedgerPosted:
    return await service.add_revaluation(
        payload=payload,
    )


@router.get(
    path="/ledger/{entry_id}/revaluation",
    response_model=list[RevaluationLineOut],
)
async def revaluation_lines(
    entry_id: int,
    service: RevaluationServiceDep,
) -> list[RevaluationLineOut]:
    return await service.revaluation_lines(
        entry_id=entry_id,
    )


@router.post(
    path="/ledger/{entry_id}/reverse",
    response_model=LedgerPosted,
)
async def reverse_entry(
    entry_id: int,
    service: LedgerServiceDep,
) -> LedgerPosted:
    return await service.reverse(
        entry_id=entry_id,
    )
