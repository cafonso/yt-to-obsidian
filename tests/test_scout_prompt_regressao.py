from pathlib import Path
from types import SimpleNamespace

import config
from analyzer import VideoAnalyzer
from models import AgendaScout


def test_executar_scout_inclui_contexto_e_regras_no_prompt(tmp_path: Path, monkeypatch) -> None:
    analyzer = VideoAnalyzer(vault_path=tmp_path)
    capturado: dict = {}

    dados_video = {
        "video_id": "conf1234567",
        "titulo": "AI Engineer Summit 2026 - Dia 2",
        "canal": "AI Engineer",
        "duracao_segundos": 7200,
        "descricao": "Sessões técnicas sobre agentes e avaliação em produção.",
    }

    monkeypatch.setattr(analyzer, "_preparar_contexto_scout", lambda _dados: "CAPÍTULOS: [00:00] Abertura")

    def fake_chamar_com_fallback(modelo: str, conteudos: list, config_obj):
        capturado["modelo"] = modelo
        capturado["prompt"] = conteudos[0]
        capturado["config"] = config_obj
        agenda_fake = AgendaScout(
            nome_conferencia="AI Engineer Summit 2026",
            dia=2,
            dia_rotulo="Dia 2",
            data_sessao="2026-11-12",
            eh_conferencia=True,
            sessoes=[],
        )
        return SimpleNamespace(parsed=agenda_fake)

    monkeypatch.setattr(analyzer, "_chamar_com_fallback", fake_chamar_com_fallback)

    resultado = analyzer.executar_scout(dados_video)
    prompt = capturado["prompt"]

    assert resultado.eh_conferencia is True
    assert capturado["modelo"] == config.MODELO_SCOUT
    assert capturado["config"].response_schema is AgendaScout
    assert "AI Engineer Summit 2026 - Dia 2" in prompt
    assert "7200 segundos" in prompt
    assert "CAPÍTULOS: [00:00] Abertura" in prompt
    assert "eh_conferencia=True" in prompt
    assert "eh_conferencia=False" in prompt
    assert "Ignora intervalos vazios ou pausas de almoço" in prompt