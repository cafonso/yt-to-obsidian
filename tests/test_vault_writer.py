import asyncio
from pathlib import Path

import pytest
import yaml

import vault_writer as vw
from models import (
    AgendaScout,
    AnaliseVideo,
    ArtefactoIA,
    ObraCitada,
    PessoaMencionada,
    SessaoScout,
)
from vault_writer import ObsidianVaultWriter


@pytest.fixture
def temp_vault(tmp_path: Path) -> Path:
    """Cria um diretório temporário isolado que simula o Vault do Obsidian."""
    return tmp_path


def _extrair_frontmatter(texto_md: str) -> dict:
    """Extrai e valida o bloco YAML inicial de uma nota Markdown."""
    assert texto_md.startswith("---\n"), "Nota não começa com frontmatter YAML"
    partes = texto_md.split("---\n", 2)
    assert len(partes) == 3, "Frontmatter YAML mal fechado"
    return yaml.safe_load(partes[1])


# ---------------------------------------------------------------------------
# Testes existentes
# ---------------------------------------------------------------------------


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
        "canal_url": "https://www.youtube.com/@techtalkspt",
        "data": "2026-11-18",
        "url": "https://www.youtube.com/watch?v=exemplo123",
        "descricao": "Uma palestra sobre modelos de linguagem e agentes.",
    }

    analise = AnaliseVideo(
        titulo_sugerido="Introdução à Inteligência Artificial Avançada",
        resumo_executivo="Neste vídeo exploramos o estado da arte dos modelos generativos e a sua aplicação prática na engenharia de software.",
        takeaways_principais=[
            "Os agentes autónomos requerem validação rigorosa.",
            "O contexto longo muda a arquitetura de RAG.",
        ],
        temas=["Inteligência Artificial", "Engenharia de Software"],
        pessoas=[
            PessoaMencionada(
                nome="João Silva",
                papel_ou_bio="Investigador principal de IA.",
            )
        ],
        obras=[
            ObraCitada(
                titulo="Attention Is All You Need",
                tipo="paper",
                autores=["Ashish Vaswani"],
                contexto="Base dos Transformers.",
            )
        ],
        artefactos=[
            ArtefactoIA(
                nome="GPT-4o",
                subtipo="modelo",
                fabricante_ou_autor="OpenAI",
                descricao="Modelo multimodal avançado.",
            )
        ],
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


# ---------------------------------------------------------------------------
# Novos testes — Fixes 1–6 e regressões em vault_writer.py
# ---------------------------------------------------------------------------


def test_limpar_nome_ficheiro_pontos_finais_e_reservados_windows():
    assert (
        vw.limpar_nome_ficheiro("Anthropic Ran 1,000 AI Agents. Yours Needs The Same Thing Again.")
        == "Anthropic Ran 1,000 AI Agents. Yours Needs The Same Thing Again"
    )
    assert vw.limpar_nome_ficheiro('A:B/C\\D*E?F"G<H>I|J') == "ABCDEFGHIJ"
    assert vw.limpar_nome_ficheiro("CON") == "_CON"
    assert vw.limpar_nome_ficheiro("com1.") == "_com1"
    assert vw.limpar_nome_ficheiro("NUL ") == "_NUL"

    titulo_longo = "A" * 119 + ". B"
    limpo = vw.limpar_nome_ficheiro(titulo_longo)
    assert len(limpo) <= 120
    assert not limpo.endswith(".")


def test_yaml_listas_e_sanitizacao_sem_listas_aninhadas(temp_vault: Path):
    writer = ObsidianVaultWriter(str(temp_vault), validar_links=False)

    dados_video = {
        "titulo": 'Vídeo "Com Aspas": Teste Final.',
        "canal": "Canal Teste",
        "canal_url": "https://youtube.com/@teste",
        "data": "2026-11-22",
        "url": "https://youtu.be/teste001",
        "descricao": "Descrição de teste.",
    }
    analise = AnaliseVideo(
        titulo_sugerido="Vídeo Teste Final.",
        resumo_executivo="Resumo curto.",
        takeaways_principais=["Ponto 1"],
        temas=["Agentes IA", "Segurança"],
        pessoas=[PessoaMencionada(nome="Ana Costa", papel_ou_bio="Linha 1\n> Linha 2")],
        obras=[ObraCitada(titulo="Paper Base", tipo="paper", autores=["Ana Costa"], contexto="Contexto")],
        organizacoes=["Anthropic"],
        artefactos=[
            ArtefactoIA(nome="Modelo Local", subtipo="modelo", fabricante_ou_autor=None, descricao="Sem fabricante"),
        ],
    )

    caminho_video = writer.salvar_video(dados_video, analise, data_leitura="2026-11-22")
    assert caminho_video.name == "Vídeo Teste Final.md"

    fm_video = _extrair_frontmatter(caminho_video.read_text(encoding="utf-8"))
    assert fm_video["titulo"] == 'Vídeo "Com Aspas": Teste Final.'
    assert fm_video["temas"] == ["[[Agentes IA]]", "[[Segurança]]"]
    assert fm_video["pessoas"] == ["[[Ana Costa]]"]
    assert fm_video["obras"] == ["[[Paper Base]]"]

    fm_obra = _extrair_frontmatter((temp_vault / "Livros" / "Paper Base.md").read_text(encoding="utf-8"))
    assert fm_obra["autores"] == ["[[Ana Costa]]"]

    fm_art = _extrair_frontmatter((temp_vault / "Artefactos" / "Modelo Local.md").read_text(encoding="utf-8"))
    assert fm_art["fabricante"] is None

    nota_pessoa = (temp_vault / "Pessoas" / "Ana Costa.md").read_text(encoding="utf-8")
    assert "> Linha 1\n> Linha 2" in nota_pessoa


def test_validar_recursos_externos_com_loop_ativo_e_multiplos_urls(monkeypatch):
    monkeypatch.setattr(vw, "verificar_link_ativo", lambda url, timeout=3.5: "inativo" not in url)

    recursos = [
        "- Ver https://exemplo.com/ok e https://exemplo.com/inativo.",
        "- Apenas válido: https://exemplo.com/ok",
    ]

    async def executar_com_loop():
        return vw.validar_recursos_externos(recursos, ativar=True)

    resultado = asyncio.run(executar_com_loop())
    assert "⚠️" in resultado[0]
    assert "https://exemplo.com/inativo" in resultado[0]
    assert resultado[1] == "- Apenas válido: https://exemplo.com/ok"


def test_diario_preserva_separador_antes_de_resenha_e_escapa_regex(temp_vault: Path):
    writer = ObsidianVaultWriter(str(temp_vault), validar_links=False)
    diario = temp_vault / "2026-11-22.md"
    diario.write_text("Manhã livre.\n\n---\n\n# Resenha do dia\nTexto existente.\n", encoding="utf-8")

    dados = {
        "titulo": "Vídeo \\2 [Especial]",
        "canal": "Canal",
        "data": "2026-11-22",
        "url": "https://youtu.be/abc",
        "descricao": "Desc",
    }
    analise = AnaliseVideo(
        titulo_sugerido="Vídeo \\2 [Especial]",
        resumo_executivo="Resumo",
        takeaways_principais=["T1"],
        temas=["Tema"],
    )
    writer.atualizar_nota_diaria(dados, "[[Vídeo \\2 [Especial]]]", analise, data_leitura="2026-11-22")

    texto_diario = diario.read_text(encoding="utf-8")
    assert "---" in texto_diario
    assert "# [[Vídeo \\2 [Especial]]]" in texto_diario
    assert texto_diario.index("---") < texto_diario.index("# [[Vídeo \\2 [Especial]]]")
    assert texto_diario.index("# [[Vídeo \\2 [Especial]]]") < texto_diario.index("# Resenha do dia")

    writer.salvar_ou_atualizar_tema("Tema", "[[Vídeo Inicial]]")
    nota_tema = (temp_vault / "Temas" / "Tema.md").read_text(encoding="utf-8")
    atualizada = writer._adicionar_link_se_nao_existir(
        nota_tema, "### 📹 Vídeos sobre este tema:", "[[Vídeo \\2 [Especial]]]"
    )
    assert "- [[Vídeo \\2 [Especial]]]" in atualizada


def test_conferencia_moc_sem_duracao_e_sem_quadruplos_colchetes(temp_vault: Path):
    writer = ObsidianVaultWriter(str(temp_vault), validar_links=False)
    dados = {
        "id": "vid42",
        "titulo": "Conferência Dia 1",
        "canal": "Organização Conf",
        "data": "2026-11-22",
        "url": "https://youtube.com/watch?v=vid42",
        "duracao_segundos": None,
        "descricao": "Descrição da conferência.",
    }
    sessao = SessaoScout(
        ordem=1,
        titulo_palestra="Sessão 1",
        orador_principal="Grace Hopper",
        organizacao="Marinha",
        timestamp_inicio="00:00:00",
        timestamp_fim="00:20:00",
        segundos_inicio=0,
        segundos_fim=1200,
    )
    agenda = AgendaScout(
        eh_conferencia=True,
        nome_conferencia="Conferência Dia 1",
        sessoes=[sessao],
    )

    palestras = [
        {
            "sessao": sessao,
            "caminho": temp_vault / "Sessão 1.md",
        }
    ]
    moc_path = writer.salvar_ou_atualizar_moc_conferencia(
        dados,
        agenda,
        palestras,
    )

    conteudo = Path(moc_path).read_text(encoding="utf-8")

    # Estrutura base antes da tabela de palestras
    assert "# 🏛️ Conferência Dia 1" in conteudo
    assert "## 📅 Dia 1 (2026-11-22)" in conteudo
    assert "Duração Total" in conteudo
    assert "| # | Início | Orador | Empresa | Palestra |" in conteudo

    # Conteúdo da palestra e ausência de [[[[ ou "None"
    assert "Sessão 1" in conteudo
    assert "[[[[" not in conteudo
    assert "None" not in conteudo