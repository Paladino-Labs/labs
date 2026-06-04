"""add_maquininha_pix_fee_source

Revision ID: g3h4i5j6k7l8
Revises: f2g3h4i5j6k7
Create Date: 2026-06-04

1. fee_percentage: NOT NULL → NULL (NULL = taxa não configurada → dispara aviso).
   Registros existentes (fee_percentage=0) permanecem inalterados — 0 ≠ NULL.

2. Insere política MAQUININHA_PIX (fee_percentage=NULL, is_active=TRUE) para todos
   os tenants existentes que ainda não a possuem. Novos tenants recebem esta
   política via create_company() após este deploy.

Nota: fee_source é VARCHAR — nenhum ALTER TYPE necessário.
      payment_method também é VARCHAR — MAQUININHA_PIX é aceito como valor livre.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g3h4i5j6k7l8"
down_revision: Union[str, Sequence[str], None] = "f2g3h4i5j6k7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Tornar fee_percentage nullable (NULL = "não configurado" → dispara aviso no app)
    op.execute(sa.text(
        "ALTER TABLE tenant_fee_routing_policies "
        "ALTER COLUMN fee_percentage DROP NOT NULL"
    ))

    # 2. Seed MAQUININHA_PIX para tenants existentes que ainda não têm a política.
    #    ON CONFLICT é seguro — UNIQUE(company_id, fee_source) impede duplicatas.
    op.execute(sa.text("""
        INSERT INTO tenant_fee_routing_policies
            (policy_id, company_id, fee_source,
             client_share, tenant_share, professional_share,
             fee_percentage, fee_flat, is_active,
             created_at)
        SELECT
            gen_random_uuid(),
            id,
            'MAQUININHA_PIX',
            0, 100, 0,
            NULL, 0, TRUE,
            now()
        FROM companies
        WHERE NOT EXISTS (
            SELECT 1
            FROM   tenant_fee_routing_policies tfp
            WHERE  tfp.company_id = companies.id
              AND  tfp.fee_source  = 'MAQUININHA_PIX'
        )
    """))


def downgrade() -> None:
    # Remove registros MAQUININHA_PIX inseridos pelo seed
    op.execute(sa.text(
        "DELETE FROM tenant_fee_routing_policies WHERE fee_source = 'MAQUININHA_PIX'"
    ))

    # Restaura NOT NULL (converte NULL → 0 antes de aplicar)
    op.execute(sa.text(
        "UPDATE tenant_fee_routing_policies SET fee_percentage = 0 WHERE fee_percentage IS NULL"
    ))
    op.execute(sa.text(
        "ALTER TABLE tenant_fee_routing_policies "
        "ALTER COLUMN fee_percentage SET NOT NULL"
    ))
