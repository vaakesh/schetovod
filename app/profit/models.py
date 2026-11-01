from datetime import date

from sqlalchemy import CheckConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base
from core.db_types import BigInt, DateTimeTz, Money, expense_basis_enum
from core.enums import ExpenseBasis


class OperatingExpense(Base):
    """a cost of running the shop, a new rate is a new row so past months keep the old one"""

    __tablename__ = "operating_expenses"

    id: Mapped[BigInt] = mapped_column(
        primary_key=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        nullable=False,
    )
    basis: Mapped[ExpenseBasis] = mapped_column(
        expense_basis_enum,
        nullable=False,
    )
    # rubles or a percent, the basis says which
    amount: Mapped[Money] = mapped_column(
        CheckConstraint(
            sqltext="amount > 0",
            name="amount",
        ),
        nullable=False,
    )
    # the first month it applies to, stored as the first day of that month
    starts_on: Mapped[date] = mapped_column(
        CheckConstraint(
            sqltext="extract(day from starts_on) = 1",
            name="starts_on",
        ),
        nullable=False,
    )
    # the first month it no longer applies to, None while it is in force
    ends_on: Mapped[date | None] = mapped_column(
        CheckConstraint(
            sqltext="extract(day from ends_on) = 1",
            name="ends_on",
        ),
        nullable=True,
    )
    created_at: Mapped[DateTimeTz] = mapped_column(
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )

    __table_args__ = (
        # a rate that ends before it starts would never apply
        CheckConstraint(
            sqltext="ends_on IS NULL OR ends_on > starts_on",
            name="period",
        ),
        # a percent can not take more than the whole base
        CheckConstraint(
            sqltext=(
                f"basis NOT IN ('{ExpenseBasis.REVENUE_PERCENT}', "
                f"'{ExpenseBasis.CARD_PERCENT}') OR amount <= 100"
            ),
            name="percent",
        ),
    )
