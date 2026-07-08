# -*- coding: utf-8 -*-
"""Seed mínimo do banco de DEV — NUNCA roda contra produção.

Popula um banco recém-migrado (alembic upgrade head) com:
  - 1 PLATFORM_OWNER (company_id=None)
  - 1 company de teste via create_company() (semeia TenantConfig, módulos,
    branding, categorias, templates, conta CAIXA e fee policies)
  - 1 OWNER da company
  - 2 services, 1 professional (vinculado aos serviços + working hours seg–sáb)
  - 2 customers
  - 1 product e 1 package (1 item SERVICE) para testar catálogo

Uso:
  cd agendamento_engine
  $env:DATABASE_URL = "<connection string do DEV>"
  .\\venv\\Scripts\\python.exe scripts\\seed_dev.py

Idempotente por slug: se a company 'barbearia-dev' já existe, aborta sem
duplicar nada.
"""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Guard anti-produção — ANTES de qualquer import da app ────────────────────
# O ref do projeto Supabase de produção aparece em qualquer forma de conexão
# (direta db.<ref>.supabase.co ou pooler postgres.<ref>@...).
_PROD_PROJECT_REF = "uhhygdqioqcgcfqfbmif"

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    sys.exit("ERRO: DATABASE_URL não configurada. Aponte para o banco de DEV.")
if _PROD_PROJECT_REF in DATABASE_URL:
    sys.exit(
        "ABORTADO: DATABASE_URL aponta para o banco de PRODUÇÃO "
        f"(ref {_PROD_PROJECT_REF}). seed_dev não roda em produção."
    )

from datetime import time as dtime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password
from app.infrastructure.db.models.customer import Customer
from app.infrastructure.db.models.package import Package, PackageItem
from app.infrastructure.db.models.product import Product
from app.infrastructure.db.models.professional import Professional
from app.infrastructure.db.models.service import Service, ProfessionalService
from app.infrastructure.db.models.user import User
from app.infrastructure.db.models.availability_slot import WorkingHour
from app.modules.companies.schemas import CompanyCreate
from app.modules.companies.service import create_company

SLUG = "barbearia-dev"
SENHA_DEV = "DevPaladino2026"  # só para ambiente de dev

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


def main() -> None:
    db = SessionLocal()
    try:
        from app.infrastructure.db.models.company import Company
        if db.query(Company).filter(Company.slug == SLUG).first():
            print(f"Company '{SLUG}' já existe — seed já rodou. Nada a fazer.")
            return

        # 1. PLATFORM_OWNER (global, sem tenant)
        platform_owner = db.query(User).filter(
            User.email == "platform@dev.paladino.app").first()
        if not platform_owner:
            platform_owner = User(
                company_id=None,
                email="platform@dev.paladino.app",
                password_hash=hash_password(SENHA_DEV),
                role="PLATFORM_OWNER",
                name="Platform Owner (dev)",
                active=True,
            )
            db.add(platform_owner)
            db.commit()
            print("PLATFORM_OWNER criado: platform@dev.paladino.app")

        # 2. Company via create_company (onboarding completo; commit interno)
        company = create_company(db, CompanyCreate(name="Barbearia Dev", slug=SLUG))
        print(f"Company criada: {company.name} ({company.id})")

        # 3. OWNER do tenant
        owner = User(
            company_id=company.id,
            email="owner@dev.paladino.app",
            password_hash=hash_password(SENHA_DEV),
            role="OWNER",
            name="Owner Dev",
            active=True,
        )
        db.add(owner)

        # 4. Serviços
        corte = Service(company_id=company.id, name="Corte masculino",
                        price=Decimal("50.00"), duration=30)
        barba = Service(company_id=company.id, name="Barba",
                        price=Decimal("35.00"), duration=20)
        db.add_all([corte, barba])
        db.flush()

        # 5. Profissional + vínculo com serviços + escala seg–sáb 09h–18h
        prof = Professional(company_id=company.id, name="João Barbeiro",
                            active=True)
        db.add(prof)
        db.flush()
        db.add_all([
            ProfessionalService(company_id=company.id, professional_id=prof.id,
                                service_id=corte.id),
            ProfessionalService(company_id=company.id, professional_id=prof.id,
                                service_id=barba.id),
        ])
        for weekday in range(0, 6):  # 0=seg ... 5=sáb (6=dom sem escala)
            db.add(WorkingHour(
                company_id=company.id, professional_id=prof.id,
                weekday=weekday,
                opening_time=dtime(9, 0), closing_time=dtime(18, 0),
                is_active=True,
            ))

        # 6. Clientes (phone com DDI 55, convenção de Customer.phone)
        db.add_all([
            Customer(company_id=company.id, name="Cliente Um",
                     phone="5562999990001"),
            Customer(company_id=company.id, name="Cliente Dois",
                     phone="5562999990002"),
        ])

        # 7. Produto + pacote (1 item SERVICE) para o catálogo
        pomada = Product(company_id=company.id, name="Pomada modeladora",
                         price=Decimal("25.00"), stock=10, active=True)
        db.add(pomada)
        pacote = Package(company_id=company.id, name="Pacote 4 cortes",
                         total_cotas=4, price=Decimal("180.00"),
                         validity_days=90, is_active=True)
        db.add(pacote)
        db.flush()
        db.add(PackageItem(package_id=pacote.package_id, company_id=company.id,
                           item_type="SERVICE", service_id=corte.id,
                           quantity=4, display_order=0))

        db.commit()
        print("Seed concluído:")
        print(f"  PLATFORM_OWNER: platform@dev.paladino.app / {SENHA_DEV}")
        print(f"  OWNER:          owner@dev.paladino.app / {SENHA_DEV}")
        print(f"  slug booking:   {SLUG}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
