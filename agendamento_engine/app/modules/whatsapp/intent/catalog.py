"""Catálogo mestre de intenções do Estágio 0 (Sprint 2.0).

Catálogo dinâmico por tenant (invariante 5): intenções que dependem de um
módulo só ficam ativas se o ModuleActivation correspondente estiver ativo.

Nomes de módulo seguem o enum modulename real do banco (português):
ESTOQUE, PACOTES — não STOCK/PACKAGES.
"""

ALL_INTENTS = [
    "AGENDAR",
    "COMPRAR_PRODUTO",
    "COMPRAR_PACOTE",
    "CONSULTAR",
    "REMARCAR",
    "CANCELAR",
    "FALAR_COM_HUMANO",
]

# Mapeamento intenção → módulo necessário (valores do enum modulename)
INTENT_MODULE_REQUIREMENTS = {
    "COMPRAR_PRODUTO": "ESTOQUE",
    "COMPRAR_PACOTE": "PACOTES",
    # demais: sem restrição de módulo (FALAR_COM_HUMANO sempre ativo)
}


def is_module_active(module_activations, module_name: str) -> bool:
    """module_activations: lista de ModuleActivation do tenant."""
    for activation in module_activations or []:
        name = getattr(activation.module_name, "value", activation.module_name)
        if name == module_name:
            return bool(activation.is_active)
    return False


def get_active_intents(module_activations) -> list[str]:
    """Intenções habilitadas conforme ModuleActivation do tenant."""
    active = []
    for intent in ALL_INTENTS:
        required_module = INTENT_MODULE_REQUIREMENTS.get(intent)
        if required_module is None:
            active.append(intent)
        elif is_module_active(module_activations, required_module):
            active.append(intent)
    return active
