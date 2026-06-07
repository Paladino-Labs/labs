"""fix_fee_source_names

Revision ID: j2k3l4m5n6o7
Revises: i3j4k5l6m7n8
Create Date: 2026-06-07

Renomeia fee_sources legados para os nomes canônicos esperados pelo sistema:
  ASAAS_PIX  → PIX
  ASAAS_CARD → CARD_CREDIT

Remove fee_sources não relacionados a MDR de maquininha:
  ANTECIPACAO, ESTORNO, RECORRENTE_FEE

Insere fee_sources ausentes para cada empresa (CASH, BOLETO, CARD_DEBIT,
MAQUININHA_PIX, CARD_CREDIT se não existirem).

Idempotente: usa UPDATE/DELETE/INSERT com EXISTS checks.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "j2k3l4m5n6o7"
down_revision: Union[str, Sequence[str], None] = "i3j4k5l6m7n8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Renomear legados → canônicos
    conn.execute(sa.text(
        "UPDATE tenant_fee_routing_policies SET fee_source = 'PIX' "
        "WHERE fee_source = 'ASAAS_PIX'"
    ))
    conn.execute(sa.text(
        "UPDATE tenant_fee_routing_policies SET fee_source = 'CARD_CREDIT' "
        "WHERE fee_source = 'ASAAS_CARD'"
    ))

    # 2. Remover fee_sources não-MDR que não devem aparecer na tela de taxas
    conn.execute(sa.text(
        "DELETE FROM tenant_fee_routing_policies "
        "WHERE fee_source IN ('ANTECIPACAO', 'ESTORNO', 'RECORRENTE_FEE')"
    ))

    # 3. Inserir fee_sources ausentes para cada empresa
    #    fee_percentage: NULL para MAQUININHA_PIX (aviso até configurar),
    #                    0 para os demais (sem taxa por padrão).
    missing_sources = [
        ("CASH",             "0",    "0",    "0",   "100", "TRUE"),
        ("BOLETO",           "0",    "0",    "0",   "100", "TRUE"),
        ("MAQUININHA_PIX",   "NULL", "0",    "0",   "100", "TRUE"),
        ("MAQUININHA_CREDIT","0",    "0",    "0",   "100", "TRUE"),
        ("MAQUININHA_DEBIT", "0",    "0",    "0",   "100", "TRUE"),
        ("CARD_CREDIT",      "0",    "0",    "0",   "100", "TRUE"),
        ("CARD_DEBIT",       "0",    "0",    "0",   "100", "TRUE"),
        ("PIX",              "0",    "0",    "0",   "100", "TRUE"),
    ]

    for (source, fee_pct, fee_flat, client, tenant, is_active) in missing_sources:
        fee_pct_sql = fee_pct if fee_pct == "NULL" else fee_pct
        conn.execute(sa.text(f"""
            INSERT INTO tenant_fee_routing_policies
                (policy_id, company_id, fee_source,
                 fee_percentage, fee_flat,
                 client_share, tenant_share, professional_share,
                 is_active)
            SELECT
                gen_random_uuid(), c.id, '{source}',
                {fee_pct_sql}, {fee_flat},
                {client}, {tenant}, 0,
                {is_active}
            FROM companies c
            WHERE NOT EXISTS (
                SELECT 1 FROM tenant_fee_routing_policies p
                WHERE p.company_id = c.id AND p.fee_source = '{source}'
            )
        """))


def downgrade() -> None:
    # Não há downgrade seguro para renomeação de dados em produção.
    pass
