"""expand_fee_sources_bandeiras — bandeiras de maquininha + Chave Pix

Revision ID: l4m5n6o7p8q9
Revises: k3l4m5n6o7p8
Create Date: 2026-06-10

Expansão dos fee_sources de 8 para 10 valores canônicos:
  CASH, CHAVE_PIX, MAQUININHA_PIX,
  MAQUININHA_CREDIT_VISA_MASTER, MAQUININHA_CREDIT_ELO,
  MAQUININHA_CREDIT_HIPER_AMEX, MAQUININHA_CREDIT_OUTROS,
  MAQUININHA_DEBIT_VISA_MASTER, MAQUININHA_DEBIT_ELO, MAQUININHA_DEBIT_OUTROS

Operações (idempotentes):
  1. Remove fee_sources de pagamentos online Asaas — taxa chega via webhook:
     PIX, BOLETO, CARD_CREDIT, CARD_DEBIT
  2. Renomeia MAQUININHA_CREDIT → MAQUININHA_CREDIT_OUTROS (fallback),
     preservando configuração existente; duplicata (se _OUTROS já existir) é removida.
  3. Renomeia MAQUININHA_DEBIT → MAQUININHA_DEBIT_OUTROS (idem).
  4. Insere políticas ausentes por empresa:
     CHAVE_PIX com fee_percentage=0 (sem taxa por padrão);
     bandeiras de maquininha com fee_percentage=NULL (dispara fee_warning
     até o operador configurar — semântica NULL = "não configurado").
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l4m5n6o7p8q9"
down_revision: Union[str, Sequence[str], None] = "k3l4m5n6o7p8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Remover fee_sources de pagamentos online (taxa via webhook Asaas)
    conn.execute(sa.text(
        "DELETE FROM tenant_fee_routing_policies "
        "WHERE fee_source IN ('PIX', 'BOLETO', 'CARD_CREDIT', 'CARD_DEBIT')"
    ))

    # 2/3. Renomear legados para os fallbacks *_OUTROS (preserva configuração).
    #      Se a empresa já tiver o destino, remove o legado em vez de renomear.
    for old, new in (
        ("MAQUININHA_CREDIT", "MAQUININHA_CREDIT_OUTROS"),
        ("MAQUININHA_DEBIT", "MAQUININHA_DEBIT_OUTROS"),
    ):
        conn.execute(sa.text(f"""
            UPDATE tenant_fee_routing_policies p
            SET fee_source = '{new}'
            WHERE p.fee_source = '{old}'
              AND NOT EXISTS (
                  SELECT 1 FROM tenant_fee_routing_policies d
                  WHERE d.company_id = p.company_id AND d.fee_source = '{new}'
              )
        """))
        conn.execute(sa.text(
            f"DELETE FROM tenant_fee_routing_policies WHERE fee_source = '{old}'"
        ))

    # 4. Inserir políticas ausentes por empresa.
    #    fee_percentage: NULL = não configurado (fee_warning); 0 = sem taxa.
    missing_sources = [
        ("CASH",                          "0"),
        ("CHAVE_PIX",                     "0"),
        ("MAQUININHA_PIX",                "NULL"),
        ("MAQUININHA_CREDIT_VISA_MASTER", "NULL"),
        ("MAQUININHA_CREDIT_ELO",         "NULL"),
        ("MAQUININHA_CREDIT_HIPER_AMEX",  "NULL"),
        ("MAQUININHA_CREDIT_OUTROS",      "NULL"),
        ("MAQUININHA_DEBIT_VISA_MASTER",  "NULL"),
        ("MAQUININHA_DEBIT_ELO",          "NULL"),
        ("MAQUININHA_DEBIT_OUTROS",       "NULL"),
    ]

    for source, fee_pct in missing_sources:
        conn.execute(sa.text(f"""
            INSERT INTO tenant_fee_routing_policies
                (policy_id, company_id, fee_source,
                 fee_percentage, fee_flat,
                 client_share, tenant_share, professional_share,
                 is_active)
            SELECT
                gen_random_uuid(), c.id, '{source}',
                {fee_pct}, 0,
                0, 100, 0,
                TRUE
            FROM companies c
            WHERE NOT EXISTS (
                SELECT 1 FROM tenant_fee_routing_policies p
                WHERE p.company_id = c.id AND p.fee_source = '{source}'
            )
        """))


def downgrade() -> None:
    # Não há downgrade seguro: a remoção de PIX/BOLETO/CARD_* descarta
    # configurações e o rename para *_OUTROS é com perda de granularidade.
    pass
