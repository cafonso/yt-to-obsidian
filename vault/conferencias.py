from __future__ import annotations

import datetime
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from analyzer import _desduplicar_videos_citados
from models import AgendaScout, PalestraAnalise, SessaoScout
from vault.core import (
    _escapar_yaml_str,
    _yaml_lista,
    limpar_nome_ficheiro,
    validar_recursos_externos,
)

if TYPE_CHECKING:
    from vault.core import ObsidianVaultWriter

logger = logging.getLogger("yt_obsidian")


class ConferenciasWriter:
    """Responsável pela geração de palestras individuais, índices MOC e entradas diárias de conferências."""

    def __init__(self, core: ObsidianVaultWriter):
        self.core = core

    def obter_pasta_conferencia(self, nome_conferencia: str) -> Path:
        """Cria e devolve a subpasta dedicada a uma conferência dentro de Videos/."""
        pasta_conf = self.core.pasta_videos / limpar_nome_ficheiro(nome_conferencia)
        pasta_conf.mkdir(parents=True, exist_ok=True)
        return pasta_conf

    def salvar_palestra_conferencia(
        self,
        dados_video: Dict[str, Any],
        agenda: AgendaScout,
        sessao: SessaoScout,
        analise: PalestraAnalise,
        data_leitura: str | None = None,
        historico: Optional[Dict[str, Any]] = None,
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

        pessoas_validas, organizacoes_todas = self.core._extrair_entidades_base(
            analise.pessoas, analise.organizacoes
        )

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
        historico_atual = historico if historico is not None else self.core._carregar_historico_vault()
        videos_citados = _desduplicar_videos_citados(getattr(analise, "videos_citados", []) or [])
        bloco_videos_citados, videos_citados_links = self.core._renderizar_seccao_videos_citados(
            videos_citados,
            historico_atual,
        )

        conteudo_existente: Optional[str] = None
        data_leitura_final = data_leitura
        if caminho_palestra.exists():
            conteudo_existente = caminho_palestra.read_text(encoding="utf-8")
            match = re.search(
                r'^data_leitura:\s*"?([0-9]{4}-[0-9]{2}-[0-9]{2})"?',
                conteudo_existente,
                re.MULTILINE,
            )
            if match:
                data_leitura_final = match.group(1)

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
            + _yaml_lista("videos_citados", videos_citados_links)
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
            recursos_verificados = validar_recursos_externos(
                analise.recursos_e_links, ativar=self.core.validar_links
            )
            nota += "\n---\n\n## 🔗 Recursos & Links\n"
            for r in recursos_verificados:
                nota += f"- {r}\n"

        if analise.temas:
            nota += "\n---\n\n## 🏷️ Temas\n"
            for tm in analise.temas:
                nota += f"- [[{limpar_nome_ficheiro(tm)}]]\n"

        if bloco_videos_citados:
            nota += bloco_videos_citados

        if conteudo_existente is not None:
            from vault.core import _extrair_seccoes_manuais
            from vault.entidades import _extrair_itens_lista_yaml, _fundir_lista_yaml_no_frontmatter

            match_fm = re.match(r"^---\n([\s\S]*?)\n---", conteudo_existente)
            if match_fm:
                fm_antigo = match_fm.group(1)
                for chave in ("tags", "temas", "pessoas", "obras", "artefactos", "organizacoes", "videos_citados"):
                    antigos = _extrair_itens_lista_yaml(fm_antigo, chave)
                    if antigos:
                        nota = _fundir_lista_yaml_no_frontmatter(nota, chave, antigos)

            seccoes_manuais = _extrair_seccoes_manuais(conteudo_existente)
            if seccoes_manuais:
                nota = nota.rstrip() + "\n\n---\n\n" + "\n\n---\n\n".join(seccoes_manuais) + "\n"

        self.core._escrever_atomico(caminho_palestra, nota)
        

        self.core._persistir_entidades_relacionadas(
            nota_wikilink=palestra_wikilink,
            pessoas_validas=pessoas_validas,
            obras=analise.obras,
            temas=analise.temas,
            organizacoes_todas=organizacoes_todas,
            artefactos=analise.artefactos,
            videos_citados=videos_citados,
        )

        return caminho_palestra

    def salvar_ou_atualizar_moc_conferencia(
        self,
        dados_video: Dict[str, Any],
        agenda: AgendaScout,
        palestras_processadas: List[Dict[str, Any]],
        data_leitura: str | None = None,
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
            self.core._escrever_atomico(caminho_moc, conteudo_moc)
        else:
            conteudo_existente = caminho_moc.read_text(encoding="utf-8")
            padrao_dia = re.compile(rf"{re.escape(seccao_cabecalho_dia)}[\s\S]*?(?=\n## 📅|\Z)")
            if padrao_dia.search(conteudo_existente):
                novo_conteudo = padrao_dia.sub(lambda _m: tabela_dia.strip(), conteudo_existente, count=1)
            else:
                novo_conteudo = conteudo_existente.rstrip() + f"\n\n---\n\n{tabela_dia}\n"
            self.core._escrever_atomico(caminho_moc, novo_conteudo)

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
        data_leitura: str | None = None,
        pasta_conf_nome: Optional[str] = None,
    ) -> None:
        """Regista a conferência no Diário (YYYY-MM-DD.md) com link para o MOC e lista das palestras do dia."""
        if not data_leitura:
            data_leitura = datetime.date.today().isoformat()

        caminho_diario = self.core.vault_path / f"{data_leitura}.md"
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

            novo_conteudo = self.core._inserir_antes_resenha(conteudo, bloco_novo)
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