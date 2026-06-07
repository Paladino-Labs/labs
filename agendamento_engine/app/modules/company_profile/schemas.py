import re
from typing import Optional, List, Any
from pydantic import BaseModel, field_validator, model_validator


class BusinessHourEntry(BaseModel):
    weekday: int   # 0=segunda, 6=domingo
    open: str      # "HH:MM"
    close: str     # "HH:MM"

    @field_validator("weekday")
    @classmethod
    def validate_weekday(cls, v: int) -> int:
        if not (0 <= v <= 6):
            raise ValueError("weekday deve ser 0-6 (0=segunda, 6=domingo)")
        return v

    @field_validator("open", "close")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError("Horário deve estar no formato HH:MM")
        h, m = v.split(":")
        if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
            raise ValueError("Horário inválido")
        return v


class CompanyProfileOut(BaseModel):
    """Resposta de GET /company/profile"""
    tagline: Optional[str] = None
    description: Optional[str] = None

    logo_url: Optional[str] = None
    cover_url: Optional[str] = None
    gallery_urls: List[str] = []

    address: Optional[str] = None
    city: Optional[str] = None
    whatsapp: Optional[str] = None
    maps_url: Optional[str] = None

    instagram_url: Optional[str] = None
    facebook_url: Optional[str] = None
    tiktok_url: Optional[str] = None
    google_review_url: Optional[str] = None

    business_hours: Optional[str] = None
    business_hours_structured: Optional[List[BusinessHourEntry]] = None

    class Config:
        from_attributes = True


class CompanyProfileUpdate(BaseModel):
    """Body de PATCH /company/profile — todos os campos opcionais"""
    tagline: Optional[str] = None
    description: Optional[str] = None

    logo_url: Optional[str] = None
    cover_url: Optional[str] = None
    gallery_urls: Optional[List[str]] = None

    address: Optional[str] = None
    city: Optional[str] = None
    whatsapp: Optional[str] = None
    maps_url: Optional[str] = None

    instagram_url: Optional[str] = None
    facebook_url: Optional[str] = None
    tiktok_url: Optional[str] = None
    google_review_url: Optional[str] = None

    business_hours: Optional[str] = None
    business_hours_structured: Optional[List[BusinessHourEntry]] = None
