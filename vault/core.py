# vault\core.py
import asyncio
import concurrent.futures
import datetime
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import os
import tempfile


import config
from models import (
    AgendaScout,
    AnaliseVideo,
    ArtefactoIA,
    ObraCitada,
    PalestraAnalise,
    PessoaMencionada,
    SessaoScout,
    VideoCitado,
)
from utils import (
    eh_nome_valido_pessoa,
    eh_organizacao,
    verificar_link_ativo,
)

logger = logging.getLogger("yt_obsidian")

_RESERVADOS_WINDOWS = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *{f"COM{i}" for i in range(1, 10)},
    *{f"LPT{i}" for i in range(1, 10)},
}


def _escapar_yaml_str(valor: Any) -> str:
    """Escapa aspas e quebras de linha para valores em aspas duplas no YAML."""
    texto = "" if valor is None else str(valor)
    return texto.replace("\\", "\\\\").replace('"', '\\"').replace("\r\n", " ").replace("\n", " ")


def _yaml_lista(chave: str, valores: List[str], indent: int = 0) -> str:
    """Gera uma lista em bloco YAML (`chave: []` se vazia) para evitar `[[[X]]]`."""
    prefixo = " " * indent
    if not valores:
        return f"{prefixo}{chave}: []\n"
    linhas = [f"{prefixo}{chave}:"]
    for v in valores:
        linhas.append(f'{prefixo}  - "{_escapar_yaml_str(v)}"')
    return "\n".join(linhas) + "\n"


def _sanitizar_blockquote(texto: Optional[str]) -> str:
    """Garante que blocos de citação multi-linha mantêm `> ` sem duplicar prefixos."""
    if not texto:
        return ""
    linhas = []
    for linha in str(texto).splitlines():
        linha_limpa = linha.lstrip()
        if linha_limpa.startswith(">"):
            linha_limpa = linha_limpa[1:].lstrip()
        linhas.append(f"> {linha_limpa}" if linha_limpa else ">")
    return "\n".join(linhas)


