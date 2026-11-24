from pathlib import Path
import pytest

from analyzer import _desduplicar_videos_citados
from main import _resolver_caminho_historico, gravar_historico
from models import AnaliseVideo, VideoCitado
from vault_writer import ObsidianVaultWriter


from types import SimpleNamespace

from models import PalestraAnalise, VideoCitado


@pytest.fixture
def temp_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "VaultTeste"
    vault.mkdir(parents=True, exist_ok=True)
    return vault


def test_desduplicar_videos_citados_por_url_e_titulo():
    v1 = VideoCitado(
        titulo_ou_assunto="Deep Dive into Agents",
        canal_ou_orador="AI Explained",
        url_ou_id="https://www.youtube.com/watch?v=abc123XYZ01",
        contexto="Referência inicial",
    )
    v1_duplicado_url = VideoCitado(
        titulo_ou_assunto="Deep Dive into Agents (repetido)",
        canal_ou_orador="AI Explained",
        url_ou_id="https://www.youtube.com/watch?v=abc123XYZ01",
        contexto="Repetido pelo mesmo URL",
    )
    v2 = VideoCitado(
        titulo_ou_assunto="Outro Vídeo Sem Link",
        canal_ou_orador="Canal X",
        url_ou_id=None,
        contexto="Menção oral",
    )
    v2_duplicado_titulo = VideoCitado(
        titulo_ou_assunto="outro vídeo sem link.",
        canal_ou_orador="canal x",
        url_ou_id=None,
        contexto="Segunda menção",
    )
    v_vazio = VideoCitado(
        titulo_ou_assunto="   ",
        canal_ou_orador=None,
        url_ou_id=None,
        contexto=None,
    )

    resultado = _desduplicar_videos_citados([v1, v1_duplicado_url, v2, v2_duplicado_titulo, v_vazio])
    assert len(resultado) == 2
    assert resultado[0].titulo_ou_assunto == "Deep Dive into Agents"
    assert resultado[1].titulo_ou_assunto == "Outro Vídeo Sem Link"


def test_salvar_video_cruza_videos_citados_com_historico(temp_vault: Path):


    writer = ObsidianVaultWriter(str(temp_vault), validar_links=False)
    dados_video = {
        "titulo": "Vídeo Principal",
        "canal": "Canal Principal",
        "canal_url": "https://www.youtube.com/@principal",
        "data": "2026-11-23",
        "url": "https://www.youtube.com/watch?v=principal01",
        "descricao": "Descrição de teste.",
    }
    
    
    nota_existente = writer.vault_path / "Videos" / "Nota Vídeo Citado Existente.md"
    nota_existente.parent.mkdir(parents=True, exist_ok=True)
    nota_existente.write_text("# Nota Vídeo Citado Existente\n", encoding="utf-8")

    caminho_hist = _resolver_caminho_historico(writer.vault_path)
    
    gravar_historico(
        {
            "vidJaGrav01": {
                "titulo": "Vídeo Já Processado",
                "canal": "Canal Antigo",
                "url": "https://www.youtube.com/watch?v=vidJaGrav01",
                "data_leitura": "2026-11-10",
                "nota": str(nota_existente),
            }
        },
        caminho_hist,
    )


    analise = AnaliseVideo(
        titulo_sugerido="Vídeo Principal",
        resumo_executivo="Resumo de teste.",
        takeaways_principais=["Takeaway 1"],
        temas=["PKM"],
        videos_citados=[
            VideoCitado(
                titulo_ou_assunto="Vídeo Já Processado",
                canal_ou_orador="Canal Antigo",
                url_ou_id="https://youtu.be/vidJaGrav01",
                contexto="Continuação direta",
            ),
            VideoCitado(
                titulo_ou_assunto="Vídeo Ainda Não Visto",
                canal_ou_orador="Joana Martins",
                url_ou_id=None,
                contexto="Recomendação",
            ),
        ],
    )

    caminho_nota = writer.salvar_video(dados_video, analise, data_leitura="2026-11-23")
    conteudo = caminho_nota.read_text(encoding="utf-8")

    assert "## 🎬 Vídeos Citados / Referenciados" in conteudo
    assert writer._carregar_historico_vault().get("vidJaGrav01") is not None 
    assert (writer.pasta_pessoas / "Joana Martins.md").exists()
    assert "**[[Nota Vídeo Citado Existente]]**" in conteudo
    assert 'videos_citados:\n  - "[[Nota Vídeo Citado Existente]]"' in conteudo
    assert "**Vídeo Ainda Não Visto** por [[Joana Martins]] — _Recomendação_" in conteudo
    assert caminho_hist.exists()



