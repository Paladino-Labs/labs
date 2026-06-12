from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.infrastructure.db.session import get_db
from app.infrastructure.db.models import CustomerClassification
from app.modules.crm import service as crm_service
from app.modules.crm.schemas import (
    ClassificationOut,
    CrmAlertsResponse,
    CrmConfigResponse,
    CrmConfigUpdate,
)

router = APIRouter(prefix="/crm", tags=["crm"])


@router.get("/alerts", response_model=CrmAlertsResponse)
def get_alerts(
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return crm_service.get_crm_alerts(db, current_user.company_id)


@router.get("/classifications", response_model=List[ClassificationOut])
def list_classifications(
    classification: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    query = db.query(CustomerClassification).filter(
        CustomerClassification.company_id == current_user.company_id
    )
    if classification:
        query = query.filter(CustomerClassification.classification == classification)
    if date_from:
        query = query.filter(CustomerClassification.computed_at >= date_from)
    return query.order_by(CustomerClassification.computed_at.desc()).limit(200).all()


@router.get("/config", response_model=CrmConfigResponse)
def get_config(
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    return crm_service.get_or_create_config(db, current_user.company_id)


@router.put("/config", response_model=CrmConfigResponse)
def update_config(
    body: CrmConfigUpdate,
    current_user=Depends(require_role("OWNER")),
    db: Session = Depends(get_db),
):
    config = crm_service.get_or_create_config(db, current_user.company_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(config, field, value)
    db.commit()
    db.refresh(config)
    return config
