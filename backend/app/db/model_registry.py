from importlib import import_module

from sqlalchemy import MetaData

from app.db.base import Base


# Add feature model module paths here as each approved model is implemented.
MODEL_MODULES: tuple[str, ...] = (
    "app.modules.users.models",
    "app.modules.staff.models",
    "app.modules.commissions.models",
    "app.modules.catalog.models",
    "app.modules.transactions.models",
    "app.modules.auth.models",
    "app.modules.audit.models",
    "app.modules.transactions.idempotency_models",
    "app.modules.transactions.attempt_models",
)


def get_model_metadata() -> MetaData:
    for module_name in MODEL_MODULES:
        import_module(module_name)
    return Base.metadata
