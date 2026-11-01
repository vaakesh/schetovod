from fastapi import APIRouter

from profit.schemas import ExpenseForm, ProfitReport
from profit.service import ProfitServiceDep

router = APIRouter()


@router.get(
    path="/profit",
    response_model=ProfitReport,
)
async def profit_report(
    service: ProfitServiceDep,
) -> ProfitReport:
    return await service.report()


@router.post(
    path="/profit/expenses",
    response_model=ProfitReport,
)
async def add_expense(
    payload: ExpenseForm,
    service: ProfitServiceDep,
) -> ProfitReport:
    return await service.add_expense(
        payload=payload,
    )


@router.put(
    path="/profit/expenses/{expense_id}",
    response_model=ProfitReport,
)
async def edit_expense(
    expense_id: int,
    payload: ExpenseForm,
    service: ProfitServiceDep,
) -> ProfitReport:
    return await service.edit_expense(
        expense_id=expense_id,
        payload=payload,
    )


@router.delete(
    path="/profit/expenses/{expense_id}",
    response_model=ProfitReport,
)
async def stop_expense(
    expense_id: int,
    service: ProfitServiceDep,
) -> ProfitReport:
    return await service.stop_expense(
        expense_id=expense_id,
    )
