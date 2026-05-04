"""
Testes unitários para mask_cpf_cnpj (Sprint 0.0b).
"""
import pytest
from app.core.logging import mask_cpf_cnpj


# ─── CPF ──────────────────────────────────────────────────────────────────────

def test_mask_cpf_returns_masked_pattern():
    assert mask_cpf_cnpj("123.456.789-09") == "***.456.789-**"


def test_mask_cpf_inside_sentence():
    result = mask_cpf_cnpj("cliente CPF 123.456.789-09 registrado")
    assert result == "cliente CPF ***.456.789-** registrado"


def test_mask_cpf_preserves_middle_digits():
    result = mask_cpf_cnpj("987.654.321-00")
    assert result == "***.654.321-**"


# ─── CNPJ ─────────────────────────────────────────────────────────────────────

def test_mask_cnpj_returns_masked_pattern():
    assert mask_cpf_cnpj("12.345.678/0001-90") == "**.345.678/0001-**"


def test_mask_cnpj_inside_sentence():
    result = mask_cpf_cnpj("empresa CNPJ 12.345.678/0001-90 ativa")
    assert result == "empresa CNPJ **.345.678/0001-** ativa"


def test_mask_cnpj_preserves_middle_segment():
    result = mask_cpf_cnpj("99.888.777/0002-35")
    assert result == "**.888.777/0002-**"


# ─── Strings sem documento ────────────────────────────────────────────────────

def test_no_document_returns_intact():
    msg = "agendamento criado para João às 10h"
    assert mask_cpf_cnpj(msg) == msg


def test_empty_string_returns_empty():
    assert mask_cpf_cnpj("") == ""


def test_partial_cpf_not_masked():
    assert mask_cpf_cnpj("123.456") == "123.456"


def test_partial_cnpj_not_masked():
    assert mask_cpf_cnpj("12.345.678") == "12.345.678"


# ─── Múltiplos documentos no mesmo texto ─────────────────────────────────────

def test_multiple_documents_all_masked():
    text = "CPF 111.222.333-44 e CNPJ 55.666.777/0001-88"
    result = mask_cpf_cnpj(text)
    assert result == "CPF ***.222.333-** e CNPJ **.666.777/0001-**"
