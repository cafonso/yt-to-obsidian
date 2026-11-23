"""Casos-limite do fluxo de conferências (VideoAnalyzer).

Nota: duplicados de conferências NÃO são testados aqui — uma conferência é
um vídeo classificado, pelo que passa pelo mesmo `deve_saltar` (e --forcar)
coberto em test_regras_casos_limite.py.
"""
from unittest.mock import MagicMock

import pytest

from analyzer import VideoAnalyzer


@pytest.fixture
def analyzer(tmp_path, monkeypatch):
    # Evita criar o cliente Gemini real no __init__ (sem rede/API)
    monkeypatch.setattr("analyzer.genai.Client", lambda **kw: MagicMock())
    # Evita que o canonicalizer leia o vault durante o teste
    monkeypatch.setattr("analyzer._criar_canonicalizer", lambda p: MagicMock())
    return VideoAnalyzer(vault_path=tmp_path)


# --- executar_scout ---------------------------------------------------------

def test_scout_sem_capitulos_nem_transcricao_falha(analyzer):
    # dados vazios → _preparar_contexto_scout rebenta antes de chamar a API
    with pytest.raises(ValueError, match="Não há capítulos nem transcrição"):
        analyzer.executar_scout({})


def test_scout_devolve_none_falha(analyzer):
    # dados válidos (passam a preparação) mas a API devolve None
    analyzer._chamar_com_fallback = MagicMock(return_value=None)
    dados = {
        "titulo": "X",
        "transcricao_blocos": [{"start": 0, "text": "olá"}],
    }
    with pytest.raises(ValueError, match="Falha ao executar o Scout"):
        analyzer.executar_scout(dados)

# --- processar_conferencia_completa ----------------------------------------

def test_processar_conferencia_sem_transcricao_falha(analyzer):
    dados = {"transcricao_blocos": []}
    agenda = MagicMock()
    with pytest.raises(ValueError, match="sem transcrição"):
        analyzer.processar_conferencia_completa(dados, agenda, writer=MagicMock())


def test_processar_conferencia_sessao_sem_blocos_nao_rebenta(analyzer, capsys):
    # 1 sessão; blocos fora do intervalo e fora do fallback ±30s
    agenda = MagicMock()
    agenda.nome_conferencia = "TestConf"
    agenda.dia_rotulo = "Dia 1"
    agenda.dia = 1
    agenda.sessoes = [MagicMock(
        ordem=1,
        orador_principal="Orador",
        organizacao=None,
        titulo_palestra="Palestra X",
        timestamp_inicio="00:00",
        timestamp_fim="00:10",
        segundos_inicio=0,
        segundos_fim=600,
    )]
    dados = {"transcricao_blocos": [{"start": 9999, "text": "fora"}]}
    writer = MagicMock()

    # Não deve lançar; deve avisar e continuar
    analyzer.processar_conferencia_completa(dados, agenda, writer=writer)

    saida = capsys.readouterr().out
    assert "Transcrição vazia" in saida
    writer.salvar_palestra_conferencia.assert_not_called()