def test_salvar_video_citado_com_url_externo_fora_do_historico(temp_vault: Path):
    writer = ObsidianVaultWriter(str(temp_vault), validar_links=False)
    dados_video = {
        "titulo": "Vídeo Externo",
        "canal": "Canal Teste",
        "canal_url": "https://www.youtube.com/@teste",
        "data": "2026-11-23",
        "url": "https://www.youtube.com/watch?v=principal02",
        "descricao": "Descrição.",
    }
    analise = AnaliseVideo(
        titulo_sugerido="Vídeo Externo",
        resumo_executivo="Resumo.",
        takeaways_principais=["Ponto 1"],
        temas=["IA"],
        videos_citados=[
            VideoCitado(
                titulo_ou_assunto="Talk Externa",
                canal_ou_orador="OpenAI",
                url_ou_id="https://www.youtube.com/watch?v=naoEstaNoHist",
                contexto="Demo oficial",
            )
        ],
    )

    caminho_nota = writer.salvar_video(dados_video, analise, data_leitura="2026-11-23")
    conteudo = caminho_nota.read_text(encoding="utf-8")

    assert "videos_citados: []" in conteudo
    assert "**[Talk Externa](https://www.youtube.com/watch?v=naoEstaNoHist)** por [[OpenAI]] — _Demo oficial_" in conteudo


def test_salvar_video_sem_videos_citados_nao_cria_seccao(temp_vault: Path):
    writer = ObsidianVaultWriter(str(temp_vault), validar_links=False)
    dados_video = {
        "titulo": "Vídeo Sem Citações",
        "canal": "Canal Teste",
        "canal_url": "https://www.youtube.com/@teste",
        "data": "2026-11-23",
        "url": "https://www.youtube.com/watch?v=principal03",
        "descricao": "Descrição.",
    }
    analise = AnaliseVideo(
        titulo_sugerido="Vídeo Sem Citações",
        resumo_executivo="Resumo.",
        takeaways_principais=["Ponto 1"],
        temas=["IA"],
        videos_citados=[],
    )

    caminho_nota = writer.salvar_video(dados_video, analise, data_leitura="2026-11-23")
    conteudo = caminho_nota.read_text(encoding="utf-8")

    assert "videos_citados: []" in conteudo
    assert "## 🎬 Vídeos Citados / Referenciados" not in conteudo
    


@pytest.fixture
def vault_writer(tmp_path: Path) -> ObsidianVaultWriter:
    destino_vault = tmp_path / "obsidian_vault"
    destino_vault.mkdir(parents=True, exist_ok=True)
    return ObsidianVaultWriter(destino_vault)


def _payload_video() -> dict:
    return {
        "id": "confSession99",
        "url": "https://youtu.be/confSession99",
        "titulo": "Dia 2 - Sessões Técnicas",
        "data": "2026-11-21",
        "canal": "Tech Summit PT",
        "canal_url": "https://youtube.com/@techsummitpt",
    }


def _dados_agenda() -> SimpleNamespace:
    return SimpleNamespace(
        nome_conferencia="Summit Engenharia",
        dia=2,
        dia_rotulo="Dia 2",
        data_sessao="2026-11-21",
    )


