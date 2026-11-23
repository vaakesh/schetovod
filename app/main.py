from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.concurrency import run_in_threadpool

import model_registry  # noqa: F401
from aqsi.router import router as aqsi_router
from auth.dependencies import get_current_user
from auth.router import router as auth_router
from core.config import settings
from core.health import router as health_router
from core.store import Store, get_store
from core.telemetry import is_health_check, setup_telemetry, shutdown_telemetry
from invoices.router import router as invoices_router
from ledger.router import router as ledger_router
from orders.router import router as orders_router
from price_tags.router import router as price_tags_router
from products.router import router as products_router
from profit.router import router as profit_router
from purchases.router import router as purchases_router
from recognition.client import close_client
from reports.router import router as reports_router
from stocktakes.events import StocktakeEvents
from stocktakes.router import router as stocktakes_router
from stocktakes.websocket import router as stocktake_events_router
from suppliers.router import router as suppliers_router
from traffic.router import router as traffic_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    telemetry = setup_telemetry(
        serve_metrics=True,
    )
    app.state.stocktake_events = StocktakeEvents(
        database_url=settings.database_url,
    )
    try:
        yield
    finally:
        await app.state.stocktake_events.close()
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

store_routers = APIRouter(
    dependencies=[
        Depends(
            dependency=get_current_user,
        ),
    ],
)

store_routers.include_router(
    router=invoices_router,
)
store_routers.include_router(
    router=suppliers_router,
)
store_routers.include_router(
    router=products_router,
)
store_routers.include_router(
    router=ledger_router,
)
store_routers.include_router(
    router=reports_router,
)
store_routers.include_router(
    router=price_tags_router,
)

gastronom_routers = APIRouter(
    dependencies=[
        Depends(
            dependency=get_current_user,
        ),
    ],
)

gastronom_routers.include_router(
    router=orders_router,
)
gastronom_routers.include_router(
    router=stocktakes_router,
)
gastronom_routers.include_router(
    router=aqsi_router,
)
gastronom_routers.include_router(
    router=traffic_router,
)
gastronom_routers.include_router(
    router=profit_router,
)
gastronom_routers.include_router(
    router=purchases_router,
)

# the old paths use the gastronom database
app.include_router(
    router=store_routers,
)
app.include_router(
    router=gastronom_routers,
)
app.include_router(
    router=store_routers,
    prefix="/stores/{store}",
    dependencies=[
        Depends(
            dependency=get_store,
        ),
    ],
)
app.include_router(
    router=gastronom_routers,
    prefix=f"/stores/{Store.GASTRONOM}",
)
app.include_router(
    router=stocktake_events_router,
    prefix=f"/stores/{Store.GASTRONOM}",
)
# login and refresh are open, the auth router closes the other routes itself
app.include_router(
    router=auth_router,
)
