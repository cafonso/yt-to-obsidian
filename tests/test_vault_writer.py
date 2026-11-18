import pytest
from pathlib import Path
from vault_writer import ObsidianVaultWriter
from models import AnaliseVideo, PessoaMencionada, ArtefactoIA, ObraCitada


@pytest.fixture
def temp_vault(tmp_path: Path) -> Path:
    """Fixture que cria uma estrutura temporária de cofre do Obsidian."""
    return tmp_path


def test_vault_writer_criacao_pastas(temp_vault: Path):
    writer = ObsidianVaultWriter(str(temp_vault))
    
    # Verifica se as subpastas essenciais foram criadas automaticamente
    assert (temp_vault / "Videos").exists()
    assert (temp_vault / "Pessoas").exists()
    assert (temp_vault / "Livros").exists()
    assert (temp_vault / "Temas").exists()
    assert (temp_vault / "Artefactos").exists()
    assert (temp_vault / "Organizações").exists()


def test_salvar_video_e_diario(temp_vault: Path):
    writer = ObsidianVaultWriter(str(temp_vault))
    
    dados_video = {
        "titulo": "Introdução à Inteligência Artificial Avançada",
        "canal": "Tech Talks PT",
        "canal_id": "UC123456",
        "data": "2026-11-01",
        "duracao_segundos": 1800,
        "url": "https://www.youtube.com/watch?v=exemplo123",
        "descricao": "Uma palestra sobre modelos de linguagem e agentes."
    }
    
    analise = AnaliseVideo(
        titulo_sugerido="Introdução à Inteligência Artificial Avançada",
        resumo_executivo="Neste vídeo exploramos o estado da arte dos modelos generativos e a sua aplicação prática na engenharia de software.",
        takeaways_principais=[
            "Os agentes de IA mudam o paradigma de interação.",
            "A canonicalização de dados evita duplicações no cofre."
        ],
        temas=["Inteligência Artificial", "Engenharia de Software"],
        pessoas=[
            PessoaMencionada(nome="João Silva", papel_ou_bio="Investigador principal na área de IA.")
        ],
        artefactos=[
            ArtefactoIA(nome="GPT-4o", subtipo="modelo", fabricante_ou_autor="OpenAI", descricao="Modelo multimodal avançado.")
        ]
    )
    
    data_leitura = "2026-11-18"
    caminho_video = writer.salvar_video(dados_video, analise, data_leitura=data_leitura)
    
    # 1. Verifica se a nota do vídeo foi criada corretamente
    assert caminho_video.exists()
    conteudo_video = caminho_video.read_text(encoding="utf-8")
    assert "Introdução à Inteligência Artificial Avançada" in conteudo_video
    assert "[[João Silva]]" in conteudo_video
    assert "[[GPT-4o]]" in conteudo_video
    
    # 2. Verifica se a nota diária (YYYY-MM-DD.md) foi criada/atualizada com o bloco correto
    caminho_diario = temp_vault / f"{data_leitura}.md"
    assert caminho_diario.exists()
    conteudo_diario = caminho_diario.read_text(encoding="utf-8")
    assert "Introdução à Inteligência Artificial Avançada" in conteudo_diario
    assert "Tech Talks PT" in conteudo_diario
    
    # 3. Verifica se a nota atómica da pessoa foi criada na pasta Pessoas/
    caminho_pessoa = temp_vault / "Pessoas" / "João Silva.md"
    assert caminho_pessoa.exists()
    assert "Investigador principal" in caminho_pessoa.read_text(encoding="utf-8")