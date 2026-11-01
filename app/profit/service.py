from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, HTTPException, status

from core.config import today
from core.enums import ExpenseBasis, LedgerKind
from core.http import conflict, invalid
from invoices.repository import DayPurchases, InvoiceRepositoryDep
from ledger.repository import LedgerRepositoryDep
from profit import calculations
from profit.models import OperatingExpense
from profit.repository import ExpenseRepositoryDep
from profit.schemas import ExpenseForm, ExpenseOut, ProfitMonth, ProfitReport
from traffic.analytics import DayTakings
from traffic.repository import ReceiptRepositoryDep
from traffic.service import months_of

PERCENT_BASES = (
    ExpenseBasis.REVENUE_PERCENT,
    ExpenseBasis.CARD_PERCENT,
)


def check_form(payload: ExpenseForm) -> None:
    if not payload.amount:
        invalid(
            detail="Сумма должна быть больше нуля",
        )
    if payload.basis in PERCENT_BASES and payload.amount > calculations.HUNDRED:
        invalid(
            detail="Процент не может быть больше 100",
        )
    if payload.starts_on.day != 1:
        invalid(
            detail="Расход начинается с первого числа месяца",
        )


def new_expense(payload: ExpenseForm) -> OperatingExpense:
    return OperatingExpense(
        name=payload.name.strip(),
        basis=payload.basis,
        amount=payload.amount,
        starts_on=payload.starts_on,
    )


class ProfitService:
    def __init__(
        self,
        expenses: ExpenseRepositoryDep,
        receipts: ReceiptRepositoryDep,
        invoices: InvoiceRepositoryDep,
        ledger: LedgerRepositoryDep,
    ) -> None:
        self.expenses = expenses
        self.receipts = receipts
        self.invoices = invoices
        self.ledger = ledger

    async def report(self) -> ProfitReport:
        now = today()
        days = await self.receipts.daily_takings()
        purchases = await self.invoices.daily_purchases(
            date_from=calculations.COUNTED_ON,
        )
        expenses = await self.expenses.all()
        months = await self._months(
            now=now,
            days=days,
            purchases=purchases,
            expenses=expenses,
        )
        margin = calculations.margin_on(
            purchases=purchases,
            on=now,
        )
        return ProfitReport(
            last_receipt_at=await self.receipts.last_receipt_at(),
            months=months,
            average_profit=calculations.average_profit(
                months=months,
            ),
            break_even_day=self._break_even(
                now=now,
                days=days,
                expenses=expenses,
                purchases=purchases,
            ),
            margin=margin.out() if margin is not None else None,
            expenses=[
                ExpenseOut(
                    id=expense.id,
                    name=expense.name,
                    basis=expense.basis,
                    amount=expense.amount,
                    starts_on=expense.starts_on,
                )
                for expense in expenses
                if expense.ends_on is None
            ],
        )

    async def _months(
        self,
        now: date,
        days: list[DayTakings],
        purchases: list[DayPurchases],
        expenses: list[OperatingExpense],
    ) -> list[ProfitMonth]:
        if not days:
            return []
        months = []
        for month, last_day in months_of(
            date_from=calculations.month_start(
                day=days[0].day,
            ),
            date_to=now,
        ):
            margin = calculations.margin_on(
                purchases=purchases,
                on=last_day,
            )
            estimated = margin is None
            stock = await self._stock_sums(
                month=month,
                last_day=last_day,
            )
            months.append(
                calculations.profit_month(
                    month=month,
                    last_day=last_day,
                    takings=calculations.month_takings(
                        days=days,
                        date_from=month,
                        date_to=last_day,
                    ),
                    expenses=expenses,
                    margin=margin
                    or calculations.first_margin(
                        purchases=purchases,
                    ),
                    margin_estimated=estimated,
                    stock_difference=stock.get(
                        LedgerKind.STOCKTAKE,
                        calculations.ZERO,
                    ),
                    # the ledger keeps them negative
                    write_offs=-stock.get(
                        LedgerKind.WRITE_OFF,
                        calculations.ZERO,
                    ),
                ),
            )
        months.reverse()
        return months

    async def _stock_sums(
        self,
        month: date,
        last_day: date,
    ) -> dict[LedgerKind, Decimal]:
        """the first count only replaced a made-up balance, so the sums start after it"""
        date_from = max(
            month,
            calculations.COUNTED_ON
            + timedelta(
                days=1,
            ),
        )
        if date_from > last_day:
            return {}
        return await self.ledger.sums_by_kind(
            date_from=date_from,
            date_to=last_day,
        )

    def _break_even(
        self,
        now: date,
        days: list[DayTakings],
        expenses: list[OperatingExpense],
        purchases: list[DayPurchases],
    ) -> Decimal | None:
        """the last finished month gives the days and the card share, the rates are of today"""
        this_month = calculations.month_start(
            day=now,
        )
        last_day = this_month - timedelta(
            days=1,
        )
        return calculations.break_even_day(
            takings=calculations.month_takings(
                days=days,
                date_from=calculations.month_start(
                    day=last_day,
                ),
                date_to=last_day,
            ),
            expenses=calculations.in_force(
                expenses=expenses,
                month=this_month,
            ),
            margin=calculations.margin_on(
                purchases=purchases,
                on=now,
            ),
        )

    async def add_expense(
        self,
        payload: ExpenseForm,
    ) -> ProfitReport:
        check_form(
            payload=payload,
        )
        await self.expenses.add(
            expense=new_expense(
                payload=payload,
            ),
        )
        await self.expenses.commit()
        return await self.report()

    async def edit_expense(
        self,
        expense_id: int,
        payload: ExpenseForm,
    ) -> ProfitReport:
        """a change from a later month closes the old rate, the past keeps it"""
        check_form(
            payload=payload,
        )
        expense = await self._get_in_force(
            expense_id=expense_id,
        )
        if payload.starts_on < expense.starts_on:
            invalid(
                detail="Новая ставка не может начинаться раньше текущей",
            )
        if payload.starts_on == expense.starts_on:
            expense.name = payload.name.strip()
            expense.basis = payload.basis
            expense.amount = payload.amount
        else:
            expense.ends_on = payload.starts_on
            await self.expenses.add(
                expense=new_expense(
                    payload=payload,
                ),
            )
        await self.expenses.commit()
        return await self.report()

    async def stop_expense(
        self,
        expense_id: int,
    ) -> ProfitReport:
        """stops from this month on, a rate that never applied leaves no trace"""
        expense = await self._get_in_force(
            expense_id=expense_id,
        )
        this_month = calculations.month_start(
            day=today(),
        )
        if expense.starts_on >= this_month:
            await self.expenses.delete(
                expense=expense,
            )
        else:
            expense.ends_on = this_month
        await self.expenses.commit()
        return await self.report()

    async def _get_in_force(
        self,
        expense_id: int,
    ) -> OperatingExpense:
        expense = await self.expenses.get(
            expense_id=expense_id,
        )
        if expense is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Расход не найден",
            )
        if expense.ends_on is not None:
            conflict(
                detail="Этот расход уже не действует",
            )
        return expense


ProfitServiceDep = Annotated[
    ProfitService,
    Depends(
        dependency=ProfitService,
    ),
]
