import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models.company import Company
from app.infrastructure.db.models.company_settings import CompanySettings
from app.infrastructure.db.models.tenant_config import TenantConfig
from app.infrastructure.db.models.module_activation import ModuleActivation, ModuleName
from app.infrastructure.db.models.tenant_branding import TenantBranding
from app.infrastructure.db.models.category import Category, EntityType
from app.infrastructure.db.models.communication_setting import CommunicationSetting
from app.infrastructure.db.models.communication_template import CommunicationTemplate
from app.infrastructure.db.models.account import Account
from app.infrastructure.db.models.tenant_fee_routing_policy import TenantFeeRoutingPolicy
from app.modules.companies.schemas import CompanyCreate, CompanyPatch

logger = logging.getLogger(__name__)


_DEFAULT_FEE_SOURCES = [
    "ASAAS_PIX",
    "ASAAS_CARD",
    "MAQUININHA_DEBIT",
    "MAQUININHA_CREDIT",
    "MAQUININHA_PIX",
    "ANTECIPACAO",
    "ESTORNO",
    "RECORRENTE_FEE",
]

# fee_sources que partem com fee_percentage=NULL (taxa ainda não configurada).
# Dispara aviso no confirm_manual até o operador configurar via PATCH /financial/fee-policies.
_FEE_SOURCES_UNCONFIGURED_BY_DEFAULT = {"MAQUININHA_PIX"}


_DEFAULT_CATEGORIES: dict = {
    EntityType.SERVICE: ["Corte", "Barba", "Tratamento", "Combo", "Outros"],
    EntityType.PRODUCT: ["Cuidado", "Finalização", "Ferramentas", "Outros"],
    EntityType.EXPENSE: ["Aluguel", "Utilities", "Marketing", "Software",
                         "Contabilidade", "Limpeza", "Outros"],
}

# Templates mínimos obrigatórios por company — is_default=True, is_active=True.
# Variáveis disponíveis: {{cliente_nome}}, {{horario}}, {{data}}, {{servico}},
#                        {{profissional}}, {{empresa_nome}}
_DEFAULT_TEMPLATES: list[dict] = [
    {
        "event_type": "appointment.confirmed",
        "channel": "WHATSAPP",
        "audience": "CLIENT",
        "body_template": (
            "Olá, {{cliente_nome}}! ✅\n\n"
            "Seu agendamento foi confirmado:\n\n"
            "✂️  *{{servico}}*\n"
            "👤  {{profissional}}\n"
            "📅  {{data}} às {{horario}}\n\n"
            "Te esperamos! Qualquer dúvida, é só responder aqui. 😊"
        ),
    },
    {
        "event_type": "appointment.confirmed",
        "channel": "WHATSAPP",
        "audience": "PROFESSIONAL",
        "body_template": (
            "Novo agendamento confirmado!\n\n"
            "👤  Cliente: {{cliente_nome}}\n"
            "✂️  Serviço: {{servico}}\n"
            "📅  {{data}} às {{horario}}"
        ),
    },
    {
        "event_type": "appointment.cancelled",
        "channel": "WHATSAPP",
        "audience": "CLIENT",
        "body_template": (
            "Olá, {{cliente_nome}}. 😔\n\n"
            "Seu agendamento de *{{servico}}* no dia {{data}} às {{horario}} "
            "foi cancelado.\n\n"
            "Para reagendar, é só responder aqui."
        ),
    },
    {
        "event_type": "appointment.reminder_24h",
        "channel": "WHATSAPP",
        "audience": "CLIENT",
        "body_template": (
            "Olá, {{cliente_nome}}! 👋\n\n"
            "Lembrete: você tem *{{servico}}* com *{{profissional}}* "
            "amanhã, {{data}} às {{horario}}. 💈\n\n"
            "Responda _Ver agendamentos_ para gerenciar."
        ),
    },
    {
        "event_type": "appointment.reminder_2h",
        "channel": "WHATSAPP",
        "audience": "CLIENT",
        "body_template": (
            "Olá, {{cliente_nome}}! 😊\n\n"
            "Seu *{{servico}}* começa em 2 horas, às {{horario}}. "
            "Te esperamos! 💈"
        ),
    },
    {
        "event_type": "appointment.no_show",
        "channel": "WHATSAPP",
        "audience": "PROFESSIONAL",
        "body_template": (
            "Atenção: o cliente {{cliente_nome}} não compareceu ao agendamento "
            "de *{{servico}}* às {{horario}} do dia {{data}}."
        ),
    },
    {
        "event_type": "appointment.no_show",
        "channel": "WHATSAPP",
        "audience": "OWNER",
        "body_template": (
            "No-show registrado: {{cliente_nome}} — *{{servico}}* "
            "com {{profissional}} às {{horario}} do dia {{data}}."
        ),
    },
    {
        "event_type": "auth.password_reset_requested",
        "channel": "WHATSAPP",
        "audience": "CLIENT",
        "body_template": (
            "Seu código de redefinição de senha Paladino: {{token}}. "
            "Válido por 15 minutos. Não compartilhe este código."
        ),
    },
    {
        "event_type": "user.invitation_sent",
        "channel": "EMAIL",
        "audience": "CLIENT",
        "body_template": (
            "Olá!\n\n"
            "Você foi convidado para acessar {{company_name}} no Paladino.\n\n"
            "Clique no link abaixo para criar sua senha e ativar sua conta:\n"
            "{{activation_link}}\n\n"
            "Este convite expira em 48 horas.\n\n"
            "Se não reconhece este convite, ignore este e-mail."
        ),
    },
    {
        "event_type": "auth.password_reset_requested",
        "channel": "EMAIL",
        "audience": "CLIENT",
        "body_template": (
            "Olá, {{user_name}}!\n\n"
            "Seu código de redefinição de senha é: {{token}}\n\n"
            "Válido por 15 minutos. Não compartilhe este código.\n\n"
            "Se você não solicitou a redefinição, ignore este e-mail."
        ),
    },
]


