from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.concurrency import run_in_threadpool

import model_registry  # noqa: F401
from aqsi.router import router as aqsi_router
from auth.dependencies import get_current_user
from auth.router import router as auth_router
from core.health import router as health_router
from core.telemetry import is_health_check, setup_telemetry, shutdown_telemetry
from invoices.router import router as invoices_router
from ledger.router import router as ledger_router
from orders.router import router as orders_router
from products.router import router as products_router
from profit.router import router as profit_router
from recognition.client import close_client
from reports.router import router as reports_router
from suppliers.router import router as suppliers_router
from traffic.router import router as traffic_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    telemetry = setup_telemetry(
        serve_metrics=True,
    )
    try:
        yield
    finally:
        await close_client()
        await run_in_threadpool(
            func=shutdown_telemetry,
            telemetry=telemetry,
        )


# the docs and the schema are routes too, and they would describe the api to anyone
app = FastAPI(
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    # the providers come from setup_telemetry, FastAPI only uses them
    telemetry={
        "auto_configure": False,
        "exclude": is_health_check,
    },
)

app.include_router(
    router=health_router,
)

# a router added here is closed without a word in its own code
protected = APIRouter(
    dependencies=[
        Depends(
            dependency=get_current_user,
        ),
    ],
)

protected.include_router(
    router=invoices_router,
)
protected.include_router(
    router=suppliers_router,
)
protected.include_router(
    router=products_router,
)
protected.include_router(
    router=ledger_router,
)
protected.include_router(
    router=reports_router,
)
protected.include_router(
    router=orders_router,
)
protected.include_router(
    router=aqsi_router,
)
protected.include_router(
    router=traffic_router,
)
protected.include_router(
    router=profit_router,
)

app.include_router(
    router=protected,
)
# login and refresh are open, the auth router closes the other routes itself
app.include_router(
    router=auth_router,
)