def _dados_sessao() -> SimpleNamespace:
    return SimpleNamespace(
        ordem=3,
        titulo_palestra="Observabilidade em Produção",
        orador_principal="Diogo Martins",
        organizacao="ObservaLab",
        timestamp_inicio="01:05:00",
        timestamp_fim="01:40:00",
        segundos_inicio=3900,
    )


def test_desduplica_e_separa_links_resolvidos_de_nao_resolvidos(vault_writer: ObsidianVaultWriter, monkeypatch):
    def _resolver_simulado(video: VideoCitado, _hist):
        if video.url_ou_id == "vidMatch01":
            return ("Palestra Anterior sobre Traces", "2026-09-15 - Palestra Anterior sobre Traces")
        return (video.titulo_ou_assunto, None)

    monkeypatch.setattr(vault_writer, "_resolver_video_citado", _resolver_simulado)

    analise = PalestraAnalise(
        titulo_palestra="Observabilidade em Produção",
        resumo_executivo="Análise prática de métricas, logs e traces distribuídos.",
        takeaways_principais=["Correlacionar traces com latência p99"],
        videos_citados=[
            VideoCitado(
                titulo_ou_assunto="Palestra Anterior sobre Traces",
                url_ou_id="vidMatch01",
                canal_ou_orador="Canal Base",
                contexto="baseline de referência",
            ),
            VideoCitado(
                titulo_ou_assunto="Título Alternativo Mesmo Vídeo",
                url_ou_id="vidMatch01",
                canal_ou_orador="Canal Base",
                contexto="duplicado pelo mesmo ID",
            ),
            VideoCitado(
                titulo_ou_assunto="Demo Ainda Não Arquivada",
                url_ou_id="vidNovo999",
                canal_ou_orador="DemoLab",
                contexto="exemplo complementar",
            ),
        ],
    )

    nota_path = vault_writer.salvar_palestra_conferencia(
        _payload_video(),
        _dados_agenda(),
        _dados_sessao(),
        analise,
        data_leitura="2026-11-24",
        historico={"vidMatch01": {"stem": "2026-09-15 - Palestra Anterior sobre Traces"}},
    )

    texto = nota_path.read_text(encoding="utf-8")
    assert texto.count("**Demo Ainda Não Arquivada**") == 1
    assert texto.count("**Palestra Anterior sobre Traces**") == 1
    assert '"[[2026-09-15 - Palestra Anterior sobre Traces]]"' in texto
    assert "vidNovo999" not in texto


def test_carrega_historico_automaticamente_quando_omitido(vault_writer: ObsidianVaultWriter, monkeypatch):
    chamadas = {"carregou": 0, "resolveu": 0}

    def _carregar_mock():
        chamadas["carregou"] += 1
        return {"vidHistorico77": {"stem": "2026-08-10 - Nota do Histórico"}}

    def _resolver_mock(_video: VideoCitado, hist):
        chamadas["resolveu"] += 1
        assert "vidHistorico77" in hist
        return ("Nota do Histórico", "2026-08-10 - Nota do Histórico")

    monkeypatch.setattr(vault_writer, "_carregar_historico_vault", _carregar_mock)
    monkeypatch.setattr(vault_writer, "_resolver_video_citado", _resolver_mock)

    analise = PalestraAnalise(
        titulo_palestra="Observabilidade em Produção",
        resumo_executivo="Resumo curto.",
        takeaways_principais=["Ponto único"],
        videos_citados=[
            VideoCitado(
                titulo_ou_assunto="Nota do Histórico",
                url_ou_id="vidHistorico77",
                canal_ou_orador="",
                contexto="",
            )
        ],
    )

    nota_path = vault_writer.salvar_palestra_conferencia(
        _payload_video(),
        _dados_agenda(),
        _dados_sessao(),
        analise,
        data_leitura="2026-11-24",
    )

    assert nota_path.exists()
    assert chamadas["carregou"] == 1
    assert chamadas["resolveu"] == 1
