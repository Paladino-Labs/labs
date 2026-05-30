from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CategoryResponse(BaseModel):
    category_id: UUID
    company_id: UUID
    name: str
    entity_type: str
    is_default: bool
    is_active: bool
    sort_order: int

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    entity_type: str
    is_active: bool = True
    sort_order: int = Field(0, ge=0)


class CategoryPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    entity_type: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = Field(None, ge=0)