def create_company(db: Session, data: CompanyCreate) -> Company:
    """Cria company e semente todos os registros de onboarding na mesma transação."""
    if data.slug:
        conflict = db.query(Company).filter(Company.slug == data.slug).first()
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"Slug '{data.slug}' já está em uso",
            )

    # Valida CPF/CNPJ do owner antes de qualquer criação no banco (fail-fast)
    _owner_cpf_cnpj_clean = ""
    if data.owner_cpf_cnpj:
        from app.modules.payments.service import validate_and_clean_cpf_cnpj
        _owner_cpf_cnpj_clean = validate_and_clean_cpf_cnpj(data.owner_cpf_cnpj)

    company = Company(name=data.name, slug=data.slug)
    db.add(company)
    db.flush()  # gera company.id sem commit

    # TenantConfig com todos os defaults
    db.add(TenantConfig(company_id=company.id))

    # ModuleActivation — um por módulo, todos inativos
    for module in ModuleName:
        db.add(ModuleActivation(company_id=company.id, module_name=module.value, is_active=False))

    # TenantBranding vazio
    db.add(TenantBranding(company_id=company.id))

    # Categories default por entity_type
    for entity_type, names in _DEFAULT_CATEGORIES.items():
        for sort_order, name in enumerate(names):
            db.add(Category(
                company_id=company.id,
                name=name,
                entity_type=entity_type.value,
                is_default=True,
                is_active=True,
                sort_order=sort_order,
            ))

    # CommunicationSettings com defaults
    db.add(CommunicationSetting(
        company_id=company.id,
        whatsapp_enabled=False,
        email_enabled=False,
        quiet_hours_enabled=True,
    ))

    # Templates default de comunicação (7 templates obrigatórios)
    for tmpl_data in _DEFAULT_TEMPLATES:
        db.add(CommunicationTemplate(
            company_id=company.id,
            is_default=True,
            is_active=True,
            **tmpl_data,
        ))

    # ── Financial Core (Sprint 6) ─────────────────────────────────────────────

    # Account default CAIXA
    db.add(Account(
        company_id=company.id,
        name="Caixa principal",
        type="CAIXA",
        is_default_inflow=True,
    ))

    # TenantFeeRoutingPolicy defaults — tenant_share=100% (sem repasse).
    # MAQUININHA_PIX parte com fee_percentage=NULL para disparar aviso até configuração.
    for fs in _DEFAULT_FEE_SOURCES:
        db.add(TenantFeeRoutingPolicy(
            company_id=company.id,
            fee_source=fs,
            client_share=0,
            tenant_share=100,
            professional_share=0,
            fee_percentage=None if fs in _FEE_SOURCES_UNCONFIGURED_BY_DEFAULT else 0,
        ))

    # ─────────────────────────────────────────────────────────────────────────

    db.commit()
    db.refresh(company)

    # ── Sprint 8: subconta Asaas — NÃO BLOQUEANTE ─────────────────────────────
    # Falha não impede a criação do tenant; apenas loga warning.
    try:
        from app.modules.payments.provider_factory import get_payment_provider
        provider = get_payment_provider(company_id=company.id, db=db)

        # Busca OWNER recém-criado para email
        from app.infrastructure.db.models.user import User
        owner = (
            db.query(User)
            .filter(User.company_id == company.id, User.role == "OWNER")
            .first()
        )
        owner_email = owner.email if owner else f"{company.slug or str(company.id)}@paladino.app"

        if not _owner_cpf_cnpj_clean or not data.owner_birth_date:
            logger.warning(
                "asaas_subaccount_missing_cpf_or_birthdate",
                extra={"company_id": str(company.id)},
            )

        result = provider.create_subaccount(
            name=company.name,
            cpf_cnpj=_owner_cpf_cnpj_clean,
            email=owner_email,
            birth_date=data.owner_birth_date or "",
        )
        company.payment_provider = "asaas"
        company.external_account_id = result["accountId"]
        company.external_account_status = "pending_verification"
        company.external_account_created_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(company)
    except Exception as exc:
        logger.warning(
            "payment_subaccount_creation_failed",
            extra={"company_id": str(company.id), "error": str(exc)},
        )
    # ──────────────────────────────────────────────────────────────────────────

    return company


