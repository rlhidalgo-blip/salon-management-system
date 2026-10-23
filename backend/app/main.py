from fastapi import FastAPI

from app.core.exceptions import install_error_handlers
from app.modules.auth.router import router as auth_router
from app.modules.catalog.router import router as catalog_router
from app.modules.commissions.router import router as commission_rules_router
from app.modules.staff.router import router as staff_router
from app.modules.transactions.router import router as transactions_router
from app.modules.transactions.options_router import router as sales_options_router


app = FastAPI(title="Yab's Salon Management System API")
install_error_handlers(app)
app.include_router(auth_router)
app.include_router(staff_router)
app.include_router(commission_rules_router)
app.include_router(catalog_router)
app.include_router(transactions_router)
app.include_router(sales_options_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
