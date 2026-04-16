"""
Templates de mensagem do bot de agendamento.

Todas as strings enviadas ao usuário via WhatsApp estão aqui.
O bot_service.py não deve conter strings de interface — apenas chamadas a este módulo.

Convenção:
  - Funções que recebem variáveis retornam str formatado.
  - Strings fixas são constantes MODULE-LEVEL (maiúsculas).
  - Nenhuma lógica de negócio aqui — apenas formatação.
"""

from app.core.config import settings


# ─── INICIO / Identificação ───────────────────────────────────────────────────

def boas_vindas_novo(company_name: str) -> str:
    return f"""Fala, beleza? 👋

Mais uma carinha nova por aqui, bem-vindo à *{company_name}*!!

Qual é o seu nome?"""


# ─── AGUARDANDO_NOME ──────────────────────────────────────────────────────────


def confirmar_nome(nome: str) -> str:
    return f"""Seu nome é *{nome}*, certo?

1️⃣ Sim
2️⃣ Corrigir"""


PEDIR_NOME_NOVAMENTE = (
    "Pode me dizer seu nome novamente? 😊"
)


def boas_vindas_nome_confirmado(first_name: str) -> str:
    return f"""Prazer, {first_name}! 😄

Vamos agendar seu horário."""


# ─── OFERTA_RECORRENTE ────────────────────────────────────────────────────────


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


OFERTA_EXPIRADA = (
    "⏰ O tempo de reserva expirou. Vou buscar os próximos horários disponíveis..."
)

ESCOLHA_OPCAO = "Escolha uma das opções acima. 😊"
ESCOLHA_OPCAO_OPS = "Ops! Escolha uma das opções acima. 😊"


# ─── CHAMADO_HUMANO ───────────────────────────────────────────────────────


HUMANO_CHAMADO = "Ok! Vou chamar um atendente agora. Aguarde um momento… ☎️"


# ─── MENU_PRINCIPAL ───────────────────────────────────────────────────────


def menu_principal(name: str) -> str:
    return f"""Beleza, {name}! 👋

O que você quer fazer?

1️⃣ Agendar horário
2️⃣ Ver meus agendamentos
3️⃣ Falar com atendente"""


# ─── ESCOLHENDO_SERVICO ───────────────────────────────────────────────────────

SEM_SERVICOS = (
    "😔 Não há serviços disponíveis no momento. "
    "Entre em contato conosco para mais informações."
)


def escolha_servico(first_name: str = "") -> str:
    if first_name:
        return f"Qual serviço você gostaria, {first_name}?"
    return "Qual serviço você gostaria?"


# ─── ESCOLHENDO_PROFISSIONAL ──────────────────────────────────────────────────

def escolha_profissional(service_name: str) -> str:
    return f"Com quem você quer agendar *{service_name}*?"


# ─── ESCOLHENDO_HORARIO ───────────────────────────────────────────────────────

SEM_HORARIOS = (
    "😔 Não encontrei horários disponíveis para esse período. "
    "Tente outra data ou entre em contato conosco!"
)


def escolha_horario(service_name: str, prof_name: str = "") -> str:
    if prof_name and prof_name != "Qualquer disponível":
        return f"Escolha um horário para *{service_name}* com *{prof_name}*:"
    return f"Escolha um horário para *{service_name}*:"


# ─── ESCOLHENDO_DATA ──────────────────────────────────────────────────────────

def escolha_data_titulo(service_name: str) -> str:
    return f"📅 Escolha a data para {service_name}"


def escolha_data_descricao(first_name: str = "", prof_name: str = "") -> str:
    desc = f"Para qual dia, {first_name}?" if first_name else "Para qual dia?"
    if prof_name and prof_name != "Qualquer disponível":
        desc += f"\n_Profissional: {prof_name}_"
    return desc


# ─── CONFIRMANDO ─────────────────────────────────────────────────────────────

def confirmacao_resumo(
    service_name: str,
    prof_name: str,
    date_label: str,
    time_label: str,
) -> str:
    prof_display = prof_name if prof_name and prof_name != "Qualquer disponível" else "—"
    return (
        f"Confirme seu agendamento:\n\n"
        f"✂️ *{service_name}*\n"
        f"👤 {prof_display}\n"
        f"📅 {date_label} às {time_label}\n\n"
        f"Tudo certo?"
    )


def confirmacao_fallback(
    service_name: str,
    prof_name: str,
    date_label: str,
    time_label: str,
) -> str:
    return (
        confirmacao_resumo(service_name, prof_name, date_label, time_label)
        + "\n\n1 - ✅ Confirmar\n2 - 🕐 Alterar horário\n3 - ❌ Cancelar"
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
        f"_Lembre-se: cancelamentos ou reagendamentos devem ser feitos com "
        f"pelo menos {min_hours_cancel}h de antecedência._"
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

ERRO_DADOS_INCOMPLETOS = "❌ Erro interno. Tente novamente."


# ─── VER_AGENDAMENTOS ─────────────────────────────────────────────────────────

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


# ─── GERENCIANDO_AGENDAMENTO ──────────────────────────────────────────────────

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
        f"⚠️ O prazo para reagendamento já passou "
        f"(mínimo {min_hours}h antes).\n"
        "Neste caso você só pode cancelar o agendamento."
    )


# ─── CANCELANDO ───────────────────────────────────────────────────────────────

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


# ─── REAGENDANDO ─────────────────────────────────────────────────────────────

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


# ─── Erros genéricos ─────────────────────────────────────────────────────────

ERRO_GENERICO = (
    "Ops! 😅 Ocorreu um erro inesperado. Tente novamente em instantes."
)

INPUT_INVALIDO = "Ops! Escolha uma das opções acima. 😊"

