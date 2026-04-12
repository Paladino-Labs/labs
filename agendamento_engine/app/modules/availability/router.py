from uuid import UUID
from datetime import date
from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.core.deps import get_current_company_id
from app.modules.availability import schemas, service as svc

router = APIRouter(prefix="/availability", tags=["availability"])


@router.get("/slots", response_model=List[schemas.AvailableSlot])
def get_available_slots(
    professional_id: UUID = Query(...),
    service_id: UUID = Query(...),
    date: date = Query(...),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return svc.get_available_slots(db, company_id, professional_id, service_id, date)
