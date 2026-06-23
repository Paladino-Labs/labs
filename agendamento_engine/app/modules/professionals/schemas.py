from decimal import Decimal
from uuid import UUID
from typing import Optional, List
from pydantic import BaseModel


class ProfessionalCreate(BaseModel):
    name: str


class ProfessionalUpdate(BaseModel):
    name: Optional[str] = None
    active: Optional[bool] = None
    specialty: Optional[str] = None
    cpf_cnpj: Optional[str] = None  # recebido em plaintext; gravado encrypted+hash+masked
    user_id: Optional[UUID] = None  # None (explícito) = desvincula; UUID = vincula


class ProfessionalResponse(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    active: bool
    specialty: Optional[str] = None
    cpf_cnpj_masked: Optional[str] = None  # nunca retornar encrypted ou plaintext
    user_id: Optional[UUID] = None  # conta de login vinculada (Sprint 27)

    model_config = {"from_attributes": True}


class ProfessionalServiceCreate(BaseModel):
    service_id: UUID
    commission_percentage: Optional[Decimal] = None  # ex: 30.00


class ProfessionalServiceResponse(BaseModel):
    id: UUID
    service_id: UUID
    service_name: str
    price: Decimal
    duration: int
    commission_percentage: Optional[Decimal] = None
