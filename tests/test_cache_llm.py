from types import SimpleNamespace
from pydantic import BaseModel
import pytest

import analyzer as analyzer_mod
from cache_local import CacheLocalLLM
from models import SinteseGlobal, SegmentoAnalise


@pytest.fixture
def cache_isolado(tmp_path):
    """Cria uma instância de CacheLocalLLM apontada para um diretório temporário isolado."""
    return CacheLocalLLM(vault_path=tmp_path, ativo=True)


class _CanonFake:
    def canonicalizar_pessoas(self, x):
        return x

    def canonicalizar_artefactos(self, x):
        return x

    def canonicalizar_obras(self, x):
        return x

    def canonicalizar_strings(self, _tipo, x):
        return x

    def gravar(self):
        pass


def _segmento_minimo(modelo_seg):
    return modelo_seg(
        timestamp_inicio="00:00",
        timestamp_fim="10:00",
        titulo_segmento="Bloco 1",
        resumo_bloco="Resumo do bloco 1.",
        takeaways_bloco=["Takeaway A", "Takeaway B"],
        oradores_ou_apresentadores=[],
        pessoas=[],
        obras=[],
        organizacoes=[],
        artefactos=[],
        temas=[],
        metricas_e_numeros=[],
        tensoes_e_riscos=[],
        agenda_e_previsoes=[],
        recursos_e_links=[],
        videos_citados=[],
    )


def _dados_video_minimos():
    return {
        "id": "vid_longo_1",
        "titulo": "Palestra Longa",
        "canal": "Canal Teste",
        "duracao_segundos": 3600,
    }


def test_consolidar_segmentos_usa_cache_e_respeita_forcar(
    cache_isolado: CacheLocalLLM, tmp_path, monkeypatch
):
    chamadas = {"llm": 0}

    def fake_chamar(modelo, conteudos, cfg):
        chamadas["llm"] += 1
        return SimpleNamespace(
            parsed=SinteseGlobal(
                titulo_sugerido="Palestra Longa",
                resumo_executivo=f"Resumo chamada {chamadas['llm']}",
                takeaways_principais=["Takeaway 1"],
            )
        )

    va = analyzer_mod.VideoAnalyzer(vault_path=tmp_path, cache=cache_isolado)
    monkeypatch.setattr(va, "_chamar_com_fallback", fake_chamar)
    monkeypatch.setattr(analyzer_mod, "_criar_canonicalizer", lambda _vp: _CanonFake())

    # Utiliza diretamente o modelo SegmentoAnalise
    segmentos = [_segmento_minimo(SegmentoAnalise)]
    dados = _dados_video_minimos()

    # 1.ª chamada: preenche cache
    res1 = va._consolidar_segmentos(dados, segmentos, forcar=False)
    assert chamadas["llm"] == 1
    assert res1.resumo_executivo == "Resumo chamada 1"

    # 2.ª chamada (forcar=False): deve reutilizar cache sem chamar LLM
    res2 = va._consolidar_segmentos(dados, segmentos, forcar=False)
    assert chamadas["llm"] == 1
    assert res2.resumo_executivo == "Resumo chamada 1"

    # 3.ª chamada (forcar=True): ignora leitura em cache e volta a chamar LLM
    res3 = va._consolidar_segmentos(dados, segmentos, forcar=True)
    assert chamadas["llm"] == 2
    assert res3.resumo_executivo == "Resumo chamada 2"


def test_consolidar_segmentos_fallback_marca_degradado(
    cache_isolado: CacheLocalLLM, tmp_path, monkeypatch
):
    def fake_chamar_falha(*_args, **_kwargs):
        raise RuntimeError("timeout simulado no Gemini")

    va = analyzer_mod.VideoAnalyzer(vault_path=tmp_path, cache=cache_isolado)
    monkeypatch.setattr(va, "_chamar_com_fallback", fake_chamar_falha)
    monkeypatch.setattr(analyzer_mod, "_criar_canonicalizer", lambda _vp: _CanonFake())

    segmentos = [_segmento_minimo(SegmentoAnalise)]
    dados = _dados_video_minimos()

    # Inicializa o estado para verificar que degradado=True fica persistido
    estado_inicial = va.estado_pipeline.carregar(dados, forcar=True)
    va.estado_pipeline.guardar(dados, estado_inicial, passo_concluido="metadados")

    res = va._consolidar_segmentos(dados, segmentos, forcar=False)
    assert res.resumo_executivo == "Resumo do bloco 1."
    assert "Takeaway A" in res.takeaways_principais

    estado_pos = va.estado_pipeline.carregar(dados, forcar=False)
    assert estado_pos.degradado is True
    assert "metadados" in estado_pos.passos_concluidos


def test_analisar_passo_unico_usa_cache_e_respeita_forcar(
    cache_isolado: CacheLocalLLM, tmp_path, monkeypatch
):
    from models import AnaliseVideo

    chamadas = {"llm": 0, "upload": 0}

    def fake_chamar(modelo, conteudos, cfg):
        chamadas["llm"] += 1
        return SimpleNamespace(
            parsed=AnaliseVideo(
                titulo_sugerido="Vídeo Passo Único",
                resumo_executivo=f"Resumo executivo chamada {chamadas['llm']}",
                takeaways_principais=["Ponto 1", "Ponto 2"],
                temas=["IA", "Cache"],
            )
        )

    class FakeFiles:
        def upload(self, file):
            chamadas["upload"] += 1
            return SimpleNamespace(name="fake_uploaded_file")

        def delete(self, name):
            pass

    va = analyzer_mod.VideoAnalyzer(vault_path=tmp_path, cache=cache_isolado)
    va.client = SimpleNamespace(files=FakeFiles())
    monkeypatch.setattr(va, "_chamar_com_fallback", fake_chamar)
    monkeypatch.setattr(analyzer_mod, "_criar_canonicalizer", lambda _vp: _CanonFake())

    dados = {
        "id": "vid_passo_unico_1",
        "titulo": "Vídeo Passo Único",
        "canal": "Canal Criador",
        "data": "2026-11-27",
        "descricao": "Descrição teste com links",
        "transcricao": "Transcrição do vídeo passo único.",
    }

    # 1.ª chamada: sem cache, deve chamar LLM
    res1 = va.analisar_passo_unico(dados, forcar=False)
    assert chamadas["llm"] == 1
    assert res1.resumo_executivo == "Resumo executivo chamada 1"

    # 2.ª chamada (forcar=False): deve dar cache hit e NÃO chamar LLM
    res2 = va.analisar_passo_unico(dados, forcar=False)
    assert chamadas["llm"] == 1
    assert res2.resumo_executivo == "Resumo executivo chamada 1"

    # 3.ª chamada (forcar=True): ignora cache e volta a chamar LLM
    res3 = va.analisar_passo_unico(dados, forcar=True)
    assert chamadas["llm"] == 2
    assert res3.resumo_executivo == "Resumo executivo chamada 2"
