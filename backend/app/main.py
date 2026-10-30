from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.core.exceptions import install_error_handlers
from app.core.startup import validate_startup_configuration
from app.core.static import frontend_response
from app.modules.auth.router import router as auth_router
from app.modules.catalog.router import router as catalog_router
from app.modules.commissions.router import router as commission_rules_router
from app.modules.staff.router import router as staff_router
from app.modules.reports.router import router as reports_router
from app.modules.transactions.router import router as transactions_router
from app.modules.transactions.options_router import router as sales_options_router
from app.modules.transactions.attempt_router import router as sale_attempts_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_startup_configuration()
    yield


app = FastAPI(title="Yab's Salon Management System API", lifespan=lifespan)
install_error_handlers(app)


@app.middleware("http")
async def sale_attempt_no_store(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/v1/sales/attempts"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(auth_router)
app.include_router(staff_router)
app.include_router(commission_rules_router)
app.include_router(catalog_router)
app.include_router(transactions_router)
app.include_router(sales_options_router)
app.include_router(sale_attempts_router)
app.include_router(reports_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route(
    "/api/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
def unknown_api(path: str):
    raise HTTPException(status_code=404, detail="Not Found")


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    return frontend_response(path)
