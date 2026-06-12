"""impersonation_grants — acesso cross-tenant time-boxed (PlatformSecurity-1)

Revision ID: e0sC2_impersonation_grants
Revises: e0sC1_tenant_status
Create Date: 2026-06-12

Sprint C — Painel Owner Paladino (2/3):
  Grant de impersonation: PLATFORM_OWNER acessa um tenant por tempo limitado
  (default 30 min), com reason obrigatório. READ_ONLY por default; escrita
  exige mode=ELEVATED.

  Tabela de PLATAFORMA — sem RLS por tenant (acesso só via service layer,
  endpoints exigem PLATFORM_OWNER).

  Quase-append-only (variação do padrão consent_records): DELETE sempre
  bloqueado; UPDATE permitido APENAS para revogação (revoked_at NULL → valor,
  demais campos intactos). Revogação é única e irreversível.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0sC2_impersonation_grants"
down_revision: Union[str, Sequence[str], None] = "e0sC1_tenant_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS impersonation_grants (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            platform_user_id  UUID NOT NULL REFERENCES users(id),
            company_id        UUID NOT NULL REFERENCES companies(id),
            mode              VARCHAR(20) NOT NULL DEFAULT 'READ_ONLY',
            reason            TEXT NOT NULL,
            expires_at        TIMESTAMPTZ NOT NULL,
            revoked_at        TIMESTAMPTZ,
            created_at        TIMESTAMPTZ DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_impersonation_grants_company "
        "ON impersonation_grants (company_id, expires_at)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_impersonation_grants_platform_user "
        "ON impersonation_grants (platform_user_id)"
    ))

    # Quase-append-only: DELETE bloqueado; UPDATE só para revogar (uma vez).
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION prevent_impersonation_grant_modification()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'impersonation_grants é append-only — DELETE não permitido';
            END IF;
            IF OLD.revoked_at IS NOT NULL
               OR NEW.revoked_at IS NULL
               OR NEW.id IS DISTINCT FROM OLD.id
               OR NEW.platform_user_id IS DISTINCT FROM OLD.platform_user_id
               OR NEW.company_id IS DISTINCT FROM OLD.company_id
               OR NEW.mode IS DISTINCT FROM OLD.mode
               OR NEW.reason IS DISTINCT FROM OLD.reason
               OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
               OR NEW.created_at IS DISTINCT FROM OLD.created_at
            THEN
                RAISE EXCEPTION 'impersonation_grants: UPDATE permitido apenas para revogação (revoked_at NULL → valor)';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """))
    op.execute(sa.text("""
        CREATE TRIGGER impersonation_grants_no_modify
        BEFORE UPDATE OR DELETE ON impersonation_grants
        FOR EACH ROW EXECUTE FUNCTION prevent_impersonation_grant_modification()
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS impersonation_grants"))
    op.execute(sa.text(
        "DROP FUNCTION IF EXISTS prevent_impersonation_grant_modification()"
    ))