def get_company_or_404(db: Session, company_id: UUID) -> Company:
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return company


def get_company_with_settings(db: Session, company_id: UUID) -> Company:
    """Retorna a company com settings carregado (para o GET /me)."""
    company = get_company_or_404(db, company_id)

    # Carrega settings explicitamente para evitar lazy-load fora de contexto
    settings = (
        db.query(CompanySettings)
        .filter(CompanySettings.company_id == company_id)
        .first()
    )
    # Injeta no objeto para serialização pelo schema (from_attributes)
    company.settings = settings
    return company


def update_company(db: Session, company_id: UUID, data: CompanyPatch) -> Company:
    company = get_company_or_404(db, company_id)

    # Atualiza campos da Company
    if data.company is not None:
        company_fields = data.company.model_dump(exclude_none=True)

        # Valida unicidade do slug (ignora a própria company)
        if "slug" in company_fields:
            slug_conflict = (
                db.query(Company)
                .filter(
                    Company.slug == company_fields["slug"],
                    Company.id != company_id,
                )
                .first()
            )
            if slug_conflict:
                raise HTTPException(
                    status_code=409,
                    detail=f"Slug '{company_fields['slug']}' já está em uso por outra empresa",
                )

        for field, value in company_fields.items():
            setattr(company, field, value)

    # Atualiza (ou cria) CompanySettings
    if data.settings is not None:
        settings_fields = data.settings.model_dump(exclude_none=True)

        settings = (
            db.query(CompanySettings)
            .filter(CompanySettings.company_id == company_id)
            .first()
        )

        if settings is None:
            # Cria com os valores fornecidos; demais campos usam defaults do modelo
            settings = CompanySettings(company_id=company_id, **settings_fields)
            db.add(settings)
        else:
            for field, value in settings_fields.items():
                setattr(settings, field, value)

    db.commit()
    db.refresh(company)

    # Recarrega settings após commit para retornar estado atualizado
    settings = (
        db.query(CompanySettings)
        .filter(CompanySettings.company_id == company_id)
        .first()
    )
    company.settings = settings
    return company
