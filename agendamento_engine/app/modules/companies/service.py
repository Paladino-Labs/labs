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
from app.modules.companies.schemas import CompanyCreate, CompanyPatch


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

    db.commit()
    db.refresh(company)
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
