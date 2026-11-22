import pytest
from pathlib import Path

from utils import eh_organizacao, eh_nome_valido_pessoa
from extrator import extrair_id_youtube, formatar_tempo
from canonicalizer import norm, chave_bloqueio, Canonicalizer


from models import ArtefactoIA, ObraCitada, PessoaMencionada
import yaml

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
    

def test_validacao_pessoa_e_organizacao_casos_limite() -> None:
    assert eh_nome_valido_pessoa("Jordan Ellenberg") is True
    assert eh_nome_valido_pessoa("jordan ellenberg") is True
    assert eh_nome_valido_pessoa("Monónimo") is False
    assert eh_nome_valido_pessoa("   ") is False
    assert isinstance(eh_organizacao("Ruby Central"), bool)

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
    
def test_canonicalizer_carrega_aliases_de_yaml_existente(tmp_path) -> None:
    aliases_file = tmp_path / "aliases.yaml"
    decisoes_file = tmp_path / "decisoes.jsonl"
    revisao_file = tmp_path / "revisao.md"

    aliases_file.write_text(
        yaml.safe_dump(
            {
                "tema": {
                    "Fine-Tuning": ["Fine Tuning", "fine tuning"],
                }
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    c = Canonicalizer(
        aliases_path=aliases_file,
        decisoes_path=decisoes_file,
        revisao_path=revisao_file,
    )
    assert c.canonicalizar_strings("tema", ["Fine Tuning", "fine tuning"]) == ["Fine-Tuning"]
    
def test_canonicalizar_strings_tipo_invalido_levanta_value_error(tmp_path) -> None:
    c = Canonicalizer(
        aliases_path=tmp_path / "aliases.yaml",
        decisoes_path=tmp_path / "decisoes.jsonl",
        revisao_path=tmp_path / "revisao.md",
    )
    with pytest.raises(ValueError):
        c.canonicalizar_strings("temas", ["LLM"])
        
def test_canonicalizer_persiste_aliases_e_recarrega(tmp_path) -> None:
    aliases_file = tmp_path / "aliases.yaml"
    decisoes_file = tmp_path / "decisoes.jsonl"
    revisao_file = tmp_path / "revisao.md"

    c1 = Canonicalizer(aliases_path=aliases_file, decisoes_path=decisoes_file, revisao_path=revisao_file)
    resultado = c1.canonicalizar_strings("tema", ["Fine-Tuning", "Fine Tuning", "LLM"])
    assert resultado == ["Fine-Tuning", "LLM"]   # explícito em vez de len == 2
    c1.gravar()

    # Verifica o conteúdo do aliases.yaml antes de recarregar
    import yaml
    aliases = yaml.safe_load(aliases_file.read_text(encoding="utf-8"))
    assert "Fine-Tuning" in aliases["tema"]
    assert "Fine Tuning" not in aliases["tema"]   # "Fine Tuning" é alias, não canónico

    c2 = Canonicalizer(aliases_path=aliases_file, decisoes_path=decisoes_file, revisao_path=revisao_file)
    assert c2.canonicalizar_strings("tema", ["Fine Tuning"]) == ["Fine-Tuning"]