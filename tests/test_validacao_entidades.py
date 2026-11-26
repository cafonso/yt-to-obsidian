#tests/test_validacao_entidades.py
from pathlib import Path
import pytest

from models import AnaliseVideo, ArtefactoIA, ObraCitada, PessoaMencionada
from utils import eh_nome_valido_pessoa, eh_organizacao
from vault.core import ObsidianVaultWriter


@pytest.mark.parametrize(
    "nome,esperado",
    [
        ("João Silva", True),
        ("Andrej Karpathy", True),
        ("Ana Maria Ferreira", True),
        ("João", False),          # primeiro nome solto
        ("OpenAI", False),        # organização não é pessoa válida
        ("MIT", False),
        ("", False),
        ("   ", False),
        ("et al.", False),
    ],
)
def test_eh_nome_valido_pessoa(nome: str, esperado: bool):
    assert eh_nome_valido_pessoa(nome) is esperado


@pytest.mark.parametrize(
    "nome,esperado",
    [
        ("OpenAI", True),
        ("Google DeepMind", True),
        ("MIT", True),
        ("Hugging Face", True),
        ("João Silva", False),
        ("Andrej Karpathy", False),
        ("", False),
        ("   ", False),
    ],
)
def test_eh_organizacao(nome: str, esperado: bool):
    assert eh_organizacao(nome) is esperado


def test_extrair_entidades_base_reencaminha_org_em_pessoas(tmp_path: Path):
    writer = ObsidianVaultWriter(str(tmp_path), validar_links=False)
    pessoas = [
        PessoaMencionada(nome="Demis Hassabis", papel_ou_bio="CEO da DeepMind."),
        PessoaMencionada(nome="Google DeepMind", papel_ou_bio="Laboratório de IA."),
        PessoaMencionada(nome="Lucas", papel_ou_bio="Nome incompleto."),
    ]

    pessoas_validas, orgs_todas = writer._extrair_entidades_base(pessoas, ["OpenAI"])

    assert [p.nome for p in pessoas_validas] == ["Demis Hassabis"]
    assert "Google DeepMind" in orgs_todas
    assert "OpenAI" in orgs_todas
    assert "Lucas" not in orgs_todas


def test_salvar_video_filtra_pessoas_e_encaminha_org_e_fabricante(tmp_path: Path):
    writer = ObsidianVaultWriter(str(tmp_path), validar_links=False)
    dados_video = {
        "titulo": "Sistemas Multi-Agente em Produção",
        "canal": "Anthropic",
        "canal_url": "https://www.youtube.com/@AnthropicAI",
        "data": "2026-11-26",
        "url": "https://www.youtube.com/watch?v=teste_val_01",
        "descricao": "Discussão sobre agentes.",
    }
    analise = AnaliseVideo(
        titulo_sugerido="Sistemas Multi-Agente em Produção",
        resumo_executivo="Resumo curto para teste.",
        takeaways_principais=["Ponto 1"],
        temas=["Agentes"],
        pessoas=[
            PessoaMencionada(nome="Chris Olah", papel_ou_bio="Investigador de interpretabilidade."),
            PessoaMencionada(nome="Anthropic", papel_ou_bio="Empresa de IA."),
            PessoaMencionada(nome="Sam", papel_ou_bio="Apenas primeiro nome."),
        ],
        obras=[
            ObraCitada(
                titulo="Superintelligence",
                tipo="Livro",
                autores=["Nick Bostrom", "DeepMind"],
                contexto="Referência histórica.",
            )
        ],
        organizacoes=["DeepMind"],
        artefactos=[
            ArtefactoIA(
                nome="Claude Code",
                subtipo="ferramenta",
                fabricante_ou_autor="Anthropic",
                descricao="Ferramenta de linha de comandos.",
            )
        ],
    )

    caminho_nota = writer.salvar_video(dados_video, analise, data_leitura="2026-11-26")
    conteudo_nota = caminho_nota.read_text(encoding="utf-8")

    assert (tmp_path / "Pessoas" / "Chris Olah.md").exists()
    assert not (tmp_path / "Pessoas" / "Anthropic.md").exists()
    assert not (tmp_path / "Pessoas" / "Sam.md").exists()
    assert (tmp_path / "Organizações" / "Anthropic.md").exists()
    assert (tmp_path / "Organizações" / "DeepMind.md").exists()
    assert "[[Chris Olah]]" in conteudo_nota
    assert "[[Sam]]" not in conteudo_nota