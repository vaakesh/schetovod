from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException

from aqsi.client import AqsiClientDep
from aqsi.schemas import (
    AqsiClosedReport,
    AqsiCounters,
    AqsiShift,
    ImportedShift,
    ShiftImportCreate,
    ShiftImportResult,
    SkippedShift,
)
from core.config import settings
from core.enums import LedgerKind
from core.http import invalid
from ledger.models import LedgerEntry
from ledger.repository import LedgerRepositoryDep
from ledger.rules import check_date

NOT_CLOSED = "смена ещё не закрыта"
NOT_DATED = "нет отчёта об открытии смены"
ALREADY_LOADED = "смена уже загружена"
UNSUPPORTED = (
    "есть расход, коррекция или оплата кроме наличных и безнала, занесите вручную"
)
NOT_A_SALE = "возвраты больше продаж, занесите вручную"


@dataclass
class ShiftSale:
    cash: Decimal
    card: Decimal


def rubles(kopecks: int) -> Decimal:
    return Decimal(
        value=kopecks,
    ).scaleb(
        other=-2,
    )


def opened_on(shift: AqsiShift) -> date | None:
    """a shift goes to the day it was opened, it may close on the next one"""
    report = shift.shift_opened_report
    if report is None:
        return None
    return report.date_time.astimezone(
        tz=ZoneInfo(
            key=settings.timezone,
        ),
    ).date()


def has_other_payments(counters: AqsiCounters) -> bool:
    return bool(
        counters.prepayment or counters.credit or counters.consideration,
    )


def is_supported(report: AqsiClosedReport) -> bool:
    """a sale of the ledger holds only the cash and the card takings"""
    counters = report.shift_counters
    corrections = counters.corrections
    return not (
        counters.expense.total
        or counters.expense_refund.total
        or corrections.income.total
        or corrections.income_refund.total
        or corrections.expense.total
        or corrections.expense_refund.total
        or has_other_payments(
            counters=counters.income,
        )
        or has_other_payments(
            counters=counters.income_refund,
        )
    )


def has_takings(report: AqsiClosedReport) -> bool:
    counters = report.shift_counters
    return bool(
        counters.income.total or counters.income_refund.total,
    )


def shift_sale(report: AqsiClosedReport) -> ShiftSale | None:
    """the takings without the refunds, None when they do not make a sale"""
    counters = report.shift_counters
    cash = counters.income.cash - counters.income_refund.cash
    card = counters.income.cashless - counters.income_refund.cashless
    if cash < 0 or card < 0 or cash + card == 0:
        return None
    return ShiftSale(
        cash=rubles(
            kopecks=cash,
        ),
        card=rubles(
            kopecks=card,
        ),
    )


class ShiftImportService:
    def __init__(
        self,
        ledger: LedgerRepositoryDep,
        aqsi: AqsiClientDep,
    ) -> None:
        self.ledger = ledger
        self.aqsi = aqsi

    async def load(
        self,
        payload: ShiftImportCreate,
    ) -> ShiftImportResult:
        """one sale for each closed shift, manual sales of the same days stay as they are"""
        if payload.date_from > payload.date_to:
            invalid(
                detail="Начало периода позже конца",
            )
        # the ledger is locked after the requests, they must not hold it up
        shifts = await self.aqsi.shifts(
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
        await self.ledger.lock()
        present = await self.ledger.aqsi_shifts_present(
            shift_ids=[shift.id for shift in shifts],
        )
        result = ShiftImportResult(
            imported=[],
            skipped=[],
        )
        for shift in sorted(
            shifts,
            key=lambda shift: shift.number,
        ):
            await self._load_shift(
                shift=shift,
                loaded=shift.id in present,
                result=result,
            )
        await self.ledger.commit()
        return result

    async def _load_shift(
        self,
        shift: AqsiShift,
        loaded: bool,
        result: ShiftImportResult,
    ) -> None:
        on = opened_on(
            shift=shift,
        )
        report = shift.shift_closed_report

        def skip(reason: str) -> None:
            result.skipped.append(
                SkippedShift(
                    shift_number=shift.number,
                    occurred_on=on,
                    reason=reason,
                ),
            )

        if loaded:
            skip(
                reason=ALREADY_LOADED,
            )
            return
        if report is None:
            skip(
                reason=NOT_CLOSED,
            )
            return
        if on is None:
            skip(
                reason=NOT_DATED,
            )
            return
        if not has_takings(
            report=report,
        ) and is_supported(
            report=report,
        ):
            # an empty shift has nothing to enter
            return
        if not is_supported(
            report=report,
        ):
            skip(
                reason=UNSUPPORTED,
            )
            return
        sale = shift_sale(
            report=report,
        )
        if sale is None:
            skip(
                reason=NOT_A_SALE,
            )
            return
        try:
            await check_date(
                ledger=self.ledger,
                on=on,
                stock=True,
                cash=sale.cash > 0,
            )
        except HTTPException as error:
            skip(
                reason=error.detail,
            )
            return
        entry = await self.ledger.create(
            entry=LedgerEntry(
                kind=LedgerKind.SALE,
                occurred_on=on,
                amount=-(sale.cash + sale.card),
                cash=sale.cash,
                comment=f"Смена aQsi №{shift.number}",
                aqsi_shift_id=shift.id,
            ),
        )
        result.imported.append(
            ImportedShift(
                entry_id=entry.id,
                shift_number=shift.number,
                occurred_on=on,
                cash=sale.cash,
                card=sale.card,
            ),
        )


ShiftImportServiceDep = Annotated[
    ShiftImportService,
    Depends(
        dependency=ShiftImportService,
    ),
]
