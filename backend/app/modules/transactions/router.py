"""Owner/Cashier direct current-day sale endpoint."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import Principal, require_owner_or_cashier
from app.modules.transactions.schemas import SaleCreate, SalePublic, SaleKeyStatus
from app.modules.transactions.service import lookup_sale_key, record_direct_sale


router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])


@router.get("/by-idempotency-key/{idempotency_key}", response_model=SaleKeyStatus)
def get_sale_key_status(idempotency_key: UUID, response: Response,
                        principal: Principal = Depends(require_owner_or_cashier),
                        session: Session = Depends(get_db_session)):
    response.headers["Cache-Control"] = "no-store"
    with session.begin():
        status, sale = lookup_sale_key(session, actor_user_id=principal.user_id,
                                       idempotency_key=idempotency_key)
    if status == "processing":
        response.status_code = 202
    return SaleKeyStatus(status=status, sale=sale)


@router.post("", response_model=SalePublic, status_code=201)
def post_direct_sale(payload: SaleCreate, response: Response,
                     idempotency_key: UUID = Header(alias="Idempotency-Key"),
                     principal: Principal = Depends(require_owner_or_cashier),
                     session: Session = Depends(get_db_session)):
    with session.begin():
        result, replayed = record_direct_sale(session, payload, actor_user_id=principal.user_id,
                                              idempotency_key=idempotency_key)
    # Context manager has committed before either success status is returned.
    if replayed:
        response.status_code = 200
    return result
