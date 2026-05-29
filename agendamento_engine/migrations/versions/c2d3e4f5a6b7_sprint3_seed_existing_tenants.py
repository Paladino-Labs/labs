"""sprint3_seed_existing_tenants

Data migration idempotente: cria tenant_config, module_activations, tenant_branding
e categories default para companies que ainda não os possuem.

Idempotente via ON CONFLICT DO NOTHING — pode ser re-executada sem efeito colateral.

Revision ID: c2d3e4f5a6b7
Revises: c1d2e3f4a5b6
Create Date: 2026-05-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MODULES = [
    "ESTOQUE", "COMISSOES", "PACOTES", "ASSINATURAS", "PROMOCOES",
    "CRM", "NPS", "FILA", "BOT_WHATSAPP", "LINK_PUBLICO",
]

_DEFAULT_CATEGORIES = {
    "SERVICE": ["Corte", "Barba", "Tratamento", "Combo", "Outros"],
    "PRODUCT": ["Cuidado", "Finalização", "Ferramentas", "Outros"],
    "EXPENSE": ["Aluguel", "Utilities", "Marketing", "Software",
                "Contabilidade", "Limpeza", "Outros"],
}


def upgrade() -> None:
    conn = op.get_bind()

    companies = conn.execute(sa.text("SELECT id FROM companies")).fetchall()

    for (company_id,) in companies:

        # tenant_config
        conn.execute(sa.text("""
            INSERT INTO tenant_configs (company_id)
            VALUES (:company_id)
            ON CONFLICT (company_id) DO NOTHING
        """), {"company_id": company_id})

        # module_activations — um por módulo
        for module in _MODULES:
            conn.execute(sa.text("""
                INSERT INTO module_activations (company_id, module_name, is_active)
                VALUES (:company_id, CAST(:module_name AS modulename), false)
                ON CONFLICT (company_id, module_name) DO NOTHING
            """), {"company_id": company_id, "module_name": module})

        # tenant_branding
        conn.execute(sa.text("""
            INSERT INTO tenant_brandings (company_id)
            VALUES (:company_id)
            ON CONFLICT (company_id) DO NOTHING
        """), {"company_id": company_id})

        # categories default
        for entity_type, names in _DEFAULT_CATEGORIES.items():
            for sort_order, name in enumerate(names):
                conn.execute(sa.text("""
                    INSERT INTO categories
                        (company_id, name, entity_type, is_default, is_active, sort_order)
                    VALUES
                        (:company_id, :name, CAST(:entity_type AS entitytype), true, true, :sort_order)
                    ON CONFLICT (company_id, name, entity_type) DO NOTHING
                """), {
                    "company_id": company_id,
                    "name": name,
                    "entity_type": entity_type,
                    "sort_order": sort_order,
                })


def downgrade() -> None:
    # Downgrade intencional não-destrutivo: não apaga dados de produção.
    pass
