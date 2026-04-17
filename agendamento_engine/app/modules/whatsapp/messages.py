"""
Templates de mensagem do bot de agendamento.
 
Todas as strings enviadas ao usuário via WhatsApp estão aqui.
O bot_service.py não deve conter strings de interface — apenas chamadas a este módulo.
 
Convenção:
  - Funções que recebem variáveis retornam str formatado.
  - Strings fixas são constantes MODULE-LEVEL (maiúsculas).
  - Nenhuma lógica de negócio aqui — apenas formatação.
  - Helpers privados (_) centralizam padrões repetidos.
"""
 
from app.core.config import settings
 
 
# ─── Helpers privados ─────────────────────────────────────────────────────────
 
def _format_professional(prof_name: str | None) -> str:
    """Normaliza exibição de profissional. None/vazio/sentinel → 'Qualquer profissional'."""
    if not prof_name or prof_name == "Qualquer disponível":
        return "Qualquer profissional"
    return prof_name
 
 
def _format_slot(slot_label: str) -> str:
    """Garante que slot_label está sempre no formato esperado nas mensagens."""
    return slot_label or "—"
 
 
# ─── INICIO / Identificação ───────────────────────────────────────────────────
 
def boas_vindas_novo(company_name: str) -> str:
    return (
        f"Fala, beleza? 👋\n\n"
        f"Mais uma carinha nova por aqui, bem-vindo à *{company_name}*!!\n\n"
        f"Qual é o seu nome?"
    )
 
 
# ─── AGUARDANDO_NOME ──────────────────────────────────────────────────────────
 
def confirmar_nome(nome: str) -> str:
    return (
        f"Opa, *{nome}*, certo?\n\n"
        f"1️⃣ Sim\n"
        f"2️⃣ Corrigir"
    )
 
 
PEDIR_NOME_NOVAMENTE = "Pode me dizer seu nome novamente? 😊"
 
 
def boas_vindas_nome_confirmado(first_name: str) -> str:
    return f"Prazer, {first_name}! 😄\n\nVamos agendar seu horário."


# ─── OFERTA_RECORRENTE ────────────────────────────────────────────────────────


def oferta_recorrente(
    name: str,
    service_name: str,
    prof_name: str,
    slot_label: str,
    offer_ttl_minutes: int,
) -> str:
    prof_display = _format_professional(prof_name)
    return (
        f"Fala, {name}! 👋\n\n"
        f"Encontrei um horário pra você 👇\n\n"
        f"💈 *{service_name}*\n"
        f"👤 {prof_display}\n"
        f"🕒 {_format_slot(slot_label)}\n\n"
        f"_Reservei pra você por {offer_ttl_minutes} min._\n\n"
        f"Posso confirmar?"
    )
 
 
def confirmacao_agendamento_recorrente(
    name: str,
    service_name: str,
    prof_name: str,
    slot_label: str,
) -> str:
    prof_display = _format_professional(prof_name)
    return (
        f"✅ Pronto, {name}!\n\n"
        f"Seu *{service_name}* com {prof_display} está agendado para *{_format_slot(slot_label)}*.\n\n"
        f"⚠️ Cancelamento ou reagendamento deve ser feito no máximo "
        f"{settings.APPOINTMENT_MIN_HOURS_BEFORE_CANCEL}h antes do horário."
    )
 
 
def escolher_outro_horario(name: str) -> str:
    return f"Claro, {name}! 👍\n\nQual horário você prefere?"
 
 
def escolher_outro_servico(name: str) -> str:
    return f"Ótimo, {name}! 😄\n\nQual serviço você deseja agendar?"
 
 
OFERTA_EXPIRADA = (
    "⏰ Esse horário não está mais disponível 😕\n\n"
    "Vou te mostrar outras opções 👍"
)
 
ESCOLHA_OPCAO = "Escolha uma das opções acima 👆"
 
ESCOLHA_OPCAO_OPS = "Não entendi 😅\n\nEscolhe uma das opções ali em cima 👆"


# ─── CHAMADO_HUMANO ───────────────────────────────────────────────────────


HUMANO_CHAMADO = "Ok! Vou chamar um atendente agora. Aguarde um momento… ☎️"


# ─── MENU_PRINCIPAL ───────────────────────────────────────────────────────


def menu_principal(name: str) -> str:
    return f"Beleza, {name}! 👋\n\nQual a boa de hoje?"


# ─── ESCOLHENDO_SERVICO ───────────────────────────────────────────────────────

SEM_SERVICOS = (
    "😕 No momento não temos serviços disponíveis.\n\n"
    "Vamos começar novamente?"
)


