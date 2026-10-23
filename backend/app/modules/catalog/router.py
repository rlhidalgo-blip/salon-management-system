"""Owner-only Services and Products catalog API."""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import Principal, require_owner
from app.modules.catalog.schemas import (
    CatalogStatus, ProductCreate, ProductPublic, ProductUpdate,
    ServiceCreate, ServicePublic, ServiceUpdate,
)
from app.modules.catalog.service import change_item, create_item, list_items


router = APIRouter(prefix="/api/v1", tags=["catalog"])


@router.get("/services", response_model=list[ServicePublic])
def get_services(_principal: Principal = Depends(require_owner), session: Session = Depends(get_db_session)):
    with session.begin():
        return [ServicePublic.model_validate(item) for item in list_items(session, "service")]


@router.post("/services", response_model=ServicePublic, status_code=201)
def post_service(payload: ServiceCreate, _principal: Principal = Depends(require_owner),
                 session: Session = Depends(get_db_session)):
    with session.begin():
        return ServicePublic.model_validate(create_item(session, "service", **payload.model_dump()))


@router.patch("/services/{item_id}", response_model=ServicePublic)
def patch_service(payload: ServiceUpdate, item_id: int = Path(gt=0), _principal: Principal = Depends(require_owner),
                  session: Session = Depends(get_db_session)):
    with session.begin():
        return ServicePublic.model_validate(change_item(session, "service", item_id,
                                                         changes=payload.model_dump(exclude_unset=True)))


@router.patch("/services/{item_id}/status", response_model=ServicePublic)
def patch_service_status(payload: CatalogStatus, item_id: int = Path(gt=0),
                         _principal: Principal = Depends(require_owner), session: Session = Depends(get_db_session)):
    with session.begin():
        return ServicePublic.model_validate(change_item(session, "service", item_id, changes={"active": payload.active}))


@router.get("/products", response_model=list[ProductPublic])
def get_products(_principal: Principal = Depends(require_owner), session: Session = Depends(get_db_session)):
    with session.begin():
        return [ProductPublic.model_validate(item) for item in list_items(session, "product")]


@router.post("/products", response_model=ProductPublic, status_code=201)
def post_product(payload: ProductCreate, _principal: Principal = Depends(require_owner),
                 session: Session = Depends(get_db_session)):
    with session.begin():
        return ProductPublic.model_validate(create_item(session, "product", **payload.model_dump()))


@router.patch("/products/{item_id}", response_model=ProductPublic)
def patch_product(payload: ProductUpdate, item_id: int = Path(gt=0), _principal: Principal = Depends(require_owner),
                  session: Session = Depends(get_db_session)):
    with session.begin():
        return ProductPublic.model_validate(change_item(session, "product", item_id,
                                                         changes=payload.model_dump(exclude_unset=True)))


@router.patch("/products/{item_id}/status", response_model=ProductPublic)
def patch_product_status(payload: CatalogStatus, item_id: int = Path(gt=0),
                         _principal: Principal = Depends(require_owner), session: Session = Depends(get_db_session)):
    with session.begin():
        return ProductPublic.model_validate(change_item(session, "product", item_id, changes={"active": payload.active}))
