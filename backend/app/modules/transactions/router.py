"""Direct sales, date-scoped history, and Owner-only voiding."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.db.session import get_db_session
from app.modules.auth.dependencies import Principal, require_owner, require_owner_or_cashier
from app.modules.transactions.history_schemas import VoidRequest
from app.modules.transactions.history_service import (
    get_history_detail, list_history, record_rejected_void, void_transaction,
)
from app.modules.transactions.manual_service import record_manual_sale
from app.modules.transactions.reconciliation_service import (
    acknowledge_sale, investigate_sale, reject_acknowledgment,
)
from app.modules.transactions.schemas import ManualSaleCreate, SaleCreate, SalePublic, SaleKeyStatus, SaleAcknowledgment
from app.modules.transactions.service import lookup_sale_key, record_direct_sale


router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])


@router.get("/reconciliation/{recording_user_id}/{idempotency_key}", response_model=SaleKeyStatus)
def get_owner_sale_status(response: Response, recording_user_id: int = Path(gt=0),
                          idempotency_key: UUID = Path(),
                          principal: Principal = Depends(require_owner),
                          session: Session = Depends(get_db_session)):
    response.headers["Cache-Control"] = "no-store"
    with session.begin():
        status, sale = investigate_sale(session, recording_user_id=recording_user_id,
                                        key=idempotency_key)
    if status == "processing":
        response.status_code = 202
    return SaleKeyStatus(status=status, sale=sale)


@router.post("/reconciliation/{recording_user_id}/{idempotency_key}/acknowledge",
             response_model=SaleAcknowledgment)
def post_owner_sale_acknowledgment(response: Response, recording_user_id: int = Path(gt=0),
                                   idempotency_key: UUID = Path(),
                                   principal: Principal = Depends(require_owner_or_cashier),
                                   session: Session = Depends(get_db_session)):
    response.headers["Cache-Control"] = "no-store"
    with session.begin():
        if principal.role != "Owner":
            reject_acknowledgment(session, actor_user_id=principal.user_id,
                                  recording_user_id=recording_user_id, key=idempotency_key)
            result, error = None, ApiError(403, "forbidden", "Insufficient permissions")
        else:
            result, error = acknowledge_sale(session, actor_user_id=principal.user_id,
                                             recording_user_id=recording_user_id,
                                             key=idempotency_key)
    if error is not None:
        raise error
    # Repeated explicit acknowledgments return the same sale, with one new audit per action.
    return {"status": "committed", "recording_user_id": recording_user_id,
            "idempotency_key": str(idempotency_key), "sale": result}


@router.get("", response_model=None)
def get_transaction_history(response: Response, business_date: date | None = None,
                            limit: int = Query(default=50, ge=1, le=100), cursor: str | None = None,
                            principal: Principal = Depends(require_owner_or_cashier),
                            session: Session = Depends(get_db_session)):
    response.headers["Cache-Control"] = "no-store"
    with session.begin():
        return list_history(session, role=principal.role, business_date=business_date,
                            limit=limit, cursor=cursor)


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


@router.get("/{transaction_id}", response_model=None)
def get_transaction_detail(response: Response, transaction_id: int = Path(gt=0),
                           principal: Principal = Depends(require_owner_or_cashier),
                           session: Session = Depends(get_db_session)):
    response.headers["Cache-Control"] = "no-store"
    with session.begin():
        return get_history_detail(session, transaction_id, role=principal.role)


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


@router.post("/manual", response_model=SalePublic, status_code=201)
def post_manual_sale(payload: ManualSaleCreate, response: Response,
                     idempotency_key: UUID = Header(alias="Idempotency-Key"),
                     principal: Principal = Depends(require_owner_or_cashier),
                     session: Session = Depends(get_db_session)):
    with session.begin():
        result, replayed = record_manual_sale(
            session, payload, actor_user_id=principal.user_id,
            role=principal.role, idempotency_key=idempotency_key,
        )
    if replayed:
        response.status_code = 200
    return result


@router.post("/{transaction_id}/void", response_model=None)
def post_void_transaction(payload: VoidRequest, transaction_id: int = Path(gt=0),
                          principal: Principal = Depends(require_owner_or_cashier),
                          session: Session = Depends(get_db_session)):
    if principal.role != "Owner":
        with session.begin():
            record_rejected_void(session, actor_user_id=principal.user_id,
                                 transaction_id=transaction_id)
        raise ApiError(403, "forbidden", "Insufficient permissions")
    with session.begin():
        changed = void_transaction(session, transaction_id=transaction_id,
                                   reason=payload.reason, actor_user_id=principal.user_id)
        result = get_history_detail(session, transaction_id, role="Owner") if changed else None
    if not changed:
        raise ApiError(409, "already_voided", "Transaction is already voided")
    return result
