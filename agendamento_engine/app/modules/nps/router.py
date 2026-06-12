from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.rate_limit import limiter
from app.infrastructure.db.session import get_db
from app.infrastructure.db.models import NpsResponse, NpsSurvey
from app.modules.nps import service as nps_service
from app.modules.nps.schemas import (
    NpsConfigResponse,
    NpsConfigUpdate,
    NpsResponseOut,
    NpsSurveyDetailResponse,
    NpsSurveyResponse,
    PublicNpsRespondRequest,
    TenantResponseRequest,
)

router = APIRouter(prefix="/nps", tags=["nps"])


# ── Tenant ────────────────────────────────────────────────────────────────────

@router.get("/config", response_model=NpsConfigResponse)
def get_config(
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    return nps_service.get_or_create_config(db, current_user.company_id)


@router.put("/config", response_model=NpsConfigResponse)
def update_config(
    body: NpsConfigUpdate,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    config = nps_service.get_or_create_config(db, current_user.company_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(config, field, value)
    db.commit()
    db.refresh(config)
    return config


@router.get("/surveys", response_model=List[NpsSurveyResponse])
def list_surveys(
    status: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    query = db.query(NpsSurvey).filter(NpsSurvey.company_id == current_user.company_id)
    if status:
        query = query.filter(NpsSurvey.status == status)
    if date_from:
        query = query.filter(NpsSurvey.created_at >= date_from)
    if date_to:
        query = query.filter(NpsSurvey.created_at <= date_to)
    return query.order_by(NpsSurvey.created_at.desc()).limit(200).all()


@router.get("/surveys/{survey_id}", response_model=NpsSurveyDetailResponse)
def get_survey(
    survey_id: UUID,
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    survey = (
        db.query(NpsSurvey)
        .filter(NpsSurvey.id == survey_id, NpsSurvey.company_id == current_user.company_id)
        .first()
    )
    if survey is None:
        raise HTTPException(status_code=404, detail="Pesquisa não encontrada")
    response = db.query(NpsResponse).filter(NpsResponse.survey_id == survey.id).first()
    detail = NpsSurveyDetailResponse.model_validate(survey)
    if response is not None:
        detail.response = NpsResponseOut.model_validate(response)
    return detail


@router.post("/surveys/{survey_id}/respond", response_model=NpsResponseOut)
def tenant_respond(
    survey_id: UUID,
    body: TenantResponseRequest,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return nps_service.add_tenant_response(
        db, survey_id, body.response,
        actor_id=current_user.id, company_id=current_user.company_id,
    )


# ── Público (link na mensagem — sem auth) ────────────────────────────────────

@router.post("/respond/{survey_id}", response_model=NpsResponseOut)
@limiter.limit("3/minute")
def public_respond(
    request: Request,
    survey_id: UUID,
    body: PublicNpsRespondRequest,
    db: Session = Depends(get_db),
):
    return nps_service.record_response(db, survey_id, body.score, comment=body.comment)
