from pathlib import Path

from analyzer import VideoAnalyzer
from models import AnaliseVideo


def test_analisar_video_longo_map_reduce_fluxo_feliz(tmp_path: Path, monkeypatch) -> None:
    analyzer = VideoAnalyzer(vault_path=tmp_path)

    dados_video = {
        "video_id": "longo123456",
        "titulo": "Arquitetura de Agentes em Escala",
        "canal": "Engenharia IA",
        "duracao_segundos": 5400,
        "transcricao_blocos": [
            {"start": 0.0, "duration": 600.0, "text": "Parte 1 sobre fundamentos."},
            {"start": 600.0, "duration": 600.0, "text": "Parte 2 sobre memória e ferramentas."},
        ],
        "capitulos_originais": [],
    }

    segmentos_fake = [
        {"ts_inicio": "[00:00:00]", "ts_fim": "[00:10:00]", "texto": "Parte 1 sobre fundamentos."},
        {"ts_inicio": "[00:10:00]", "ts_fim": "[00:20:00]", "texto": "Parte 2 sobre memória e ferramentas."},
    ]

    segmentos_vistos: list[tuple[int, int, str]] = []
    consolidacao_vista: dict = {}

    monkeypatch.setattr(analyzer, "_fatiar_transcricao", lambda _blocos, _caps: segmentos_fake)

    def fake_analisar_segmento(dados_arg: dict, seg_arg: dict, idx: int, total: int) -> dict:
        segmentos_vistos.append((idx, total, seg_arg["ts_inicio"]))
        return {
            "indice": idx,
            "ts_inicio": seg_arg["ts_inicio"],
            "ts_fim": seg_arg["ts_fim"],
            "resumo": f"Resumo do bloco {idx}",
        }

    def fake_consolidar_segmentos(dados_arg: dict, segs_analisados: list) -> AnaliseVideo:
            consolidacao_vista["titulo"] = dados_arg["titulo"]
            consolidacao_vista["qtd_segmentos"] = len(segs_analisados)
            return AnaliseVideo(
                titulo_sugerido="Arquitetura de Agentes em Escala",
                resumo_executivo="Síntese consolidada dos blocos analisados.",
                takeaways_principais=["Fundamentos sólidos", "Memória e ferramentas"],
                temas=["Agentes", "Arquitetura"],
            )

    monkeypatch.setattr(analyzer, "_analisar_segmento", fake_analisar_segmento)
    monkeypatch.setattr(analyzer, "_consolidar_segmentos", fake_consolidar_segmentos)

    resultado = analyzer.analisar_video_longo(dados_video)

    assert segmentos_vistos == [
        (1, 2, "[00:00:00]"),
        (2, 2, "[00:10:00]"),
    ]
    assert consolidacao_vista == {
        "titulo": "Arquitetura de Agentes em Escala",
        "qtd_segmentos": 2,
    }
    assert isinstance(resultado, AnaliseVideo)
    assert resultado.titulo_sugerido == "Arquitetura de Agentes em Escala"