def escolha_servico(first_name: str = "") -> str:
    if first_name:
        return f"O que vamos agendar hoje, {first_name}?"
    return "O que vamos agendar hoje?"


# ─── ESCOLHENDO_PROFISSIONAL ──────────────────────────────────────────────────

def escolha_profissional(service_name: str) -> str:
    return f"Com quem você prefere?"


# ─── ESCOLHENDO_DATA ──────────────────────────────────────────────────────────


def escolha_data_titulo(service_name: str) -> str:
    return f"📅 Vamos escolher o dia"


def escolha_data_descricao(first_name: str = "", prof_name: str = "") -> str:
    desc = (
        f"Qual dia funciona melhor pra você, {first_name}? 👇"
        if first_name
        else "Qual dia funciona melhor pra você? 👇"
    )
    prof_display = _format_professional(prof_name)
    if prof_display != "Qualquer profissional":
        desc += f"\n\n👤 {prof_display}"
    return desc
  

# ─── ESCOLHENDO_HORARIO ───────────────────────────────────────────────────────


SEM_HORARIOS = (
    "😕 Não encontrei horários disponíveis para esse dia.\n\n"
    "Você pode escolher outra data ou falar com um atendente 👍"
)


def escolha_horario(service_name: str, prof_name: str = "") -> str:
    return "Bora deixar tudo na régua 😎\n\nEscolhe um horário pra você 👇"


# ─── CONFIRMANDO ─────────────────────────────────────────────────────────────

def confirmacao_resumo(
    service_name: str,
    prof_name: str,
    date_label: str,
    time_label: str,
) -> str:
    prof_display = _format_professional(prof_name)
    return (
        f"Aqui está seu agendamento:\n\n"
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
    prof_display = _format_professional(prof_name)
    despedida = f"Te esperamos, {first_name}! 💈" if first_name else "Te esperamos! 💈"
    return (
        f"✅ *Agendamento confirmado!*\n\n"
        f"✂️ {service_name} com {prof_display}\n"
        f"📅 {_format_slot(slot_label)}\n\n"
        f"{despedida}\n"
        f"_Lembre-se: cancelamentos ou reagendamentos devem ser feitos com "
        f"pelo menos {min_hours_cancel}h de antecedência._"
    )


def cancelamento_pelo_usuario(first_name: str = "") -> str:
    if first_name:
        return f"Tudo certo, {first_name}! Se precisar, é só chamar. 😊"
    return "Tudo certo! Se precisar, é só chamar. 😊"


HORARIO_OCUPADO_CONFIRMANDO = (
    "😬 Esse horário acabou de ser ocupado! Mas aqui vão os próximos disponíveis:"
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
    prof_display = _format_professional(prof_name)
    return (
        f"*{service_name}* com {prof_display}\n"
        f"📅 {_format_slot(slot_label)}\n\n"
    )


def reagendamento_fora_prazo(min_hours: int) -> str:
    return (
        f"⚠️ O prazo para reagendamento já passou "
        f"(mínimo {min_hours}h antes).\n"
        "Neste caso você pode falar com seu barbeiro."
    )


# ─── CANCELANDO ───────────────────────────────────────────────────────────────

def cancelamento_fora_prazo(msg: str) -> str:
    return (
        f"⚠️ Não é possível cancelar agora.\n\n{msg}\n\n"
        "Se precisar de ajuda, chame seu barbeiro! ☎️"
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
    "❌ Não foi possível cancelar. Tente novamente ou fale com seu barbeiro."
)


# ─── REAGENDANDO ─────────────────────────────────────────────────────────────

def reagendamento_confirmado(first_name: str, slot_label: str) -> str:
    despedida = f"Te esperamos, {first_name}! 💈" if first_name else "Te esperamos! 💈"
    return (
        f"✅ *Reagendado com sucesso!*\n\n"
        f"📅 {_format_slot(slot_label)}\n\n"
        f"{despedida}"
    )


HORARIO_OCUPADO_REAGENDANDO = (
    "😬 Esse horário acabou de ser ocupado! Mas temos outros:"
)

ERRO_REAGENDAR_AGENDAMENTO = (
    "❌ Não foi possível remarcar. Tente novamente."
)


# ─── Erros genéricos ─────────────────────────────────────────────────────────

ERRO_GENERICO = (
    "Ops! 😅 Ocorreu um erro inesperado. Tente novamente em instantes."
)

INPUT_INVALIDO = "Ops! Escolha uma das opções acima. 😊"
