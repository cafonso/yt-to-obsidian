"""Casos-limite do fluxo principal em main.py."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import config
import main


def _criar_analise_mock(titulo: str = "Título Teste"):
    return SimpleNamespace(
        titulo_sugerido=titulo,
        pessoas=[],
        obras=[],
        organizacoes=[],
        artefactos=[],
        temas=[],
        capitulos=[],
    )


# --- 1. carregar_historico -------------------------------------------------

def test_carregar_historico_json_corrompido_devolve_vazio(tmp_path, caplog):
    ficheiro_hist = tmp_path / main.NOME_HISTORICO
    ficheiro_hist.write_text("{json invalido", encoding="utf-8")

    resultado = main.carregar_historico(ficheiro_hist)

    assert resultado == {}
    assert any("Não foi possível ler o histórico" in r.message for r in caplog.records)


# --- 2. processar_ficheiro_lista -------------------------------------------

def test_processar_ficheiro_lista_datas_e_linhas_invalidas(tmp_path, monkeypatch, capsys):
    lista = tmp_path / "lista.txt"
    lista.write_text(
        "\n".join([
            "# 2026-11-20",
            "# 2026-02-30",  # data impossível -> deve manter 2026-11-20
            "# comentário ignorado",
            "linha-invalida-sem-url",
            "https://www.youtube.com/watch?v=abc12345678",
        ]),
        encoding="utf-8",
    )

    extrator = MagicMock()
    extrator.validar_url_youtube.side_effect = lambda u: u.startswith("https://www.youtube.com/watch?v=")

    chamadas = []

    def _fake_processar_um_video(
        url,
        extrator,
        analyzer,
        writer,
        forcar=False,
        data_leitura=None,
        modo_conferencia=None,
        vault_path=None,
    ):
        chamadas.append((url, data_leitura, forcar, modo_conferencia, vault_path))
        return True

    monkeypatch.setattr(main, "processar_um_video", _fake_processar_um_video)

    main.processar_ficheiro_lista(
        str(lista),
        extrator=extrator,
        analyzer=MagicMock(),
        writer=MagicMock(),
        vault_path=tmp_path,
    )

    saida = capsys.readouterr().out
    assert "Data inválida encontrada '2026-02-30'" in saida
    assert "Linha ignorada" in saida
    assert chamadas == [
        ("https://www.youtube.com/watch?v=abc12345678", "2026-11-20", False, None, tmp_path)
    ]


# --- 3. Limpeza de áudio temporário no finally -----------------------------

def test_processar_um_video_apaga_audio_temporario_quando_analise_falha(tmp_path):
    audio_temp = tmp_path / "audio_temp.mp3"
    audio_temp.write_bytes(b"dados-de-audio-ficticios")

    extrator = MagicMock()
    extrator.extrair_tudo.return_value = {
        "titulo": "Vídeo com Falha",
        "canal": "Canal Teste",
        "transcricao": "Texto qualquer",
        "duracao_segundos": 120,
        "caminho_audio": str(audio_temp),
    }

    analyzer = MagicMock()
    analyzer.analisar.side_effect = RuntimeError("Falha simulada na API")

    writer = MagicMock()

    sucesso = main.processar_um_video(
        "https://www.youtube.com/watch?v=vid_erro_01",
        extrator=extrator,
        analyzer=analyzer,
        writer=writer,
        vault_path=tmp_path,
    )

    assert sucesso is False
    assert not audio_temp.exists()


# --- 4. Scout não deteta conferência -> cai no pipeline normal ------------

def test_processar_um_video_scout_nao_conferencia_segue_pipeline_normal(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LIMIAR_VIDEO_LONGO_SEGUNDOS", 60)

    extrator = MagicMock()
    extrator.extrair_tudo.return_value = {
        "titulo": "Monólogo Longo",
        "canal": "Canal Longo",
        "transcricao": "Linha 1\nLinha 2",
        "duracao_segundos": 3600,
        "caminho_audio": None,
    }

    analyzer = MagicMock()
    analyzer.executar_scout.return_value = SimpleNamespace(
        eh_conferencia=False,
        sessoes=[],
        nome_conferencia=None,
        dia_rotulo=None,
        dia=None,
    )
    analise_esperada = _criar_analise_mock("Análise Normal")
    analyzer.analisar.return_value = analise_esperada

    nota_criada = tmp_path / "Monologo Longo.md"
    writer = MagicMock()
    writer.salvar_video.return_value = nota_criada

    sucesso = main.processar_um_video(
        "https://www.youtube.com/watch?v=vid_longo_01",
        extrator=extrator,
        analyzer=analyzer,
        writer=writer,
        data_leitura="2026-11-23",
        vault_path=tmp_path,
    )

    assert sucesso is True
    analyzer.executar_scout.assert_called_once()
    analyzer.processar_conferencia_completa.assert_not_called()
    analyzer.analisar.assert_called_once()
    writer.salvar_video.assert_called_once_with(
        extrator.extrair_tudo.return_value,
        analise_esperada,
        "2026-11-23",
    )