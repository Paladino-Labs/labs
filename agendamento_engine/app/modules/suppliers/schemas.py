from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SupplierCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    contact: Optional[str] = Field(None, max_length=255)
    document: Optional[str] = Field(None, max_length=20)


class SupplierUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    contact: Optional[str] = Field(None, max_length=255)
    document: Optional[str] = Field(None, max_length=20)
    active: Optional[bool] = None


class SupplierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    name: str
    contact: Optional[str] = None
    document: Optional[str] = None
    active: bool
    created_at: datetime
    updated_at: datetime
