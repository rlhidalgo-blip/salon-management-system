"""Read-only sale choices; Owner management endpoints stay separate."""

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import require_owner_or_cashier
from app.modules.catalog.models import Product, Service
from app.modules.commissions.models import CommissionRule
from app.modules.staff.models import Staff
from app.modules.transactions.attempt_feature import attempt_protocol_enabled


router = APIRouter(prefix="/api/v1/sales", tags=["sales"])


class StaffOption(BaseModel):
    id: int
    name: str
    role: str


class ServiceOption(BaseModel):
    id: int
    name: str
    current_price: Decimal
    allows_variable_price: bool


class ProductOption(BaseModel):
    id: int
    name: str
    current_price: Decimal


class SalesOptions(BaseModel):
    staff: list[StaffOption]
    services: list[ServiceOption]
    products: list[ProductOption]


class ManualStaffOption(BaseModel):
    id: int
    name: str
    role: str
    active: bool


class ManualCatalogOption(BaseModel):
    id: int
    name: str
    active: bool


class ManualSalesOptions(BaseModel):
    staff: list[ManualStaffOption]
    services: list[ManualCatalogOption]
    products: list[ManualCatalogOption]


class SalesCapabilities(BaseModel):
    protocol: Literal["legacy", "reserved_v1"]


@router.get("/capabilities", response_model=SalesCapabilities)
def get_sales_capabilities(response: Response, _principal=Depends(require_owner_or_cashier)):
    """Report the same process-stable protocol switch used by both sale writers."""
    response.headers["Cache-Control"] = "no-store"
    return SalesCapabilities(protocol="reserved_v1" if attempt_protocol_enabled() else "legacy")


@router.get("/options", response_model=SalesOptions)
def get_sales_options(response: Response, _principal=Depends(require_owner_or_cashier),
                      session: Session = Depends(get_db_session)):
    response.headers["Cache-Control"] = "no-store"
    staff = session.execute(select(Staff.id, Staff.name, Staff.role).where(Staff.active.is_(True))
                            .order_by(Staff.id)).all()
    services = session.execute(select(Service.id, Service.name, Service.current_price,
                                      Service.allows_variable_price).join(CommissionRule)
                               .where(Service.active.is_(True), CommissionRule.active.is_(True),
                                      CommissionRule.type == "Percentage").order_by(Service.id)).all()
    products = session.execute(select(Product.id, Product.name, Product.current_price).join(CommissionRule)
                               .where(Product.active.is_(True), CommissionRule.active.is_(True),
                                      CommissionRule.type == "Fixed").order_by(Product.id)).all()
    return SalesOptions(staff=[StaffOption.model_validate(row._mapping) for row in staff],
                        services=[ServiceOption.model_validate(row._mapping) for row in services],
                        products=[ProductOption.model_validate(row._mapping) for row in products])


@router.get("/manual-options", response_model=ManualSalesOptions)
def get_manual_sales_options(response: Response, _principal=Depends(require_owner_or_cashier),
                             session: Session = Depends(get_db_session)):
    """List current identities/statuses; historical validity requires separate evidence."""
    response.headers["Cache-Control"] = "no-store"
    staff = session.execute(select(Staff.id, Staff.name, Staff.role, Staff.active)
                            .order_by(Staff.id)).all()
    services = session.execute(select(Service.id, Service.name, Service.active)
                               .order_by(Service.id)).all()
    products = session.execute(select(Product.id, Product.name, Product.active)
                               .order_by(Product.id)).all()
    return ManualSalesOptions(
        staff=[ManualStaffOption.model_validate(row._mapping) for row in staff],
        services=[ManualCatalogOption.model_validate(row._mapping) for row in services],
        products=[ManualCatalogOption.model_validate(row._mapping) for row in products],
    )
