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


def test_retoma_video_longo_por_bloco_e_respeito_forcar(
    cache_isolado: CacheLocalLLM, tmp_path, monkeypatch
):
    from models import AnaliseVideo

    chamadas_bloco = []
    deve_falhar_no_bloco_2 = True

    def fake_fatiar(_blocos, _caps):
        return [
            {"ts_inicio": "[00:00:00]", "ts_fim": "[00:10:00]", "texto": "Bloco 1 texto", "titulo_sugerido": None},
            {"ts_inicio": "[00:10:00]", "ts_fim": "[00:20:00]", "texto": "Bloco 2 texto", "titulo_sugerido": None},
        ]

    def fake_analisar_segmento(dados_arg, seg, idx, total, forcar=False):
        chamadas_bloco.append((idx, forcar))
        if idx == 2 and deve_falhar_no_bloco_2:
            raise RuntimeError("falha simulada no bloco 2")
        return _segmento_minimo(SegmentoAnalise)

    def fake_consolidar(dados_arg, segs_analisados, forcar=False):
        return AnaliseVideo(
            titulo_sugerido="Vídeo Longo Retomado",
            resumo_executivo="Síntese dos blocos.",
            takeaways_principais=["Takeaway"],
            temas=["IA"],
        )

    va = analyzer_mod.VideoAnalyzer(vault_path=tmp_path, cache=cache_isolado)
    monkeypatch.setattr(va, "_fatiar_transcricao", fake_fatiar)
    monkeypatch.setattr(va, "_analisar_segmento", fake_analisar_segmento)
    monkeypatch.setattr(va, "_consolidar_segmentos", fake_consolidar)
    monkeypatch.setattr(analyzer_mod, "_criar_canonicalizer", lambda _vp: _CanonFake())

    dados = {
        "id": "vid_retoma_1",
        "titulo": "Vídeo Longo com Retoma",
        "canal": "Canal Longo",
        "duracao_segundos": 4000,
        "transcricao_blocos": [{"start": 0, "text": "bloco"}],
    }

    # 1.ª Execução: Falha simulada no bloco 2
    with pytest.raises(RuntimeError, match="falha simulada no bloco 2"):
        va.analisar_video_longo(dados, forcar=False)

    assert chamadas_bloco == [(1, False), (2, False)]
    estado_erro = va.estado_pipeline.carregar(dados)
    assert "bloco_1_de_2" in estado_erro.passos_concluidos
    assert "Falha no bloco 2/2" in (estado_erro.erro_ultimo_passo or "")

    # 2.ª Execução: Retoma sem forçar (deve processar o bloco 2 com sucesso e concluir)
    deve_falhar_no_bloco_2 = False
    chamadas_bloco.clear()

    res = va.analisar_video_longo(dados, forcar=False)
    assert res.titulo_sugerido == "Vídeo Longo Retomado"
    # Chamou ambos passando forcar=False (o bloco 1 chamará fake_analisar_segmento com forcar=False)
    assert (2, False) in chamadas_bloco
    estado_final = va.estado_pipeline.carregar(dados)
    assert "bloco_1_de_2" in estado_final.passos_concluidos
    assert "bloco_2_de_2" in estado_final.passos_concluidos
    assert estado_final.passo_seguinte == "consolidar"

    # 3.ª Execução: com forcar=True, repassa forcar=True para os blocos
    chamadas_bloco.clear()
    va.analisar_video_longo(dados, forcar=True)
    assert chamadas_bloco == [(1, True), (2, True)]


