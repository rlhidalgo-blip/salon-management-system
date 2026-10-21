from fastapi import FastAPI

from app.core.exceptions import install_error_handlers
from app.modules.auth.router import router as auth_router


app = FastAPI(title="Yab's Salon Management System API")
install_error_handlers(app)
app.include_router(auth_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
