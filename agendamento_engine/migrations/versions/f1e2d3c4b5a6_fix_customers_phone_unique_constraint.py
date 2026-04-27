"""fix_customers_phone_unique_constraint

Corrige a constraint de unicidade legada 'clients_phone_key' que era UNIQUE(phone)
sem incluir company_id — o que impedia o mesmo telefone de ser cliente em duas
empresas diferentes (quebra de multi-tenant).

Novo comportamento: UNIQUE(company_id, phone) — um número pode existir em
empresas distintas, mas não pode se repetir dentro da mesma empresa.

Revision ID: f1e2d3c4b5a6
Revises: e3c9a1d84f17
Create Date: 2026-04-27

"""
from typing import Sequence, Union
from alembic import op

revision: str = "f1e2d3c4b5a6"
down_revision: Union[str, Sequence[str], None] = "e3c9a1d84f17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Remover a constraint legada UNIQUE(phone) sem company_id
    #    O nome 'clients_phone_key' veio da tabela antiga 'clients' — permaneceu
    #    no banco após o rename para 'customers' pela migration f3a9e1d72b04.
    #    IF EXISTS: seguro em deploys onde a constraint já foi removida manualmente.
    op.execute(
        "ALTER TABLE customers DROP CONSTRAINT IF EXISTS clients_phone_key"
    )

    # 2. Adicionar a constraint correta para multi-tenant: UNIQUE(company_id, phone)
    op.create_unique_constraint(
        "uq_customers_company_phone",
        "customers",
        ["company_id", "phone"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_customers_company_phone", "customers", type_="unique")
    # Não restauramos clients_phone_key intencionalmente — era uma constraint errada.
    # Se necessário, adicionar manualmente: ALTER TABLE customers ADD CONSTRAINT
    # clients_phone_key UNIQUE (phone);
