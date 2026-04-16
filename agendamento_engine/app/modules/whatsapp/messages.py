"""
Templates de mensagem do bot de agendamento.

Objetivo desta versão:
- 100% compatível com comportamento atual
- Alinhado com o fluxo definido (sem mudar UX agora)
- Preparado para handlers (Sprint 3.3)
- Preparado para multi-canal / IA (separação texto vs opções)

REGRAS:
- Nenhuma lógica de negócio
- Nenhuma chamada externa
- Apenas formatação
"""

# ─────────────────────────────────────────────────────────────
# HELPERS (estrutura futura sem quebrar comportamento atual)
# ─────────────────────────────────────────────────────────────

def format_options(options: list[tuple[str, str]]) -> str:
    """Formata opções numeradas para fallback texto."""
    return "\n".join([f"{key} - {label}" for key, label in options])

# ─────────────────────────────────────────────────────────────
# CONSTANTES DE OPÇÕES (alinhadas com FSM)
# ─────────────────────────────────────────────────────────────

MENU_PRINCIPAL_OPTIONS = [
    ("1", "Agendar horário"),
    ("2", "Ver meus agendamentos"),
    ("3", "Falar com atendente"),
]

CONFIRMANDO_OPTIONS = [
    ("1", "Confirmar"),
    ("2", "Alterar horário"),
    ("3", "Alterar serviço"),
    ("0", "Cancelar"),
]

OFERTA_RECORRENTE_OPTIONS = [
    ("1", "Confirmar"),
    ("2", "Escolher outro horário"),
    ("3", "Outro serviço/profissional"),
    ("4", "Ver meus agendamentos"),
]

# ─────────────────────────────────────────────────────────────
# INÍCIO / ONBOARDING
# ─────────────────────────────────────────────────────────────

def boas_vindas_novo(company_name: str, push_name: str = "") -> str:
    greeting = f"Olá! 👋 Seja bem-vindo à *{company_name}*!"

    if push_name:
        return (
            f"{greeting}\n\n"
            f"Seu nome é *{push_name}*? Me confirme seu nome para continuar. 😊"
        )

    return f"{greeting}\n\nPara começar, qual é o seu nome?"


def menu_principal_text(name: str, company_name: str) -> str:
    if name:
        return f"Olá, {name}! 😊\n\nO que você deseja fazer?"
    return f"Olá! 👋 Bem-vindo à *{company_name}*!\n\nO que você deseja fazer?"


def menu_principal_fallback(name: str, company_name: str) -> str:
    return (
        menu_principal_text(name, company_name)
        + "\n\n"
        + format_options(MENU_PRINCIPAL_OPTIONS)
    )

HUMANO_CHAMADO = "Ok! Vou chamar um atendente agora. Aguarde um momento… ☎️"

# ─────────────────────────────────────────────────────────────
# NOME
# ─────────────────────────────────────────────────────────────

PEDIR_NOME_NOVAMENTE = (
    "Por favor, me diga seu nome completo para eu te chamar corretamente. 😊"
)


def boas_vindas_nome_confirmado(first_name: str) -> str:
    return f"Prazer, {first_name}! 😄 Vamos agendar seu horário."

# ─────────────────────────────────────────────────────────────
# OFERTA RECORRENTE
# ─────────────────────────────────────────────────────────────

def oferta_recorrente(
    name: str,
    service_name: str,
    prof_name: str,
    slot_label: str,
    offer_ttl_minutes: int,
) -> str:
    return (
        f"Olá, {name}! Tudo bem? 👋\n\n"
        f"Tenho um *{service_name}* com *{prof_name}* disponível às *{slot_label}* 🕒\n"
        f"_Reservado para você pelos próximos {offer_ttl_minutes} minutos._"
    )


def oferta_recorrente_fallback(*args, **kwargs) -> str:
    return (
        oferta_recorrente(*args, **kwargs)
        + "\n\n"
        + format_options(OFERTA_RECORRENTE_OPTIONS)
    )

OFERTA_EXPIRADA = (
    "⏰ O tempo de reserva expirou. Vou buscar os próximos horários disponíveis..."
)

# ─────────────────────────────────────────────────────────────
# SERVIÇO
# ─────────────────────────────────────────────────────────────

SEM_SERVICOS = (
    "😔 Não há serviços disponíveis no momento. "
    "Entre em contato conosco para mais informações."
)


def escolha_servico(first_name: str = "") -> str:
    if first_name:
        return f"Qual serviço você gostaria, {first_name}?"
    return "Qual serviço você gostaria?"

# ─────────────────────────────────────────────────────────────
# PROFISSIONAL
# ─────────────────────────────────────────────────────────────

def escolha_profissional(service_name: str) -> str:
    return f"Com quem você quer agendar *{service_name}*?"

# ─────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────

def escolha_data_titulo(service_name: str) -> str:
    return f"📅 Escolha a data para {service_name}"


def escolha_data_descricao(first_name: str = "", prof_name: str = "") -> str:
    desc = f"Para qual dia, {first_name}?" if first_name else "Para qual dia?"

    if prof_name and prof_name != "Qualquer disponível":
        desc += f"\n_Profissional: {prof_name}_"

    return desc

# ─────────────────────────────────────────────────────────────
# HORÁRIO
# ─────────────────────────────────────────────────────────────

SEM_HORARIOS = (
    "😔 Não encontrei horários disponíveis para esse período. "
    "Tente outra data ou entre em contato conosco!"
)


