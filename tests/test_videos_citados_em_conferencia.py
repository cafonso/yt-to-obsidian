from pathlib import Path
from types import SimpleNamespace
import pytest

from models import PalestraAnalise, VideoCitado
from vault_writer import ObsidianVaultWriter


@pytest.fixture
def writer(tmp_path: Path) -> ObsidianVaultWriter:
    vault = tmp_path / "vault"
    vault.mkdir()
    return ObsidianVaultWriter(vault)


def _dados_video() -> dict:
    return {
        "id": "vidConf1234",
        "url": "https://youtu.be/vidConf1234",
        "titulo": "Conferência Dia 1",
        "data": "2026-11-20",
        "canal": "Canal Conferência",
        "canal_url": "https://youtube.com/@canalconf",
    }


def _agenda() -> SimpleNamespace:
    return SimpleNamespace(
        nome_conferencia="Conferência Teste",
        dia=1,
        dia_rotulo="Dia 1",
        data_sessao="2026-11-20",
    )


def _sessao() -> SimpleNamespace:
    return SimpleNamespace(
        ordem=1,
        titulo_palestra="Arquitetura de Agentes",
        orador_principal="Ana Silva",
        organizacao="Acme",
        timestamp_inicio="00:10:00",
        timestamp_fim="00:45:00",
        segundos_inicio=600,
    )


def test_salvar_palestra_conferencia_inclui_videos_citados(writer: ObsidianVaultWriter, monkeypatch):
    monkeypatch.setattr(
        writer,
        "_resolver_video_citado",
        lambda v, _hist: ("Vídeo Já Gravado", "2026-10-01 - Vídeo Já Gravado"),
    )

    analise = PalestraAnalise(
        titulo_palestra="Arquitetura de Agentes",
        resumo_executivo="Resumo de teste.",
        takeaways_principais=["Ponto 1"],
        videos_citados=[
            VideoCitado(
                titulo_ou_assunto="Vídeo Já Gravado",
                url_ou_id="vidGrav0001",
                canal_ou_orador="Canal X",
                contexto="comparação de latência",
            )
        ],
    )

    caminho = writer.salvar_palestra_conferencia(
        _dados_video(),
        _agenda(),
        _sessao(),
        analise,
        data_leitura="2026-11-24",
        historico={"vidGrav0001": {"stem": "2026-10-01 - Vídeo Já Gravado"}},
    )

    conteudo = caminho.read_text(encoding="utf-8")
    assert caminho.exists()
    assert '"[[2026-10-01 - Vídeo Já Gravado]]"' in conteudo
    assert "## 🎬 Vídeos Citados / Referenciados" in conteudo
    assert "**Vídeo Já Gravado**" in conteudo


def test_salvar_palestra_conferencia_sem_videos_citados(writer: ObsidianVaultWriter):
    analise = PalestraAnalise(
        titulo_palestra="Arquitetura de Agentes",
        resumo_executivo="Resumo de teste.",
        takeaways_principais=["Ponto 1"],
        videos_citados=[],
    )

    caminho = writer.salvar_palestra_conferencia(
        _dados_video(),
        _agenda(),
        _sessao(),
        analise,
        data_leitura="2026-11-24",
        historico={},
    )

    conteudo = caminho.read_text(encoding="utf-8")
    assert caminho.exists()
    assert "## 🎬 Vídeos Citados / Referenciados" not in conteudo