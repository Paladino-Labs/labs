from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CrmConfigResponse(BaseModel):
    id: UUID
    company_id: UUID
    new_customer_days: int
    frequent_min_visits: int
    frequent_period_months: int
    risk_multiplier: Decimal
    risk_min_days: int
    vip_min_visits: int
    vip_min_spend: Decimal

    model_config = ConfigDict(from_attributes=True)


class CrmConfigUpdate(BaseModel):
    new_customer_days: Optional[int] = Field(None, ge=1)
    frequent_min_visits: Optional[int] = Field(None, ge=1)
    frequent_period_months: Optional[int] = Field(None, ge=1)
    risk_multiplier: Optional[Decimal] = Field(None, gt=0)
    risk_min_days: Optional[int] = Field(None, ge=1)
    vip_min_visits: Optional[int] = Field(None, ge=1)
    vip_min_spend: Optional[Decimal] = Field(None, ge=0)


class ClassificationOut(BaseModel):
    id: UUID
    customer_id: UUID
    classification: str
    computed_at: datetime
    metrics_snapshot: dict

    model_config = ConfigDict(from_attributes=True)


class CustomerClassificationResponse(BaseModel):
    """Última classificação + histórico (últimas 5)."""
    current: Optional[ClassificationOut] = None
    history: List[ClassificationOut] = []


class SuggestionOut(BaseModel):
    type: str  # RESCHEDULE | PACKAGE | PRODUCT
    reason: str
    service_id: Optional[UUID] = None
    product_id: Optional[UUID] = None


class InsightsResponse(BaseModel):
    churn_risk: str  # LOW | MEDIUM | HIGH
    estimated_return_window: Optional[datetime] = None
    classification: Optional[str] = None
    metrics: dict
    suggestions: List[SuggestionOut] = []


class AtRiskCustomerOut(BaseModel):
    customer_id: UUID
    days_since_last_visit: Optional[int] = None
    computed_at: datetime


class CrmAlertsResponse(BaseModel):
    at_risk_count: int
    at_risk_customers: List[AtRiskCustomerOut] = []
    new_this_month: int
    vip_count: int
    recovered_this_week: int
