from __future__ import annotations

import datetime
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from extrator import extrair_id_youtube
from models import AnaliseVideo, VideoCitado
from utils import eh_nome_valido_pessoa, eh_organizacao
from vault.core import (
    _escapar_yaml_str,
    _yaml_lista,
    limpar_nome_ficheiro,
    validar_recursos_externos,
)

if TYPE_CHECKING:
    from vault.core import ObsidianVaultWriter

logger = logging.getLogger("yt_obsidian")


class VideosWriter:
    """Responsável pela criação de notas de vídeo individuais e resolução de vídeos citados."""

    def __init__(self, core: ObsidianVaultWriter):
        self.core = core

    def resolver_video_citado(
        self,
        video: VideoCitado,
        historico: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, Optional[str]]:
        hist = historico or {}
        raw_ref = (video.url_ou_id or "").strip()
        vid_id = extrair_id_youtube(raw_ref) if raw_ref else None

        if not vid_id and raw_ref:
            match_youtu_be = re.search(r"youtu\.be/([A-Za-z0-9_-]+)", raw_ref)
            match_watch = re.search(r"[?&]v=([A-Za-z0-9_-]+)", raw_ref)
            if match_youtu_be:
                vid_id = match_youtu_be.group(1)
            elif match_watch:
                vid_id = match_watch.group(1)
            elif re.fullmatch(r"[A-Za-z0-9_-]{6,20}", raw_ref):
                vid_id = raw_ref

        if vid_id and vid_id in hist:
            entrada = hist[vid_id]
            nota_caminho = entrada.get("nota") if isinstance(entrada, dict) else None
            if nota_caminho:
                stem = Path(nota_caminho).stem
                return f"[[{stem}]]", stem

        titulo = (video.titulo_ou_assunto or "").strip()
        if raw_ref.startswith(("http://", "https://")):
            return f"[{titulo}]({raw_ref})", None
        return titulo, None

    def renderizar_seccao_videos_citados(
        self,
        videos_citados: List[VideoCitado],
        historico: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, List[str]]:
        """Devolve (bloco_markdown, links_wikilink_resolvidos)."""
        if not videos_citados:
            return "", []

        linhas = ["\n---\n\n## 🎬 Vídeos Citados / Referenciados\n"]
        links_resolvidos: List[str] = []

        for v in videos_citados:
            rotulo, stem_existente = self.core._resolver_video_citado(v, historico)
            if stem_existente:
                links_resolvidos.append(f"[[{stem_existente}]]")

            canal_raw = (v.canal_ou_orador or "").strip()
            if canal_raw and eh_nome_valido_pessoa(canal_raw):
                canal_fmt = f" por [[{limpar_nome_ficheiro(canal_raw)}]]"
            elif canal_raw and eh_organizacao(canal_raw):
                canal_fmt = f" por [[{limpar_nome_ficheiro(canal_raw)}]]"
            elif canal_raw:
                canal_fmt = f" ({canal_raw})"
            else:
                canal_fmt = ""

            contexto_fmt = f" — _{v.contexto.strip()}_" if (v.contexto and v.contexto.strip()) else ""
            linhas.append(f"- **{rotulo}**{canal_fmt}{contexto_fmt}\n")

        return "".join(linhas), links_resolvidos

    def salvar_video(
        self,
        dados_video: Dict[str, Any],
        analise: AnaliseVideo,
        data_leitura: str | None = None,
    ) -> Path:
        """Cria a nota principal do vídeo e dispara a criação/atualização de todas as entidades conectadas."""
        if not data_leitura:
            data_leitura = datetime.date.today().isoformat()

        nome_base = limpar_nome_ficheiro(analise.titulo_sugerido or dados_video.get("titulo", "Video"))
        nome_ficheiro = f"{nome_base}.md"
        caminho_video = self.core.pasta_videos / nome_ficheiro
        video_wikilink = f"[[{caminho_video.stem}]]"

        pessoas_validas, organizacoes_todas = self.core._extrair_entidades_base(
            analise.pessoas, analise.organizacoes
        )

        pessoas_links = [f"[[{limpar_nome_ficheiro(p.nome)}]]" for p in pessoas_validas]
        obras_links = [f"[[{limpar_nome_ficheiro(o.titulo)}]]" for o in analise.obras]
        temas_links = [f"[[{limpar_nome_ficheiro(t)}]]" for t in analise.temas]
        artefactos_links = [f"[[{limpar_nome_ficheiro(a.nome)}]]" for a in analise.artefactos]
        organizacoes_links = [f"[[{limpar_nome_ficheiro(o)}]]" for o in organizacoes_todas]

        videos_citados = getattr(analise, "videos_citados", []) or []
        historico_atual = self.core._carregar_historico_vault()
        bloco_videos_citados, videos_citados_links = self.core._renderizar_seccao_videos_citados(
            videos_citados,
            historico_atual,
        )
       
        conteudo_existente: Optional[str] = None
        data_leitura_final = data_leitura
        if caminho_video.exists():
            conteudo_existente = caminho_video.read_text(encoding="utf-8")
            match = re.search(
                r'^data_leitura:\s*"?([0-9]{4}-[0-9]{2}-[0-9]{2})"?',
                conteudo_existente,
                re.MULTILINE,
            )
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
            + _yaml_lista("videos_citados", videos_citados_links)
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

        if bloco_videos_citados:
            nota += bloco_videos_citados

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
            if self.core.validar_links:
                logger.info("    🌐 A verificar disponibilidade dos links externos...")
            recursos_verificados = validar_recursos_externos(
                analise.recursos_e_links, ativar=self.core.validar_links
            )
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
            
        if conteudo_existente is not None:
            from vault.core import _extrair_seccoes_manuais
            from vault.entidades import _extrair_itens_lista_yaml, _fundir_lista_yaml_no_frontmatter

            match_fm = re.match(r"^---\n([\s\S]*?)\n---", conteudo_existente)
            if match_fm:
                fm_antigo = match_fm.group(1)
                for chave in ("tags", "temas", "pessoas", "obras", "videos_citados", "artefactos", "organizacoes"):
                    antigos = _extrair_itens_lista_yaml(fm_antigo, chave)
                    if antigos:
                        nota = _fundir_lista_yaml_no_frontmatter(nota, chave, antigos)

            seccoes_manuais = _extrair_seccoes_manuais(conteudo_existente)
            if seccoes_manuais:
                nota = nota.rstrip() + "\n\n---\n\n" + "\n\n---\n\n".join(seccoes_manuais) + "\n"

        self.core._escrever_atomico(caminho_video, nota)
        self.core.atualizar_nota_diaria(dados_video, video_wikilink, analise, data_leitura_final)

        self.core._persistir_entidades_relacionadas(
            nota_wikilink=video_wikilink,
            pessoas_validas=pessoas_validas,
            obras=analise.obras,
            temas=analise.temas,
            organizacoes_todas=organizacoes_todas,
            artefactos=analise.artefactos,
            videos_citados=videos_citados,
        )

        return caminho_video