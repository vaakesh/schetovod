from collections.abc import Iterator
from datetime import UTC, datetime, tzinfo
from typing import Self
from unittest.mock import Mock

import jwt.api_jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth.dependencies import get_current_user
from auth.repository import AuthRepository
from core import config
from core.config import settings
from invoices.repository import InvoiceRepository
from ledger.repository import LedgerRepository
from main import app
from orders.repository import OrderRepository
from products.repository import ProductRepository
from suppliers.repository import SupplierRepository
from tests.fakes import (
    FakeAuth,
    FakeInvoices,
    FakeLedger,
    FakeOrders,
    FakeProducts,
    FakeReceipts,
    FakeStore,
    FakeSuppliers,
    signed_in_user,
)
from tests.fakes import invoices as fake_invoices
from traffic.repository import ReceiptRepository

FROZEN_NOW = datetime(
    year=2026,
    month=10,
    day=16,
    hour=9,
    tzinfo=UTC,
)


class FrozenDatetime(datetime):
    """PyJWT checks isinstance against datetime, a Mock there raises TypeError"""

    @classmethod
    def now(
        cls,
        tz: tzinfo | None = None,
    ) -> Self:
        return cls.fromtimestamp(
            FROZEN_NOW.timestamp(),
            tz=UTC,
        )


@pytest.fixture(
    autouse=True,
)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Mock(
        wraps=datetime,
    )
    clock.now.return_value = FROZEN_NOW

    monkeypatch.setattr(
        target=config,
        name="datetime",
        value=clock,
    )
    monkeypatch.setattr(
        target=fake_invoices,
        name="datetime",
        value=clock,
    )
    # PyJWT reads the time itself, a token of the frozen day looks expired by the real clock
    monkeypatch.setattr(
        target=jwt.api_jwt,
        name="datetime",
        value=FrozenDatetime,
    )
    monkeypatch.setattr(
        target=settings,
        name="timezone",
        value="Europe/Moscow",
    )


@pytest.fixture
def test_app() -> Iterator[FastAPI]:
    overrides = app.dependency_overrides.copy()
    try:
        yield app
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(
            overrides,
        )


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def repositories(test_app: FastAPI, store: FakeStore) -> None:
    test_app.dependency_overrides.update(
        {
            AuthRepository: lambda: FakeAuth(
                store=store,
            ),
            InvoiceRepository: lambda: FakeInvoices(
                store=store,
            ),
            SupplierRepository: lambda: FakeSuppliers(
                store=store,
            ),
            ProductRepository: lambda: FakeProducts(
                store=store,
            ),
            LedgerRepository: lambda: FakeLedger(
                store=store,
            ),
            OrderRepository: lambda: FakeOrders(
                store=store,
            ),
            ReceiptRepository: lambda: FakeReceipts(
                store=store,
            ),
        },
    )


@pytest.fixture
def client(test_app: FastAPI, repositories: None) -> Iterator[TestClient]:
    test_app.dependency_overrides[get_current_user] = signed_in_user
    with TestClient(
        app=test_app,
    ) as test_client:
        yield test_client


@pytest.fixture
def anonymous_client(
    test_app: FastAPI,
    repositories: None,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    """the real authorization: https because the cookies are secure"""
    monkeypatch.setattr(
        target=settings,
        name="auth_cookie_secure",
        value=True,
    )
    # the test client talks to the backend without the /api of nginx
    monkeypatch.setattr(
        target=settings,
        name="auth_refresh_cookie_path",
        value="/auth",
    )
    with TestClient(
        app=test_app,
        base_url="https://testserver",
    ) as test_client:
        yield test_client
