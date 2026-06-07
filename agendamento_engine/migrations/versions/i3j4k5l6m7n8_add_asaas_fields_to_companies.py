"""add_asaas_fields_to_companies

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-06-07

Adiciona 6 colunas owner_* à tabela companies para suporte aos campos
obrigatórios da API Asaas (mobilePhone, incomeValue, address, addressNumber,
province, postalCode). Todos nullable — sem DEFAULT — sem quebra de dados existentes.
"""
from alembic import op
import sqlalchemy as sa

revision = "i3j4k5l6m7n8"
down_revision = "h2i3j4k5l6m7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # owner_cpf_cnpj e owner_birth_date: presentes no CompanyCreate schema mas nunca
    # persistidos na tabela — adicionados aqui para completar o modelo ORM.
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS owner_cpf_cnpj VARCHAR(20)")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS owner_birth_date VARCHAR(10)")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS owner_mobile_phone VARCHAR(20)")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS owner_income_value NUMERIC(12,2)")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS owner_address VARCHAR(200)")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS owner_address_number VARCHAR(20)")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS owner_province VARCHAR(100)")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS owner_postal_code VARCHAR(10)")


def downgrade() -> None:
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS owner_postal_code")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS owner_province")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS owner_address_number")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS owner_address")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS owner_income_value")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS owner_mobile_phone")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS owner_birth_date")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS owner_cpf_cnpj")
