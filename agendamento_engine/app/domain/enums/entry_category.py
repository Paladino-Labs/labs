"""
Categorias de Entry — organizadas por tipo contábil.

Usado em: Entry.category, create_manual_adjustment, aggregate_dre.
"""
from enum import Enum


class EntryCategory(str, Enum):
    # ── RECEITA ──────────────────────────────────────────────────────────────
    SERVICOS = "SERVICOS"
    PRODUTOS = "PRODUTOS"
    PACOTE = "PACOTE"
    ASSINATURA_ADESAO = "ASSINATURA_ADESAO"
    ASSINATURA_RENOVACAO = "ASSINATURA_RENOVACAO"
    SINAL_SERVICO = "SINAL_SERVICO"
    RECEITA_OUTROS = "RECEITA_OUTROS"

    # ── CUSTO ────────────────────────────────────────────────────────────────
    INSUMOS_USO_INTERNO = "INSUMOS_USO_INTERNO"
    PRODUTO_VENDIDO = "PRODUTO_VENDIDO"
    MATERIAL_DESCARTAVEL = "MATERIAL_DESCARTAVEL"
    PERDA_ESTOQUE = "PERDA_ESTOQUE"
    PERDA_OPERACIONAL = "PERDA_OPERACIONAL"
    CUSTO_OUTROS = "CUSTO_OUTROS"

    # ── DESPESA ──────────────────────────────────────────────────────────────
    ALUGUEL = "ALUGUEL"
    UTILITIES = "UTILITIES"
    MARKETING = "MARKETING"
    SOFTWARE = "SOFTWARE"
    CONTABILIDADE = "CONTABILIDADE"
    LIMPEZA = "LIMPEZA"
    MANUTENCAO = "MANUTENCAO"
    SALARIO = "SALARIO"
    SERVICOS_PJ = "SERVICOS_PJ"
    ALIMENTACAO_COPA = "ALIMENTACAO_COPA"
    EQUIPAMENTOS = "EQUIPAMENTOS"
    TAXAS_BANCARIAS = "TAXAS_BANCARIAS"
    TREINAMENTO = "TREINAMENTO"
    DESPESA_OUTROS = "DESPESA_OUTROS"

    # ── TAXA ─────────────────────────────────────────────────────────────────
    ACQUIRER_FEE = "ACQUIRER_FEE"
    WITHDRAW_FEE = "WITHDRAW_FEE"
    ANTECIPATION_FEE = "ANTECIPATION_FEE"
    TAXA_OUTROS = "TAXA_OUTROS"

    # ── COMISSAO ─────────────────────────────────────────────────────────────
    COMISSAO_SERVICO = "COMISSAO_SERVICO"
    COMISSAO_VENDA = "COMISSAO_VENDA"
    COMISSAO_RENOVACAO = "COMISSAO_RENOVACAO"
    COMISSAO_PERSONALIZADA = "COMISSAO_PERSONALIZADA"

    # ── ESTORNO ──────────────────────────────────────────────────────────────
    REEMBOLSO_CLIENTE = "REEMBOLSO_CLIENTE"
    CHARGEBACK = "CHARGEBACK"
    REVERSAO_TAXA = "REVERSAO_TAXA"

    # ── AJUSTE ───────────────────────────────────────────────────────────────
    CONTAGEM_CAIXA = "CONTAGEM_CAIXA"
    CONTAGEM_ESTOQUE = "CONTAGEM_ESTOQUE"
    CORRECAO_LANCAMENTO = "CORRECAO_LANCAMENTO"
    CORRECAO_COMISSAO = "CORRECAO_COMISSAO"
    AJUSTE_OUTROS = "AJUSTE_OUTROS"


# Mapeamento category → entry_type (para validações e aggregate_dre)
CATEGORY_TO_ENTRY_TYPE: dict[str, str] = {
    # RECEITA
    EntryCategory.SERVICOS: "RECEITA",
    EntryCategory.PRODUTOS: "RECEITA",
    EntryCategory.PACOTE: "RECEITA",
    EntryCategory.ASSINATURA_ADESAO: "RECEITA",
    EntryCategory.ASSINATURA_RENOVACAO: "RECEITA",
    EntryCategory.SINAL_SERVICO: "RECEITA",
    EntryCategory.RECEITA_OUTROS: "RECEITA",
    # CUSTO
    EntryCategory.INSUMOS_USO_INTERNO: "CUSTO",
    EntryCategory.PRODUTO_VENDIDO: "CUSTO",
    EntryCategory.MATERIAL_DESCARTAVEL: "CUSTO",
    EntryCategory.PERDA_ESTOQUE: "CUSTO",
    EntryCategory.PERDA_OPERACIONAL: "CUSTO",
    EntryCategory.CUSTO_OUTROS: "CUSTO",
    # DESPESA
    EntryCategory.ALUGUEL: "DESPESA",
    EntryCategory.UTILITIES: "DESPESA",
    EntryCategory.MARKETING: "DESPESA",
    EntryCategory.SOFTWARE: "DESPESA",
    EntryCategory.CONTABILIDADE: "DESPESA",
    EntryCategory.LIMPEZA: "DESPESA",
    EntryCategory.MANUTENCAO: "DESPESA",
    EntryCategory.SALARIO: "DESPESA",
    EntryCategory.SERVICOS_PJ: "DESPESA",
    EntryCategory.ALIMENTACAO_COPA: "DESPESA",
    EntryCategory.EQUIPAMENTOS: "DESPESA",
    EntryCategory.TAXAS_BANCARIAS: "DESPESA",
    EntryCategory.TREINAMENTO: "DESPESA",
    EntryCategory.DESPESA_OUTROS: "DESPESA",
    # TAXA
    EntryCategory.ACQUIRER_FEE: "TAXA",
    EntryCategory.WITHDRAW_FEE: "TAXA",
    EntryCategory.ANTECIPATION_FEE: "TAXA",
    EntryCategory.TAXA_OUTROS: "TAXA",
    # COMISSAO
    EntryCategory.COMISSAO_SERVICO: "COMISSAO",
    EntryCategory.COMISSAO_VENDA: "COMISSAO",
    EntryCategory.COMISSAO_RENOVACAO: "COMISSAO",
    EntryCategory.COMISSAO_PERSONALIZADA: "COMISSAO",
    # ESTORNO
    EntryCategory.REEMBOLSO_CLIENTE: "ESTORNO",
    EntryCategory.CHARGEBACK: "ESTORNO",
    EntryCategory.REVERSAO_TAXA: "ESTORNO",
    # AJUSTE
    EntryCategory.CONTAGEM_CAIXA: "AJUSTE",
    EntryCategory.CONTAGEM_ESTOQUE: "AJUSTE",
    EntryCategory.CORRECAO_LANCAMENTO: "AJUSTE",
    EntryCategory.CORRECAO_COMISSAO: "AJUSTE",
    EntryCategory.AJUSTE_OUTROS: "AJUSTE",
}