def test_retoma_pipeline_real_apos_falha_na_consolidacao(
    cache_isolado: CacheLocalLLM, tmp_path, monkeypatch
):
    """
    Cenário real:
    1. Vídeo longo processa todos os blocos com sucesso.
    2. Durante a consolidação final (_consolidar_segmentos), ocorre uma falha/exceção.
    3. O main.py apanha a exceção e guarda o estado com o erro.
    4. Na 2.ª execução com forcar=False (retoma):
       - Os blocos já estão em cache (etapa='segmento').
       - A chamada a _analisar_segmento devolve cache hit sem custo de LLM.
       - A consolidação tem sucesso e o main.py conclui com sucesso marcando concluido=True.
    """
    import main as main_mod
    from models import AnaliseVideo

    # Configuração dos fakes
    deve_falhar_consolidacao = True
    chamadas_llm_segmento = []
    chamadas_consolidacao = []

    def fake_extrair_tudo(url):
        return {
            "id": "vid_real_retoma",
            "titulo": "Arquitetura Real de Agentes",
            "canal": "Engenharia IA",
            "data": "2026-11-27",
            "duracao_segundos": 3600,
            "transcricao": "Transcrição longa completa com muitas linhas\n" * 50,
            "transcricao_blocos": [{"start": float(i * 10), "duration": 10.0, "text": f"Bloco {i}"} for i in range(250)],
            "capitulos_originais": [],
        }

    def fake_fatiar(_blocos, _caps):
        return [
            {"ts_inicio": "[00:00:00]", "ts_fim": "[00:10:00]", "texto": "Bloco 1", "titulo_sugerido": None},
            {"ts_inicio": "[00:10:00]", "ts_fim": "[00:20:00]", "texto": "Bloco 2", "titulo_sugerido": None},
        ]

    va = analyzer_mod.VideoAnalyzer(vault_path=tmp_path, cache=cache_isolado)

    # Monkeypatch do extrator e fatiamento
    fake_extrator = SimpleNamespace(extrair_tudo=fake_extrair_tudo)
    monkeypatch.setattr(va, "_fatiar_transcricao", fake_fatiar)
    monkeypatch.setattr(analyzer_mod, "_criar_canonicalizer", lambda _vp: _CanonFake())

    # Mock do executar_scout para devolver não-conferência imediatamente sem gastar LLM
    from models import AgendaScout
    monkeypatch.setattr(
        va,
        "executar_scout",
        lambda _d, forcar=False: AgendaScout(
            nome_conferencia="Canal Teste",
            eh_conferencia=False,
            sessoes=[],
        ),
    )

    # Mock do _chamar_com_fallback no analyzer para registrar chamadas reais de LLM dos blocos
    def fake_chamar(modelo, conteudos, cfg):
        chamadas_llm_segmento.append(modelo)
        return SimpleNamespace(parsed=_segmento_minimo(SegmentoAnalise))

    monkeypatch.setattr(va, "_chamar_com_fallback", fake_chamar)

    orig_consolidar = va._consolidar_segmentos
    def interceptar_consolidar(dados_arg, segs_analisados, forcar=False):
        chamadas_consolidacao.append(len(segs_analisados))
        if deve_falhar_consolidacao:
            raise RuntimeError("Erro transitório ou crash durante consolidação global")
        return AnaliseVideo(
            titulo_sugerido="Arquitetura Real de Agentes",
            resumo_executivo="Resumo executivo consolidado com sucesso.",
            takeaways_principais=["Takeaway principal"],
            temas=["IA"],
        )

    monkeypatch.setattr(va, "_consolidar_segmentos", interceptar_consolidar)

    class FakeWriter:
        def salvar_video(self, dados, analise, data_leitura):
            return tmp_path / "nota_criada.md"

    fake_writer = FakeWriter()

    # -------------------------------------------------------------
    # 1.ª Tentativa: os blocos 1 e 2 passam (gravando em cache),
    # mas a consolidação falha
    # -------------------------------------------------------------
    sucesso_1 = main_mod.processar_um_video(
        url="https://www.youtube.com/watch?v=vid_real_retoma",
        extrator=fake_extrator,
        analyzer=va,
        writer=fake_writer,
        forcar=False,
        vault_path=tmp_path,
    )
    assert sucesso_1 is False
    assert len(chamadas_llm_segmento) == 2  # Ambos os blocos chamaram LLM e foram guardados em cache
    assert len(chamadas_consolidacao) == 1

    # Verifica o estado persistido após a falha
    estado_intermedio = va.estado_pipeline.carregar({"id": "vid_real_retoma"})
    assert estado_intermedio.concluido is False
    assert "bloco_1_de_2" in estado_intermedio.passos_concluidos
    assert "bloco_2_de_2" in estado_intermedio.passos_concluidos
    assert estado_intermedio.passo_seguinte == "consolidar"
    assert "Erro transitório ou crash durante consolidação" in (estado_intermedio.erro_ultimo_passo or "")

    # -------------------------------------------------------------
    # 2.ª Tentativa: Retoma no main.py com forcar=False
    # Não deve haver novas chamadas ao LLM para os blocos!
    # -------------------------------------------------------------
    deve_falhar_consolidacao = False
    chamadas_llm_segmento.clear()

    sucesso_2 = main_mod.processar_um_video(
        url="https://www.youtube.com/watch?v=vid_real_retoma",
        extrator=fake_extrator,
        analyzer=va,
        writer=fake_writer,
        forcar=False,
        vault_path=tmp_path,
    )
    assert sucesso_2 is True
    # Crucial: NENHUMA nova chamada LLM foi necessária para os blocos (cache hit em ambos!)
    assert len(chamadas_llm_segmento) == 0
    assert len(chamadas_consolidacao) == 2

    # Verifica o estado final concluído com sucesso
    estado_final = va.estado_pipeline.carregar({"id": "vid_real_retoma"})
    assert estado_final.concluido is True
    assert estado_final.passo_seguinte is None
    assert "analisar" in estado_final.passos_concluidos
    assert "escrever_nota" in estado_final.passos_concluidos
    assert estado_final.erro_ultimo_passo is None


