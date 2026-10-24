from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import config
from core.config import settings
from invoices.repository import InvoiceRepository
from ledger.repository import LedgerRepository
from main import app
from products.repository import ProductRepository
from suppliers.repository import SupplierRepository
from tests.fakes import FakeInvoices, FakeLedger, FakeProducts, FakeStore, FakeSuppliers
from tests.fakes import invoices as fake_invoices


@pytest.fixture(
    autouse=True,
)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Mock(
        wraps=datetime,
    )
    clock.now.return_value = datetime(
        year=2026,
        month=10,
        day=16,
        hour=9,
        tzinfo=UTC,
    )

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
def client(test_app: FastAPI, store: FakeStore) -> Iterator[TestClient]:
    test_app.dependency_overrides.update(
        {
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
        },
    )
    with TestClient(
        app=test_app,
    ) as test_client:
        yield test_client
