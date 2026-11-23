import asyncio
import concurrent.futures
import datetime
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import config
from models import (
    AgendaScout,
    AnaliseVideo,
    ArtefactoIA,
    ObraCitada,
    PalestraAnalise,
    PessoaMencionada,
    SessaoScout,
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


async def _validar_lista_recursos_async(
    recursos: List[str],
    timeout: float = 3.5,
    max_concorrencia: int = 10,
) -> List[str]:
    """Verifica todos os URLs de cada recurso em paralelo com limite de concorrência."""
    if not recursos:
        return []

    semaforo = asyncio.Semaphore(max_concorrencia)

    async def _validar_url(url: str) -> bool:
        async with semaforo:
            try:
                return await asyncio.to_thread(verificar_link_ativo, url, timeout)
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


class ObsidianVaultWriter:
    def __init__(self, vault_path: str = config.DEFAULT_VAULT_PATH, validar_links: bool = True):
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

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

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

    def _ligar_fabricante(self, fabricante: str, artefacto_nome: str, video_link: str):
        """Cria ou atualiza a nota adequada para o fabricante de um artefacto."""
        if not fabricante or not fabricante.strip():
            return
        fabricante = fabricante.strip()

        if eh_organizacao(fabricante):
            self.salvar_ou_atualizar_organizacao(
                nome=fabricante,
                video_link=video_link,
                artefactos_relacionados=[artefacto_nome],
            )
        elif eh_nome_valido_pessoa(fabricante):
            pessoa = PessoaMencionada(
                nome=fabricante,
                papel_ou_bio=f"Criador(a) do artefacto [[{limpar_nome_ficheiro(artefacto_nome)}]].",
            )
            self.salvar_ou_atualizar_pessoa(pessoa, video_link, [])

    # ------------------------------------------------------------------
    # Pessoas
    # ------------------------------------------------------------------

    def salvar_ou_atualizar_pessoa(self, pessoa: PessoaMencionada, video_link: str, obras: List[str]):
        """Cria ou atualiza a nota de uma pessoa com a bio e os links para vídeos e livros."""
        if not eh_nome_valido_pessoa(pessoa.nome):
            return

        nome_ficheiro = f"{limpar_nome_ficheiro(pessoa.nome)}.md"
        caminho = self.pasta_pessoas / nome_ficheiro

        if not caminho.exists():
            bio = _sanitizar_blockquote(pessoa.papel_ou_bio) or ">"
            obras_yaml = _yaml_lista("obras", [f"[[{limpar_nome_ficheiro(o)}]]" for o in obras])
            conteudo = (
                "---\n"
                "tipo: pessoa\n"
                "tags:\n"
                "  - pessoa\n"
                "aliases: []\n"
                f"{obras_yaml}"
                "---\n"
                f"# {pessoa.nome}\n\n"
                f"{bio}\n\n"
                "### 📚 Obras Relacionadas:\n"
            )
            for obra in obras:
                conteudo += f"- [[{limpar_nome_ficheiro(obra)}]]\n"

            conteudo += f"\n### 📹 Mencionada nos Vídeos:\n- {video_link}\n"
            caminho.write_text(conteudo, encoding="utf-8")
        else:
            conteudo_atual = caminho.read_text(encoding="utf-8")
            conteudo_atual = self._adicionar_link_se_nao_existir(
                conteudo_atual, "### 📹 Mencionada nos Vídeos:", video_link
            )
            for obra in obras:
                conteudo_atual = self._adicionar_link_se_nao_existir(
                    conteudo_atual, "### 📚 Obras Relacionadas:", f"[[{limpar_nome_ficheiro(obra)}]]"
                )
            caminho.write_text(conteudo_atual, encoding="utf-8")

    # ------------------------------------------------------------------
    # Organizações
    # ------------------------------------------------------------------

    def salvar_ou_atualizar_organizacao(
        self,
        nome: str,
        video_link: str,
        artefactos_relacionados: List[str] = None,
    ):
        """Cria ou atualiza a nota de uma organização, ligando-a aos vídeos e artefactos."""
        if not nome or not nome.strip():
            return

        nome_ficheiro = f"{limpar_nome_ficheiro(nome)}.md"
        caminho = self.pasta_organizacoes / nome_ficheiro
        artefactos_relacionados = artefactos_relacionados or []

        if not caminho.exists():
            art_yaml = _yaml_lista(
                "artefactos",
                [f"[[{limpar_nome_ficheiro(a)}]]" for a in artefactos_relacionados],
            )
            conteudo = (
                "---\n"
                "tipo: organizacao\n"
                "tags:\n"
                "  - organizacao\n"
                "aliases: []\n"
                f"{art_yaml}"
                "---\n"
                f"# {nome}\n\n"
                "### 🧩 Artefactos:\n"
            )
            if artefactos_relacionados:
                for a in artefactos_relacionados:
                    conteudo += f"- [[{limpar_nome_ficheiro(a)}]]\n"
            else:
                conteudo += "_Nenhum artefacto associado ainda._\n"

            conteudo += f"\n### 📹 Mencionada nos Vídeos:\n- {video_link}\n"
            caminho.write_text(conteudo, encoding="utf-8")
        else:
            conteudo_atual = caminho.read_text(encoding="utf-8")
            conteudo_atual = self._adicionar_link_se_nao_existir(
                conteudo_atual, "### 📹 Mencionada nos Vídeos:", video_link
            )
            for a in artefactos_relacionados:
                conteudo_atual = self._adicionar_link_se_nao_existir(
                    conteudo_atual, "### 🧩 Artefactos:", f"[[{limpar_nome_ficheiro(a)}]]"
                )
            caminho.write_text(conteudo_atual, encoding="utf-8")

    # ------------------------------------------------------------------
    # Obras
    # ------------------------------------------------------------------
    def salvar_ou_atualizar_obra(self, obra: ObraCitada, video_link: str):
        """Cria ou atualiza a nota de um livro ou artigo conectando aos autores e vídeos."""
        nome_ficheiro = f"{limpar_nome_ficheiro(obra.titulo)}.md"
        caminho = self.pasta_livros / nome_ficheiro

        autores_links = [f"[[{limpar_nome_ficheiro(a)}]]" for a in (obra.autores or [])]
        autores_str = ", ".join(autores_links) if autores_links else "Não especificado"
        tipo_lower = (obra.tipo or "livro").strip().lower()

        if not caminho.exists():
            contexto_str = f"{_sanitizar_blockquote(obra.contexto)}\n\n" if obra.contexto else ""
            autores_yaml = _yaml_lista("autores", autores_links)
            conteudo = (
                "---\n"
                f"tipo: {_escapar_yaml_str(tipo_lower)}\n"
                f"{autores_yaml}"
                "tags:\n"
                f"  - {_escapar_yaml_str(tipo_lower)}\n"
                "---\n"
                f"# {obra.titulo}\n\n"
                f"**Tipo:** {obra.tipo}  \n"
                f"**Autor(es):** {autores_str}\n\n"
                f"{contexto_str}"
                "### 📹 Mencionado nos Vídeos:\n"
                f"- {video_link}\n"
            )
            caminho.write_text(conteudo, encoding="utf-8")
        else:
            conteudo_atual = caminho.read_text(encoding="utf-8")
            conteudo_atual = self._adicionar_link_se_nao_existir(
                conteudo_atual, "### 📹 Mencionado nos Vídeos:", video_link
            )
            caminho.write_text(conteudo_atual, encoding="utf-8")

        for autor in (obra.autores or []):
            autor_pessoa = PessoaMencionada(
                nome=autor,
                papel_ou_bio=f"Autor(a) da obra [[{limpar_nome_ficheiro(obra.titulo)}]].",
            )
            self.salvar_ou_atualizar_pessoa(autor_pessoa, video_link, [obra.titulo])
    # ------------------------------------------------------------------
    # Temas
    # ------------------------------------------------------------------

    def salvar_ou_atualizar_tema(self, tema: str, video_link: str):
        """Cria ou atualiza uma nota de tema com os vídeos associados."""
        nome_ficheiro = f"{limpar_nome_ficheiro(tema)}.md"
        caminho = self.pasta_temas / nome_ficheiro

        if not caminho.exists():
            conteudo = (
                "---\n"
                "tipo: tema\n"
                "tags:\n"
                "  - tema\n"
                "---\n"
                f"# {tema}\n\n"
                "### 📹 Vídeos sobre este tema:\n"
                f"- {video_link}\n"
            )
            caminho.write_text(conteudo, encoding="utf-8")
        else:
            conteudo_atual = caminho.read_text(encoding="utf-8")
            conteudo_atual = self._adicionar_link_se_nao_existir(
                conteudo_atual, "### 📹 Vídeos sobre este tema:", video_link
            )
            caminho.write_text(conteudo_atual, encoding="utf-8")

    # ------------------------------------------------------------------
    # Artefactos
    # ------------------------------------------------------------------

    def salvar_ou_atualizar_artefacto(self, artefacto: ArtefactoIA, video_link: str):
        """Cria ou atualiza a nota de um artefacto (modelo, framework, ferramenta, etc)."""
        nome_ficheiro = f"{limpar_nome_ficheiro(artefacto.nome)}.md"
        caminho = self.pasta_artefactos / nome_ficheiro

        subtipo = (artefacto.subtipo or "modelo").strip().lower()
        if subtipo not in config.SUBTIPOS_ARTEFACTO:
            subtipo = "modelo"

        fabricante = (artefacto.fabricante_ou_autor or "").strip() or None
        fabricante_link = f"[[{limpar_nome_ficheiro(fabricante)}]]" if fabricante else ""

        if not caminho.exists():
            descricao_str = f"{_sanitizar_blockquote(artefacto.descricao)}\n\n" if artefacto.descricao else ""
            fab_yaml = f'fabricante: "{_escapar_yaml_str(fabricante_link)}"\n' if fabricante else "fabricante:\n"
            conteudo = (
                "---\n"
                "tipo: artefacto\n"
                f"subtipo: {_escapar_yaml_str(subtipo)}\n"
                f"{fab_yaml}"
                "tags:\n"
                f"  - artefacto/{_escapar_yaml_str(subtipo)}\n"
                "---\n"
                f"# {artefacto.nome}\n\n"
                f"**Subtipo:** {subtipo}  \n"
                f"**Fabricante/Autor:** {fabricante_link if fabricante else 'Desconhecido'}\n\n"
                f"{descricao_str}"
                "### 📹 Mencionado nos Vídeos:\n"
                f"- {video_link}\n"
            )
            caminho.write_text(conteudo, encoding="utf-8")
        else:
            conteudo_atual = caminho.read_text(encoding="utf-8")
            conteudo_atual = self._adicionar_link_se_nao_existir(
                conteudo_atual, "### 📹 Mencionado nos Vídeos:", video_link
            )
            caminho.write_text(conteudo_atual, encoding="utf-8")

        if fabricante:
            self._ligar_fabricante(fabricante, artefacto.nome, video_link)

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
                caminho_diario.write_text(novo_conteudo, encoding="utf-8")
                logger.info(
                    f"    ✓ Diário {data_leitura}.md atualizado com o bloco de metadados antes da resenha.\n"
                )
                return

            novo_conteudo = conteudo.rstrip() + f"\n\n{bloco_novo}\n"
            caminho_diario.write_text(novo_conteudo, encoding="utf-8")
            logger.info(f"    ✓ Diário {data_leitura}.md atualizado com o novo bloco de metadados.\n")
        else:
            caminho_diario.write_text(bloco_novo + "\n", encoding="utf-8")
            logger.info(f"    ✓ Diário {data_leitura}.md criado com o bloco de metadados.\n")

    # ------------------------------------------------------------------
    # Nota principal do vídeo
    # ------------------------------------------------------------------

    def salvar_video(self, dados_video: Dict[str, Any], analise: AnaliseVideo, data_leitura: str = None) -> Path:
        """Cria a nota principal do vídeo e dispara a criação/atualização de todas as entidades conectadas."""
        if not data_leitura:
            data_leitura = datetime.date.today().isoformat()

        nome_base = limpar_nome_ficheiro(analise.titulo_sugerido or dados_video.get("titulo", "Video"))
        nome_ficheiro = f"{nome_base}.md"
        caminho_video = self.pasta_videos / nome_ficheiro
        video_wikilink = f"[[{caminho_video.stem}]]"

        pessoas_validas = [p for p in analise.pessoas if eh_nome_valido_pessoa(p.nome)]
        organizacoes_extra = {p.nome.strip() for p in analise.pessoas if eh_organizacao(p.nome)}
        organizacoes_todas = list({*[o.strip() for o in analise.organizacoes if o and o.strip()], *organizacoes_extra})

        pessoas_links = [f"[[{limpar_nome_ficheiro(p.nome)}]]" for p in pessoas_validas]
        obras_links = [f"[[{limpar_nome_ficheiro(o.titulo)}]]" for o in analise.obras]
        temas_links = [f"[[{limpar_nome_ficheiro(t)}]]" for t in analise.temas]
        artefactos_links = [f"[[{limpar_nome_ficheiro(a.nome)}]]" for a in analise.artefactos]
        organizacoes_links = [f"[[{limpar_nome_ficheiro(o)}]]" for o in organizacoes_todas]

        data_leitura_final = data_leitura
        if caminho_video.exists():
            conteudo_existente = caminho_video.read_text(encoding="utf-8")
            match = re.search(r'^data_leitura:\s*"?([0-9]{4}-[0-9]{2}-[0-9]{2})"?', conteudo_existente, re.MULTILINE)
            if match:
                data_leitura_final = match.group(1)

        frontmatter = (
            "---\n"
            "tipo: video\n"
            f'titulo: "{_escapar_yaml_str(dados_video.get("titulo"))}"\n'
            f'canal: "{_escapar_yaml_str(dados_video.get("canal"))}"\n'
            f'data_publicacao: "{_escapar_yaml_str(dados_video.get("data"))}"\n'
            f'data_leitura: "{_escapar_yaml_str(data_leitura_final)}"\n'
            f'url: "{_escapar_yaml_str(dados_video.get("url"))}"\n'
            "tags:\n"
            "  - video/youtube\n"
            + _yaml_lista("temas", temas_links)
            + _yaml_lista("pessoas", pessoas_links)
            + _yaml_lista("obras", obras_links)
            + _yaml_lista("artefactos", artefactos_links)
            + _yaml_lista("organizacoes", organizacoes_links)
            + "---\n"
        )

        nota = frontmatter + (
            f"# {analise.titulo_sugerido}\n\n"
            f"> 📺 **Canal:** [{dados_video.get('canal')}]({dados_video.get('canal_url', '')})  \n"
            f"> 📅 **Data:** {dados_video.get('data')}  \n"
            f"> 🔗 **Ver no YouTube:** [{dados_video.get('url')}]({dados_video.get('url')})\n\n"
            "---\n\n"
            "## 📝 Resumo Executivo\n"
            f"{analise.resumo_executivo}\n\n"
            "---\n\n"
            "## 💡 Principais Takeaways\n"
        )
        for takeaway in analise.takeaways_principais:
            nota += f"- {takeaway}\n"

        if analise.metricas_e_numeros:
            nota += "\n---\n\n## 📊 Métricas & Números Chave\n"
            for metrica in analise.metricas_e_numeros:
                nota += f"- {metrica}\n"

        if analise.tensoes_e_riscos:
            nota += "\n---\n\n## ⚠️ Tensões, Riscos & Mitos Desmontados\n"
            for tensao in analise.tensoes_e_riscos:
                nota += f"- {tensao}\n"

        if analise.agenda_e_previsoes:
            nota += "\n---\n\n## 📅 Agenda & Previsões Futuras\n"
            for item in analise.agenda_e_previsoes:
                nota += f"- {item}\n"

        nota += "\n---\n\n## 👤 Pessoas Mencionadas\n"
        if pessoas_validas:
            for p in pessoas_validas:
                nota += f"- **[[{limpar_nome_ficheiro(p.nome)}]]**: {p.papel_ou_bio}\n"
        else:
            nota += "_Nenhuma figura pública ou especialista identificado com nome completo._\n"

        nota += "\n---\n\n## 📚 Livros, Artigos & Papers Citados\n"
        if analise.obras:
            for o in analise.obras:
                autores_fmt = (
                    ", ".join(f"[[{limpar_nome_ficheiro(a)}]]" for a in o.autores)
                    if o.autores
                    else "Autor desconhecido"
                )
                contexto_fmt = f" — _{o.contexto}_" if o.contexto else ""
                nota += f"- **[[{limpar_nome_ficheiro(o.titulo)}]]** ({o.tipo}) por {autores_fmt}{contexto_fmt}\n"
        else:
            nota += "_Nenhum livro ou artigo citado explicitamente._\n"

        if organizacoes_todas:
            nota += "\n---\n\n## 🏢 Organizações & Entidades\n"
            for org in organizacoes_todas:
                nota += f"- [[{limpar_nome_ficheiro(org)}]]\n"

        if analise.artefactos:
            nota += "\n---\n\n## 🧩 Artefactos (Modelos, Frameworks, Ferramentas, Hardware...)\n"
            for a in analise.artefactos:
                fabricante = f" — _{a.fabricante_ou_autor}_" if a.fabricante_ou_autor else ""
                desc = f": {a.descricao}" if a.descricao else ""
                nota += f"- **[[{limpar_nome_ficheiro(a.nome)}]]** (`{a.subtipo}`){fabricante}{desc}\n"

        if analise.recursos_e_links:
            if self.validar_links:
                logger.info("    🌐 A verificar disponibilidade dos links externos...")
            recursos_verificados = validar_recursos_externos(analise.recursos_e_links, ativar=self.validar_links)
            nota += "\n---\n\n## 🔗 Links & Recursos Mencionados\n"
            for recurso in recursos_verificados:
                nota += f"- {recurso}\n"

        if analise.capitulos:
            nota += "\n---\n\n## ⏱️ Capítulos / Linha Temporal\n"
            for cap in analise.capitulos:
                nota += f"- {cap}\n"

        nota += "\n---\n\n## 🏷️ Temas Abordados\n"
        for t in analise.temas:
            nota += f"- [[{limpar_nome_ficheiro(t)}]]\n"

        caminho_video.write_text(nota, encoding="utf-8")
        self.atualizar_nota_diaria(dados_video, video_wikilink, analise, data_leitura_final)

        for p in pessoas_validas:
            obras_desta_pessoa = [o.titulo for o in analise.obras if p.nome in o.autores]
            self.salvar_ou_atualizar_pessoa(p, video_wikilink, obras_desta_pessoa)

        for o in analise.obras:
            self.salvar_ou_atualizar_obra(o, video_wikilink)

        for t in analise.temas:
            self.salvar_ou_atualizar_tema(t, video_wikilink)

        for org in organizacoes_todas:
            artefactos_da_org = [
                a.nome
                for a in analise.artefactos
                if a.fabricante_ou_autor and a.fabricante_ou_autor.strip().lower() == org.lower()
            ]
            self.salvar_ou_atualizar_organizacao(org, video_wikilink, artefactos_da_org)

        for a in analise.artefactos:
            self.salvar_ou_atualizar_artefacto(a, video_wikilink)

        return caminho_video

    # ------------------------------------------------------------------
    # Módulo de Conferências e Múltiplos Dias (Opção A: Subpasta Dedicada)
    # ------------------------------------------------------------------

    def obter_pasta_conferencia(self, nome_conferencia: str) -> Path:
        """Cria e devolve a subpasta dedicada a uma conferência dentro de Videos/."""
        pasta_conf = self.pasta_videos / limpar_nome_ficheiro(nome_conferencia)
        pasta_conf.mkdir(parents=True, exist_ok=True)
        return pasta_conf

    def salvar_palestra_conferencia(
        self,
        dados_video: Dict[str, Any],
        agenda: AgendaScout,
        sessao: SessaoScout,
        analise: PalestraAnalise,
        data_leitura: str = None,
    ) -> Path:
        """Cria uma nota atómica dedicada a uma palestra individual dentro da subpasta da conferência."""
        if not data_leitura:
            data_leitura = datetime.date.today().isoformat()

        pasta_conf = self.obter_pasta_conferencia(agenda.nome_conferencia)
        dia_num = agenda.dia or 1
        dia_prefixo = f"D{dia_num:02d}"

        orador_limpo = f" - {limpar_nome_ficheiro(sessao.orador_principal)}" if sessao.orador_principal else ""
        titulo_limpo = limpar_nome_ficheiro(analise.titulo_palestra or sessao.titulo_palestra)
        nome_ficheiro = f"{dia_prefixo} - {sessao.ordem:02d}{orador_limpo} - {titulo_limpo}.md"
        if len(nome_ficheiro) > 130:
            nome_ficheiro = f"{dia_prefixo} - {sessao.ordem:02d}{orador_limpo} - {titulo_limpo[:80]}.md"

        caminho_palestra = pasta_conf / nome_ficheiro
        palestra_wikilink = f"[[{caminho_palestra.stem}]]"
        moc_conferencia_wikilink = f"[[{limpar_nome_ficheiro(agenda.nome_conferencia)}]]"

        video_id = dados_video.get("id")
        deep_link = f"https://youtu.be/{video_id}?t={sessao.segundos_inicio}" if video_id else dados_video.get("url")

        pessoas_validas = [p for p in analise.pessoas if eh_nome_valido_pessoa(p.nome)]
        organizacoes_extra = {p.nome.strip() for p in analise.pessoas if eh_organizacao(p.nome)}
        organizacoes_todas = list({*[o.strip() for o in analise.organizacoes if o and o.strip()], *organizacoes_extra})

        pessoas_links = [f"[[{limpar_nome_ficheiro(p.nome)}]]" for p in pessoas_validas]
        obras_links = [f"[[{limpar_nome_ficheiro(o.titulo)}]]" for o in analise.obras]
        temas_links = [f"[[{limpar_nome_ficheiro(t)}]]" for t in analise.temas]
        artefactos_links = [f"[[{limpar_nome_ficheiro(a.nome)}]]" for a in analise.artefactos]
        organizacoes_links = [f"[[{limpar_nome_ficheiro(o)}]]" for o in organizacoes_todas]

        orador_fmt = (
            f"[[{limpar_nome_ficheiro(sessao.orador_principal)}]]"
            if sessao.orador_principal
            else "Vários / Painel"
        )
        org_fmt = f"([[{limpar_nome_ficheiro(sessao.organizacao)}]])" if sessao.organizacao else ""
        tag_conf = limpar_nome_ficheiro(agenda.nome_conferencia).lower().replace(" ", "-")

        frontmatter = (
            "---\n"
            "tipo: video_palestra\n"
            f'conferencia: "{_escapar_yaml_str(moc_conferencia_wikilink)}"\n'
            f"dia: {dia_num}\n"
            f"ordem: {sessao.ordem}\n"
            f'orador: "{_escapar_yaml_str(sessao.orador_principal or "Vários")}"\n'
            f'organizacao: "{_escapar_yaml_str(sessao.organizacao or "")}"\n'
            f'timestamp_inicio: "{_escapar_yaml_str(sessao.timestamp_inicio)}"\n'
            f'timestamp_fim: "{_escapar_yaml_str(sessao.timestamp_fim)}"\n'
            f'url_palestra: "{_escapar_yaml_str(deep_link)}"\n'
            f'data_publicacao: "{_escapar_yaml_str(dados_video.get("data"))}"\n'
            f'data_leitura: "{_escapar_yaml_str(data_leitura)}"\n'
            "tags:\n"
            "  - video/palestra\n"
            f"  - conferencia/{_escapar_yaml_str(tag_conf)}\n"
            + _yaml_lista("temas", temas_links)
            + _yaml_lista("pessoas", pessoas_links)
            + _yaml_lista("obras", obras_links)
            + _yaml_lista("artefactos", artefactos_links)
            + _yaml_lista("organizacoes", organizacoes_links)
            + "---\n"
        )

        nota = frontmatter + (
            f"# {analise.titulo_palestra or sessao.titulo_palestra}\n\n"
            f"> 🏛️ **Conferência:** {moc_conferencia_wikilink} (Dia {dia_num})  \n"
            f"> 👤 **Orador:** {orador_fmt} {org_fmt}  \n"
            f"> ⏱️ **Momento:** `{sessao.timestamp_inicio} -> {sessao.timestamp_fim}`  \n"
            f"> 🔗 **Ver Palestra no YouTube:** [{deep_link}]({deep_link})\n\n"
            "---\n\n"
            "## 📝 Resumo da Palestra\n"
            f"{analise.resumo_executivo}\n\n"
            "---\n\n"
            "## 💡 Principais Takeaways\n"
        )
        for tk in analise.takeaways_principais:
            nota += f"- {tk}\n"

        if analise.metricas_e_numeros:
            nota += "\n---\n\n## 📊 Métricas & Números Chave\n"
            for m in analise.metricas_e_numeros:
                nota += f"- {m}\n"

        if analise.tensoes_e_riscos:
            nota += "\n---\n\n## ⚠️ Tensões & Limitações\n"
            for t in analise.tensoes_e_riscos:
                nota += f"- {t}\n"

        if analise.agenda_e_previsoes:
            nota += "\n---\n\n## 📅 Previsões & Futuro\n"
            for a in analise.agenda_e_previsoes:
                nota += f"- {a}\n"

        if pessoas_validas:
            nota += "\n---\n\n## 👤 Pessoas Mencionadas\n"
            for p in pessoas_validas:
                nota += f"- **[[{limpar_nome_ficheiro(p.nome)}]]**: {p.papel_ou_bio}\n"

        if analise.artefactos:
            nota += "\n---\n\n## 🧩 Artefactos & Ferramentas\n"
            for a in analise.artefactos:
                fab = f" — _{a.fabricante_ou_autor}_" if a.fabricante_ou_autor else ""
                desc = f": {a.descricao}" if a.descricao else ""
                nota += f"- **[[{limpar_nome_ficheiro(a.nome)}]]** (`{a.subtipo}`){fab}{desc}\n"

        if organizacoes_todas:
            nota += "\n---\n\n## 🏢 Organizações Citadas\n"
            for o in organizacoes_todas:
                nota += f"- [[{limpar_nome_ficheiro(o)}]]\n"

        if analise.recursos_e_links:
            recursos_verificados = validar_recursos_externos(analise.recursos_e_links, ativar=self.validar_links)
            nota += "\n---\n\n## 🔗 Recursos & Links\n"
            for r in recursos_verificados:
                nota += f"- {r}\n"

        if analise.temas:
            nota += "\n---\n\n## 🏷️ Temas\n"
            for tm in analise.temas:
                nota += f"- [[{limpar_nome_ficheiro(tm)}]]\n"

        caminho_palestra.write_text(nota, encoding="utf-8")

        for p in pessoas_validas:
            obras_p = [o.titulo for o in analise.obras if p.nome in o.autores]
            self.salvar_ou_atualizar_pessoa(p, palestra_wikilink, obras_p)

        for o in analise.obras:
            self.salvar_ou_atualizar_obra(o, palestra_wikilink)

        for tm in analise.temas:
            self.salvar_ou_atualizar_tema(tm, palestra_wikilink)

        for org in organizacoes_todas:
            artefactos_org = [
                a.nome
                for a in analise.artefactos
                if a.fabricante_ou_autor and a.fabricante_ou_autor.strip().lower() == org.lower()
            ]
            self.salvar_ou_atualizar_organizacao(org, palestra_wikilink, artefactos_org)

        for a in analise.artefactos:
            self.salvar_ou_atualizar_artefacto(a, palestra_wikilink)

        return caminho_palestra

    def salvar_ou_atualizar_moc_conferencia(
        self,
        dados_video: Dict[str, Any],
        agenda: AgendaScout,
        palestras_processadas: List[Dict[str, Any]],
        data_leitura: str = None,
    ) -> Path:
        """Cria ou atualiza a Nota-Mãe MOC da conferência, acumulando os dias sem apagar dias anteriores."""
        if not data_leitura:
            data_leitura = datetime.date.today().isoformat()

        pasta_conf = self.obter_pasta_conferencia(agenda.nome_conferencia)
        nome_ficheiro_moc = f"{limpar_nome_ficheiro(agenda.nome_conferencia)}.md"
        caminho_moc = pasta_conf / nome_ficheiro_moc

        dia_num = agenda.dia or 1
        dia_rotulo = agenda.dia_rotulo or f"Dia {dia_num}"
        data_sessao = agenda.data_sessao or dados_video.get("data", "")
        seccao_cabecalho_dia = f"## 📅 {dia_rotulo} ({data_sessao})"

        duracao_raw = dados_video.get("duracao_segundos")
        try:
            duracao_min = int(float(duracao_raw) // 60) if duracao_raw is not None else 0
        except (TypeError, ValueError):
            duracao_min = 0

        tabela_dia = (
            f"{seccao_cabecalho_dia}\n\n"
            f"> 🔗 **Transmissão Completa deste Dia:** [{dados_video.get('titulo')}]({dados_video.get('url')})  \n"
            f"> ⏱️ **Duração Total:** {duracao_min} min | **Total de Palestras:** {len(palestras_processadas)}\n\n"
            "| # | Início | Orador | Empresa | Palestra |\n"
            "|---|---|---|---|---|\n"
        )
        for p in palestras_processadas:
            s: SessaoScout = p["sessao"]
            link_palestra = f"[[{p['caminho'].stem}]]"
            orador_str = f"[[{limpar_nome_ficheiro(s.orador_principal)}]]" if s.orador_principal else "Painel"
            org_str = f"[[{limpar_nome_ficheiro(s.organizacao)}]]" if s.organizacao else "-"
            tabela_dia += f"| {s.ordem:02d} | `{s.timestamp_inicio}` | {orador_str} | {org_str} | {link_palestra} |\n"

        if not caminho_moc.exists():
            tag_conf = limpar_nome_ficheiro(agenda.nome_conferencia).lower().replace(" ", "-")
            conteudo_moc = (
                "---\n"
                "tipo: conferencia_moc\n"
                f'conferencia: "{_escapar_yaml_str(agenda.nome_conferencia)}"\n'
                f'canal: "{_escapar_yaml_str(dados_video.get("canal"))}"\n'
                f'data_primeira_leitura: "{_escapar_yaml_str(data_leitura)}"\n'
                "tags:\n"
                "  - conferencia/moc\n"
                f"  - conferencia/{_escapar_yaml_str(tag_conf)}\n"
                "---\n"
                f"# 🏛️ {agenda.nome_conferencia}\n\n"
                f"> 📺 **Canal Organizador:** [{dados_video.get('canal')}]({dados_video.get('canal_url', '')})  \n"
                f"> 📂 **Pasta de Palestras:** `{pasta_conf.name}/`\n\n"
                "Este ficheiro é o **Mapa de Conteúdo (MOC)** que centraliza todos os dias e palestras da conferência.\n\n"
                "---\n\n"
                f"{tabela_dia}\n"
            )
            caminho_moc.write_text(conteudo_moc, encoding="utf-8")
        else:
            conteudo_existente = caminho_moc.read_text(encoding="utf-8")
            padrao_dia = re.compile(rf"{re.escape(seccao_cabecalho_dia)}[\s\S]*?(?=\n## 📅|\Z)")
            if padrao_dia.search(conteudo_existente):
                novo_conteudo = padrao_dia.sub(lambda _m: tabela_dia.strip(), conteudo_existente, count=1)
            else:
                novo_conteudo = conteudo_existente.rstrip() + f"\n\n---\n\n{tabela_dia}\n"
            caminho_moc.write_text(novo_conteudo, encoding="utf-8")

        self.atualizar_diario_conferencia(
            dados_video,
            agenda,
            f"[[{caminho_moc.stem}]]",
            len(palestras_processadas),
            data_leitura,
            pasta_conf_nome=pasta_conf.name,
        )

        return caminho_moc

    def atualizar_diario_conferencia(
        self,
        dados_video: Dict[str, Any],
        agenda: AgendaScout,
        moc_wikilink: str,
        total_palestras: int,
        data_leitura: str = None,
        pasta_conf_nome: Optional[str] = None,
    ):
        """Regista a conferência no Diário (YYYY-MM-DD.md) com link para o MOC e lista das palestras do dia."""
        if not data_leitura:
            data_leitura = datetime.date.today().isoformat()

        caminho_diario = self.vault_path / f"{data_leitura}.md"
        canal_id = dados_video.get("canal_id")
        canal_str = f"{dados_video.get('canal')} (ID: {canal_id})" if canal_id else dados_video.get("canal")
        dia_rotulo = agenda.dia_rotulo or f"Dia {agenda.dia or 1}"
        pasta_ref = pasta_conf_nome or limpar_nome_ficheiro(agenda.nome_conferencia)
        descricao_curta = (dados_video.get("descricao") or "").strip()[:800]

        bloco_novo = (
            "===========================\n"
            f"# {moc_wikilink} — {dia_rotulo}\n"
            "=== METADADOS DA CONFERÊNCIA ===\n"
            f"Conferência: {moc_wikilink} ({dia_rotulo})\n"
            f"Canal: {canal_str}\n"
            f"Data da Sessão: {agenda.data_sessao or dados_video.get('data')}\n"
            f"Data de Leitura: {data_leitura}\n"
            f"Palestras Integradas: {total_palestras} notas atómicas na subpasta `{pasta_ref}/`\n"
            f"Link da Transmissão: {dados_video.get('url')}\n\n"
            "--- Descrição ---\n"
            f"{descricao_curta}...\n"
        )

        if caminho_diario.exists():
            conteudo = caminho_diario.read_text(encoding="utf-8")
            if f"# {moc_wikilink} — {dia_rotulo}" in conteudo:
                return

            novo_conteudo = self._inserir_antes_resenha(conteudo, bloco_novo)
            if novo_conteudo is not None:
                caminho_diario.write_text(novo_conteudo, encoding="utf-8")
                logger.info(
                    f"    ✓ Diário {data_leitura}.md atualizado com a conferência {moc_wikilink} ({dia_rotulo}) antes da resenha.\n"
                )
                return

            novo_conteudo = conteudo.rstrip() + f"\n\n{bloco_novo}\n"
            caminho_diario.write_text(novo_conteudo, encoding="utf-8")
            logger.info(
                f"    ✓ Diário {data_leitura}.md atualizado com a conferência {moc_wikilink} ({dia_rotulo}).\n"
            )
        else:
            caminho_diario.write_text(bloco_novo + "\n", encoding="utf-8")
            logger.info(
                f"    ✓ Diário {data_leitura}.md criado com a conferência {moc_wikilink} ({dia_rotulo}).\n"
            )