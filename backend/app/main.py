from fastapi import FastAPI

from app.core.exceptions import install_error_handlers
from app.modules.auth.router import router as auth_router
from app.modules.commissions.router import router as commission_rules_router
from app.modules.staff.router import router as staff_router


app = FastAPI(title="Yab's Salon Management System API")
install_error_handlers(app)
app.include_router(auth_router)
app.include_router(staff_router)
app.include_router(commission_rules_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
