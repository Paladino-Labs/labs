"""add_company_profiles

Revision ID: e3c9a1d84f17
Revises: a2b3c4d5e6f7
Create Date: 2026-04-24

Cria a tabela company_profiles com todas as informações públicas da empresa
exibidas na landing page do link de agendamento.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = 'e3c9a1d84f17'
down_revision: Union[str, Sequence[str], None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_profiles",
        sa.Column("id",             UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id",     UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=False, unique=True),

        # Identidade
        sa.Column("tagline",        sa.String(180),  nullable=True),   # ex: "Tradição e estilo desde 2010"
        sa.Column("description",    sa.Text(),       nullable=True),   # texto livre de apresentação
        sa.Column("logo_url",       sa.String(500),  nullable=True),
        sa.Column("cover_url",      sa.String(500),  nullable=True),   # foto de capa/hero

        # Galeria (até 6 fotos, array de URLs)
        sa.Column("gallery_urls",   sa.ARRAY(sa.String(500)), nullable=True, server_default="{}"),

        # Contato e localização
        sa.Column("address",        sa.String(255),  nullable=True),
        sa.Column("city",           sa.String(100),  nullable=True),
        sa.Column("whatsapp",       sa.String(30),   nullable=True),   # número para link direto
        sa.Column("maps_url",       sa.String(500),  nullable=True),   # link Google Maps

        # Redes sociais
        sa.Column("instagram_url",  sa.String(255),  nullable=True),
        sa.Column("facebook_url",   sa.String(255),  nullable=True),
        sa.Column("tiktok_url",     sa.String(255),  nullable=True),

        # Avaliações
        sa.Column("google_review_url", sa.String(500), nullable=True),

        # Horário de funcionamento (texto livre, ex: "Seg–Sex 9h–20h · Sáb 9h–18h")
        sa.Column("business_hours", sa.String(255),  nullable=True),

        sa.Column("created_at",     sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at",     sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), onupdate=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_company_profiles_company_id", "company_profiles", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_company_profiles_company_id", table_name="company_profiles")
    op.drop_table("company_profiles")