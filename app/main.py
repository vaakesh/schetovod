from fastapi import FastAPI

import model_registry  # noqa: F401
from invoices.router import router as invoices_router
from ledger.router import router as ledger_router
from products.router import router as products_router
from reports.router import router as reports_router
from suppliers.router import router as suppliers_router

app = FastAPI()

app.include_router(
    router=invoices_router,
)
app.include_router(
    router=suppliers_router,
)
app.include_router(
    router=products_router,
)
app.include_router(
    router=ledger_router,
)
app.include_router(
    router=reports_router,
)
