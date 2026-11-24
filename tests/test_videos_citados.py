from pathlib import Path
import pytest

from analyzer import _desduplicar_videos_citados
from main import _resolver_caminho_historico, gravar_historico
from models import AnaliseVideo, VideoCitado
from vault_writer import ObsidianVaultWriter


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