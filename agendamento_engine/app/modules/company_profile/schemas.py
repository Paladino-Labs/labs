from typing import Optional, List
from pydantic import BaseModel, HttpUrl
 
 
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
