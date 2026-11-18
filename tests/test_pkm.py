import pytest
from pathlib import Path

from utils import eh_organizacao, eh_nome_valido_pessoa
from extractor import extrair_id_youtube, formatar_tempo
from canonicalizer import norm, chave_bloqueio, Canonicalizer


# ==========================================
# TESTES DE UTILS (Validação de Entidades)
# ==========================================

def test_eh_organizacao():
    assert eh_organizacao("OpenAI") is True
    assert eh_organizacao("Google DeepMind") is True
    assert eh_organizacao("Anthropic") is True
    assert eh_organizacao("João Silva") is False
    assert eh_organizacao("") is False


def test_eh_nome_valido_pessoa():
    assert eh_nome_valido_pessoa("Sarah Friar") is True
    assert eh_nome_valido_pessoa("Satya Nadella") is True
    assert eh_nome_valido_pessoa("Sarah") is False  # Falha por ter apenas um token
    assert eh_nome_valido_pessoa("OpenAI") is False  # É organização, logo nome de pessoa inválido


# ==========================================
# TESTES DO EXTRACTOR (YouTube & Tempos)
# ==========================================

def test_extrair_id_youtube():
    url_padrao = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    url_curto = "https://youtu.be/dQw4w9WgXcQ"
    url_embed = "https://www.youtube.com/embed/dQw4w9WgXcQ"
    
    assert extrair_id_youtube(url_padrao) == "dQw4w9WgXcQ"
    assert extrair_id_youtube(url_curto) == "dQw4w9WgXcQ"
    assert extrair_id_youtube(url_embed) == "dQw4w9WgXcQ"
    assert extrair_id_youtube("https://exemplo.com/video") is None


def test_formatar_tempo():
    assert formatar_tempo(45) == "[00:45]"
    assert formatar_tempo(75) == "[01:15]"
    assert formatar_tempo(3665) == "[01:01:05]"


# ==========================================
# TESTES DO CANONICALIZER
# ==========================================

def test_norm():
    assert norm("José António, Ph.D.!") == "jose antonio ph d"
    assert norm("  GPT-4o (Advanced) ") == "gpt 4o advanced"
    assert norm("") == ""


def test_chave_bloqueio():
    assert chave_bloqueio("Satya Nadella") == "nadella"
    assert chave_bloqueio("OpenAI") == "openai"
    assert chave_bloqueio("") == ""


def test_canonicalizer_fluxo_isolado(tmp_path: Path):
    # Usa diretório temporário do pytest para isolar os ficheiros de suporte
    aliases_f = tmp_path / "aliases.yaml"
    decisoes_f = tmp_path / "decisoes.jsonl"
    revisao_f = tmp_path / "revisao.md"

    canon = Canonicalizer(
        aliases_path=aliases_f,
        decisoes_path=decisoes_f,
        revisao_path=revisao_f,
        threshold_fusao_auto=95,
    )

    # Testar resolução inicial de nome novo (deve cair em fallback)
    canonical, decisao = canon._resolver("pessoa", "Jason Liu")
    assert canonical == "Jason Liu"
    assert decisao.metodo == "fallback"

    # Simular registo de fusão e aprendizagem de alias
    canon._registar_fusao("pessoa", "Jason Liu", "Jason L.", decisao)
    canon.gravar()

    assert aliases_f.exists()
    assert decisoes_f.exists()