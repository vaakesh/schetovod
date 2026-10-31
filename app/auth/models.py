from __future__ import annotations

from sqlalchemy import ForeignKey, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base
from core.db_types import BigInt, DateTimeTz


class User(Base):
    __tablename__ = "users"

    id: Mapped[BigInt] = mapped_column(
        primary_key=True,
        nullable=False,
    )
    # stored in lower case, see normalize_login
    login: Mapped[str] = mapped_column(
        nullable=False,
        unique=True,
    )
    password_hash: Mapped[str] = mapped_column(
        nullable=False,
    )
    # a blocked user can not sign in and loses the open sessions at once
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default=true(),
    )
    created_at: Mapped[DateTimeTz] = mapped_column(
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[DateTimeTz] = mapped_column(
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )


class UserSession(Base):
    """one signed in device, the tokens only point to it and it can be revoked"""

    __tablename__ = "user_sessions"

    id: Mapped[BigInt] = mapped_column(
        primary_key=True,
        nullable=False,
    )
    user_id: Mapped[BigInt] = mapped_column(
        ForeignKey(
            column="users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    # the id of the only refresh token that may be exchanged
    refresh_jti: Mapped[str] = mapped_column(
        nullable=False,
    )
    # the token before the last exchange, another tab may be sending it right now
    previous_refresh_jti: Mapped[str | None] = mapped_column(
        nullable=True,
    )
    rotated_at: Mapped[DateTimeTz | None] = mapped_column(
        nullable=True,
    )
    expires_at: Mapped[DateTimeTz] = mapped_column(
        nullable=False,
    )
    revoked_at: Mapped[DateTimeTz | None] = mapped_column(
        nullable=True,
    )
    created_at: Mapped[DateTimeTz] = mapped_column(
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[DateTimeTz] = mapped_column(
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(
        lazy="raise",
    )