def _correr_async(coro):
    """Executa uma coroutine de forma segura mesmo com um event loop ativo."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    def _runner():
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_runner).result()


def limpar_nome_ficheiro(nome: str) -> str:
    """Remove caracteres inválidos e normaliza nomes de ficheiros no Windows e Obsidian."""
    nome_limpo = re.sub(r'[<>:"/\\|?*]', "", nome or "")
    nome_limpo = re.sub(r"\s+", " ", nome_limpo).strip()
    nome_limpo = nome_limpo.rstrip(" .")
    if nome_limpo.upper() in _RESERVADOS_WINDOWS:
        nome_limpo = f"_{nome_limpo}"
    return (nome_limpo[:120]).rstrip(" .") or "Nota"


def _obter_verificador_link():
    """Permite monkeypatch tanto em `vault_writer` como em `vault.core` nos testes."""
    import sys

    vw_mod = sys.modules.get("vault_writer")
    if vw_mod is not None and hasattr(vw_mod, "verificar_link_ativo"):
        return vw_mod.verificar_link_ativo
    return verificar_link_ativo


async def _validar_lista_recursos_async(
    recursos: List[str],
    timeout: float = 3.5,
    max_concorrencia: int = 10,
) -> List[str]:
    """Verifica todos os URLs de cada recurso em paralelo com limite de concorrência."""
    if not recursos:
        return []

    semaforo = asyncio.Semaphore(max_concorrencia)
    verificador = _obter_verificador_link()

    async def _validar_url(url: str) -> bool:
        async with semaforo:
            try:
                return await asyncio.to_thread(verificador, url, timeout)
            except Exception:
                return False

    async def processar_item(recurso: str) -> str:
        urls = re.findall(r"https?://[^\s\]\)]+", recurso)
        if not urls:
            return recurso

        urls_limpos = [u.rstrip(".,;:") for u in urls]
        resultados = await asyncio.gather(*(_validar_url(u) for u in urls_limpos))
        if all(resultados):
            return recurso

        inativos = [u for u, ok in zip(urls_limpos, resultados) if not ok]
        sufixo = " ⚠️ *(Link possivelmente inativo: " + ", ".join(inativos) + ")*"
        return f"{recurso}{sufixo}"

    return await asyncio.gather(*(processar_item(r) for r in recursos))


def validar_recursos_externos(recursos: List[str], ativar: bool = True) -> List[str]:
    """Ponto de entrada síncrono para validar links externos de forma segura."""
    if not recursos or not ativar:
        return recursos
    try:
        return _correr_async(_validar_lista_recursos_async(recursos))
    except Exception as exc:
        logger.warning("Validação de links falhou, a devolver originais: %s", exc)
        return recursos

_SECCOES_GERADAS_PADRAO = {
    "📝 Resumo Executivo",
    "📝 Resumo da Palestra",
    "💡 Principais Takeaways",
    "📊 Métricas & Números Chave",
    "⚠️ Tensões, Riscos & Mitos Desmontados",
    "⚠️ Tensões & Limitações",
    "📅 Agenda & Previsões Futuras",
    "📅 Previsões & Futuro",
    "👤 Pessoas Mencionadas",
    "📚 Livros, Artigos & Papers Citados",
    "🎬 Vídeos Citados / Referenciados",
    "🏢 Organizações & Entidades",
    "🏢 Organizações Citadas",
    "🧩 Artefactos (Modelos, Frameworks, Ferramentas, Hardware...)",
    "🧩 Artefactos & Ferramentas",
    "🔗 Links & Recursos Mencionados",
    "🔗 Recursos & Links",
    "⏱️ Capítulos / Linha Temporal",
    "🏷️ Temas Abordados",
    "🏷️ Temas",
}


def _extrair_seccoes_manuais(conteudo: str) -> List[str]:
    """Extrai secções H2 (`## ...`) do ficheiro existente que não são geradas automaticamente."""
    corpo = re.sub(r"^---\n[\s\S]*?\n---\n?", "", conteudo, count=1)
    partes = re.split(r"(?m)^(?=##\s+)", corpo)
    manuais: List[str] = []
    for parte in partes:
        parte_limpa = parte.strip()
        if not parte_limpa.startswith("## "):
            continue
        primeira_linha = parte_limpa.splitlines()[0][3:].strip()
        if primeira_linha not in _SECCOES_GERADAS_PADRAO:
            manuais.append(parte_limpa)
    return manuais


class ObsidianVaultWriter:
    """Orquestrador central de escrita no Obsidian, delegando por domínio para especialistas."""

    def __init__(self, vault_path: str = config.DEFAULT_VAULT_PATH, validar_links: bool = True):
        from vault.conferencias import ConferenciasWriter
        from vault.entidades import EntidadesWriter
        from vault.videos import VideosWriter

        self.vault_path = Path(vault_path)
        self.validar_links = validar_links
        self.pasta_videos = self.vault_path / config.PASTA_VIDEOS
        self.pasta_pessoas = self.vault_path / config.PASTA_PESSOAS
        self.pasta_livros = self.vault_path / config.PASTA_LIVROS
        self.pasta_temas = self.vault_path / config.PASTA_TEMAS
        self.pasta_artefactos = self.vault_path / config.PASTA_ARTEFACTOS
        self.pasta_organizacoes = self.vault_path / config.PASTA_ORGANIZACOES

        for pasta in [
            self.pasta_videos,
            self.pasta_pessoas,
            self.pasta_livros,
            self.pasta_temas,
            self.pasta_artefactos,
            self.pasta_organizacoes,
        ]:
            pasta.mkdir(parents=True, exist_ok=True)

        self.entidades = EntidadesWriter(self)
        self.videos = VideosWriter(self)
        self.conferencias = ConferenciasWriter(self)

    # ------------------------------------------------------------------
    # Helpers partilhados
    # ------------------------------------------------------------------

    def _escrever_atomico(self, caminho: Path, conteudo: str) -> None:
        """Escreve um ficheiro UTF-8 de forma atómica no mesmo sistema de ficheiros."""
        caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=caminho.parent,
                prefix=f".{caminho.stem}.",
                suffix=".tmp",
                delete=False,
            ) as tmp_file:
                tmp_path = Path(tmp_file.name)
                tmp_file.write(conteudo)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())

            os.replace(tmp_path, caminho)
        except Exception:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise
    
    
    
    def _inserir_antes_resenha(self, conteudo: str, bloco_novo: str) -> str | None:
        """Insere bloco_novo antes da secção '# Resenha do dia' preservando separadores anteriores."""
        match = re.search(r"(#\s+Resenha do [Dd]ia)", conteudo)
        if not match:
            return None

        idx = match.start()
        antes = conteudo[:idx].rstrip("\n")
        resenha = conteudo[idx:]
        if antes:
            return f"{antes}\n\n{bloco_novo}\n\n{resenha}"
        return f"{bloco_novo}\n\n{resenha}"

    def _adicionar_link_se_nao_existir(self, conteudo: str, seccao_titulo: str, novo_link: str) -> str:
        """Adiciona um item a uma secção do Markdown se ele ainda não estiver presente."""
        if novo_link in conteudo:
            return conteudo

        if seccao_titulo in conteudo:
            padrao = re.escape(seccao_titulo) + r"\n+"
            substituicao = lambda _m: f"{seccao_titulo}\n- {novo_link}\n"
            novo_conteudo, count = re.subn(padrao, substituicao, conteudo, count=1)
            if count > 0:
                return novo_conteudo

        return conteudo.rstrip() + f"\n\n{seccao_titulo}\n- {novo_link}\n"

    def _carregar_historico_vault(self) -> Dict[str, Any]:
        """Carrega o histórico associado a este cofre, se existir."""
        from main import _resolver_caminho_historico, carregar_historico

        caminho_hist = _resolver_caminho_historico(Path(self.vault_path).resolve())
        if not caminho_hist.exists():
            return {}
        return carregar_historico(caminho_hist) or {}

    def _extrair_entidades_base(self, pessoas: List[PessoaMencionada], organizacoes: List[str]):
        """Filtra pessoas válidas e promove organizações detetadas na lista de pessoas."""
        pessoas_validas = [p for p in pessoas if eh_nome_valido_pessoa(p.nome)]
        organizacoes_extra = {p.nome.strip() for p in pessoas if eh_organizacao(p.nome)}
        organizacoes_todas = list(
            {*[o.strip() for o in organizacoes if o and o.strip()], *organizacoes_extra}
        )
        return pessoas_validas, organizacoes_todas

    def _persistir_entidades_relacionadas(
        self,
        nota_wikilink: str,
        pessoas_validas: List[PessoaMencionada],
        obras: List[ObraCitada],
        temas: List[str],
        organizacoes_todas: List[str],
        artefactos: List[ArtefactoIA],
        videos_citados: Optional[List[VideoCitado]] = None,
    ) -> None:
        """Cria/atualiza todas as notas atómicas ligadas a um vídeo ou palestra."""
        for p in pessoas_validas:
            obras_desta_pessoa = [o.titulo for o in obras if p.nome in o.autores]
            self.salvar_ou_atualizar_pessoa(p, nota_wikilink, obras_desta_pessoa)

        for o in obras:
            self.salvar_ou_atualizar_obra(o, nota_wikilink)

        for t in temas:
            self.salvar_ou_atualizar_tema(t, nota_wikilink)

        for org in organizacoes_todas:
            artefactos_da_org = [
                a.nome
                for a in artefactos
                if a.fabricante_ou_autor and a.fabricante_ou_autor.strip().lower() == org.lower()
            ]
            self.salvar_ou_atualizar_organizacao(org, nota_wikilink, artefactos_da_org)

        for a in artefactos:
            self.salvar_ou_atualizar_artefacto(a, nota_wikilink)

        if videos_citados:
            for v in videos_citados:
                canal_raw = (v.canal_ou_orador or "").strip()
                if canal_raw and eh_nome_valido_pessoa(canal_raw):
                    self.salvar_ou_atualizar_pessoa(
                        PessoaMencionada(
                            nome=canal_raw,
                            papel_ou_bio=f"Referenciado no vídeo citado '{v.titulo_ou_assunto}'.",
                        ),
                        nota_wikilink,
                        [],
                    )

    # ------------------------------------------------------------------
    # Nota diária
    # ------------------------------------------------------------------

    def formatar_entrada_diario(self, dados_video: Dict[str, Any], video_wikilink: str, data_leitura: str) -> str:
        """Gera o bloco de entrada no diário exatamente no formato personalizado do utilizador."""
        canal_id = dados_video.get("canal_id")
        canal_str = f"{dados_video.get('canal')} (ID: {canal_id})" if canal_id else dados_video.get("canal")
        descricao = (dados_video.get("descricao") or "").strip()

        return (
            "===========================\n"
            f"# {video_wikilink}\n"
            "=== METADADOS DO VÍDEO ===\n"
            f"Título: {dados_video.get('titulo')}\n"
            f"Canal: {canal_str}\n"
            f"Data de Publicação: {dados_video.get('data')}\n"
            f"Data de Leitura: {data_leitura}\n"
            f"Link: {dados_video.get('url')}\n\n"
            "--- Descrição ---\n"
            f"{descricao}\n"
        )

    def atualizar_nota_diaria(
        self,
        dados_video: Dict[str, Any],
        video_wikilink: str,
        analise: AnaliseVideo,
        data_leitura: str = None,
    ):
        """Regista o bloco do vídeo no diário (YYYY-MM-DD.md) usando a data de leitura."""
        if not data_leitura:
            data_leitura = datetime.date.today().isoformat()

        caminho_diario = self.vault_path / f"{data_leitura}.md"
        bloco_novo = self.formatar_entrada_diario(dados_video, video_wikilink, data_leitura)

        if caminho_diario.exists():
            conteudo = caminho_diario.read_text(encoding="utf-8")
            if video_wikilink in conteudo:
                return

            novo_conteudo = self._inserir_antes_resenha(conteudo, bloco_novo)
            if novo_conteudo is not None:
                self._escrever_atomico(caminho_diario, novo_conteudo)
                logger.info(
                    f"    ✓ Diário {data_leitura}.md atualizado com o bloco de metadados antes da resenha.\n"
                )
                return

            novo_conteudo = conteudo.rstrip() + f"\n\n{bloco_novo}\n"
            self._escrever_atomico(caminho_diario, novo_conteudo)
            logger.info(f"    ✓ Diário {data_leitura}.md atualizado com o novo bloco de metadados.\n")
        else:
            self._escrever_atomico(caminho_diario, bloco_novo + "\n")
            logger.info(f"    ✓ Diário {data_leitura}.md criado com o bloco de metadados.\n")

    # ------------------------------------------------------------------
    # Delegação: Entidades
    # ------------------------------------------------------------------

    def _ligar_fabricante(self, fabricante: str, artefacto_nome: str, video_link: str):
        self.entidades.ligar_fabricante(fabricante, artefacto_nome, video_link)

    def salvar_ou_atualizar_pessoa(self, pessoa: PessoaMencionada, video_link: str, obras: List[str]):
        self.entidades.salvar_ou_atualizar_pessoa(pessoa, video_link, obras)

    def salvar_ou_atualizar_organizacao(
        self,
        nome: str,
        video_link: str,
        artefactos_relacionados: List[str] = None,
    ):
        self.entidades.salvar_ou_atualizar_organizacao(nome, video_link, artefactos_relacionados)

    def salvar_ou_atualizar_obra(self, obra: ObraCitada, video_link: str):
        self.entidades.salvar_ou_atualizar_obra(obra, video_link)

    def salvar_ou_atualizar_tema(self, tema: str, video_link: str):
        self.entidades.salvar_ou_atualizar_tema(tema, video_link)

    def salvar_ou_atualizar_artefacto(self, artefacto: ArtefactoIA, video_link: str):
        self.entidades.salvar_ou_atualizar_artefacto(artefacto, video_link)

    # ------------------------------------------------------------------
    # Delegação: Vídeos
    # ------------------------------------------------------------------

    def _resolver_video_citado(
        self,
        video: VideoCitado,
        historico: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, Optional[str]]:
        return self.videos.resolver_video_citado(video, historico)

    def _renderizar_seccao_videos_citados(
        self,
        videos_citados: List[VideoCitado],
        historico: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, List[str]]:
        return self.videos.renderizar_seccao_videos_citados(videos_citados, historico)

    def salvar_video(self, dados_video: Dict[str, Any], analise: AnaliseVideo, data_leitura: str = None) -> Path:
        return self.videos.salvar_video(dados_video, analise, data_leitura)

    # ------------------------------------------------------------------
    # Delegação: Conferências
    # ------------------------------------------------------------------

    def obter_pasta_conferencia(self, nome_conferencia: str) -> Path:
        return self.conferencias.obter_pasta_conferencia(nome_conferencia)

    def salvar_palestra_conferencia(
        self,
        dados_video: Dict[str, Any],
        agenda: AgendaScout,
        sessao: SessaoScout,
        analise: PalestraAnalise,
        data_leitura: str = None,
        historico: Optional[Dict[str, Any]] = None,
    ) -> Path:
        return self.conferencias.salvar_palestra_conferencia(
            dados_video, agenda, sessao, analise, data_leitura, historico
        )

    def salvar_ou_atualizar_moc_conferencia(
        self,
        dados_video: Dict[str, Any],
        agenda: AgendaScout,
        palestras_processadas: List[Dict[str, Any]],
        data_leitura: str = None,
    ) -> Path:
        return self.conferencias.salvar_ou_atualizar_moc_conferencia(
            dados_video, agenda, palestras_processadas, data_leitura
        )

    def atualizar_diario_conferencia(
        self,
        dados_video: Dict[str, Any],
        agenda: AgendaScout,
        moc_wikilink: str,
        total_palestras: int,
        data_leitura: str = None,
        pasta_conf_nome: Optional[str] = None,
    ):
        self.conferencias.atualizar_diario_conferencia(
            dados_video, agenda, moc_wikilink, total_palestras, data_leitura, pasta_conf_nome
        )