def escolha_horario(service_name: str, prof_name: str = "") -> str:
    if prof_name and prof_name != "Qualquer disponível":
        return f"Escolha um horário para *{service_name}* com *{prof_name}*:"
    return f"Escolha um horário para *{service_name}*:"

# ─────────────────────────────────────────────────────────────
# CONFIRMANDO
# ─────────────────────────────────────────────────────────────

def confirmacao_resumo(
    service_name: str,
    prof_name: str,
    date_label: str,
    time_label: str,
) -> str:
    prof_display = (
        prof_name if prof_name and prof_name != "Qualquer disponível" else "—"
    )

    return (
        f"Confirme seu agendamento:\n\n"
        f"✂️ *{service_name}*\n"
        f"👤 {prof_display}\n"
        f"📅 {date_label} às {time_label}\n\n"
        f"Tudo certo?"
    )


def confirmacao_fallback(*args, **kwargs) -> str:
    return (
        confirmacao_resumo(*args, **kwargs)
        + "\n\n"
        + format_options(CONFIRMANDO_OPTIONS)
    )


def agendamento_confirmado(
    first_name: str,
    service_name: str,
    prof_name: str,
    slot_label: str,
    min_hours_cancel: int,
) -> str:
    despedida = (
        f"Te esperamos, {first_name}! 💈" if first_name else "Te esperamos! 💈"
    )

    return (
        f"✅ *Agendamento confirmado!*\n\n"
        f"✂️ {service_name} com {prof_name}\n"
        f"📅 {slot_label}\n\n"
        f"{despedida}\n"
        f"_Cancelamentos ou reagendamentos devem ser feitos com pelo menos {min_hours_cancel}h de antecedência._"
    )


def cancelamento_pelo_usuario(first_name: str = "") -> str:
    if first_name:
        return f"Tudo certo, {first_name}! Se precisar, é só chamar. 😊"
    return "Tudo certo! Se precisar, é só chamar. 😊"

HORARIO_OCUPADO_CONFIRMANDO = (
    "😬 Esse horário acabou de ser ocupado! Veja os próximos disponíveis:"
)

ERRO_CONFIRMAR_AGENDAMENTO = (
    "❌ Não foi possível confirmar o agendamento. Tente novamente."
)

# ─────────────────────────────────────────────────────────────
# VER AGENDAMENTOS
# ─────────────────────────────────────────────────────────────


def sem_agendamentos_ativos(first_name: str = "") -> str:
    prefixo = f"{first_name}, você não tem" if first_name else "Você não tem"

    return (
        f"😅 {prefixo} agendamentos ativos no momento.\n\n"
        f"Digite *1* para agendar um horário."
    )


def lista_agendamentos_descricao(first_name: str = "") -> str:
    if first_name:
        return f"Clique em um agendamento para gerenciar, {first_name}:"
    return "Clique para gerenciar:"

# ─────────────────────────────────────────────────────────────
# GERENCIAMENTO
# ─────────────────────────────────────────────────────────────


def gerenciar_agendamento(
    service_name: str,
    prof_name: str,
    slot_label: str,
) -> str:
    return (
        f"*{service_name}* com {prof_name}\n"
        f"📅 {slot_label}\n\n"
        f"O que você deseja fazer?"
    )


def reagendamento_fora_prazo(min_hours: int) -> str:
    return (
        f"⚠️ O prazo para reagendamento já passou (mínimo {min_hours}h antes).\n"
        "Neste caso você só pode cancelar o agendamento."
    )

# ─────────────────────────────────────────────────────────────
# CANCELAMENTO
# ─────────────────────────────────────────────────────────────


def cancelamento_fora_prazo(msg: str) -> str:
    return (
        f"⚠️ Não é possível cancelar agora.\n\n{msg}\n\n"
        "Se precisar de ajuda, fale com a gente! ☎️"
    )


def confirmacao_cancelamento(slot_label: str) -> str:
    return (
        f"Confirma o cancelamento?\n\n"
        f"📅 {slot_label}\n\n"
        f"⚠️ Essa ação não pode ser desfeita."
    )


def cancelamento_confirmado(first_name: str = "") -> str:
    despedida = (
        f"Esperamos te ver em breve, {first_name}! 😊"
        if first_name
        else "Esperamos te ver em breve! 😊"
    )

    return f"✅ Agendamento cancelado com sucesso.\n{despedida}"

ERRO_CANCELAR_AGENDAMENTO = (
    "❌ Não foi possível cancelar. Tente novamente ou fale com a gente."
)

# ─────────────────────────────────────────────────────────────
# REAGENDAMENTO
# ─────────────────────────────────────────────────────────────


def reagendamento_confirmado(first_name: str, slot_label: str) -> str:
    despedida = (
        f"Te esperamos, {first_name}! 💈" if first_name else "Te esperamos! 💈"
    )

    return (
        f"✅ *Reagendado com sucesso!*\n\n"
        f"📅 {slot_label}\n\n"
        f"{despedida}"
    )

HORARIO_OCUPADO_REAGENDANDO = (
    "😬 Esse horário acabou de ser ocupado! Escolha outro:"
)

ERRO_REAGENDAR_AGENDAMENTO = (
    "❌ Não foi possível remarcar. Tente novamente."
)

# ─────────────────────────────────────────────────────────────
# ERROS GENÉRICOS
# ─────────────────────────────────────────────────────────────

ERRO_GENERICO = (
    "Ops! 😅 Ocorreu um erro inesperado. Tente novamente em instantes."
)

INPUT_INVALIDO = "Ops! Escolha uma das opções acima. 😊"
