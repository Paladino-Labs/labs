from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class GrantCotaRequest(BaseModel):
    customer_id: UUID
    total_cotas: int = Field(..., gt=0)
    expires_at: Optional[datetime] = None
    reason: str = Field(..., min_length=1)


class RevokeRequest(BaseModel):
    reason: str = Field(..., min_length=1)


class CustomerCreditResponse(BaseModel):
    credit_id: UUID
    company_id: UUID
    customer_id: UUID
    entitlement_type: str
    source_id: Optional[UUID] = None
    total_cotas: int
    remaining_cotas: int
    status: str
    granted_at: datetime
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CustomerCreditConsumptionResponse(BaseModel):
    consumption_id: UUID
    credit_id: UUID
    company_id: UUID
    customer_id: UUID
    appointment_id: Optional[UUID] = None
    consumed_at: datetime

    class Config:
        from_attributes = True


class BalanceItem(BaseModel):
    credit_id: str
    entitlement_type: str
    total_cotas: int
    remaining_cotas: int
    status: str
    granted_at: Optional[str] = None
    expires_at: Optional[str] = None
    source_id: Optional[str] = None
