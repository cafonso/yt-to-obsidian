from __future__ import annotations

import re
from typing import TYPE_CHECKING, Iterable, List

import config
from models import ArtefactoIA, ObraCitada, PessoaMencionada
from utils import eh_nome_valido_pessoa, eh_organizacao
from vault.core import (
    _escapar_yaml_str,
    _sanitizar_blockquote,
    _yaml_lista,
    limpar_nome_ficheiro,
)

if TYPE_CHECKING:
    from vault.core import ObsidianVaultWriter


def _extrair_itens_lista_yaml(frontmatter_texto: str, chave: str) -> List[str]:
    """Extrai valores de uma lista YAML simples (`chave:` ou `chave: []`) no frontmatter."""
    padrao_vazia = re.compile(rf"(?m)^{re.escape(chave)}\s*:\s*\[\s*\]\s*$")
    if padrao_vazia.search(frontmatter_texto):
        return []

    padrao_bloco = re.compile(
        rf"(?ms)^{re.escape(chave)}\s*:\s*\n((?:[ \t]+-[ \t]+.*\n?)*)"
    )
    match = padrao_bloco.search(frontmatter_texto)
    if not match:
        return []

    itens: List[str] = []
    for linha in match.group(1).splitlines():
        m_item = re.match(r"^[ \t]+-[ \t]+(.+?)\s*$", linha)
        if not m_item:
            continue
        val = m_item.group(1).strip()
        if len(val) >= 2 and ((val[0] == val[-1] == '"') or (val[0] == val[-1] == "'")):
            val = val[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        if val:
            itens.append(val)
    return itens


def _fundir_lista_yaml_no_frontmatter(
    conteudo: str,
    chave: str,
    novos_itens: Iterable[str],
) -> str:
    """Funde `novos_itens` numa lista YAML existente dentro do frontmatter, preservando o resto."""
    itens_limpos_novos = [i for i in novos_itens if i and i.strip()]
    if not itens_limpos_novos:
        return conteudo

    match_fm = re.match(r"^---\n([\s\S]*?)\n---(?:\n|$)", conteudo)
    if not match_fm:
        return conteudo

    fm_antigo = match_fm.group(1)
    existentes = _extrair_itens_lista_yaml(fm_antigo, chave)
    combinados = list(dict.fromkeys([*existentes, *itens_limpos_novos]))
    if combinados == existentes:
        return conteudo

    novo_bloco = _yaml_lista(chave, combinados).rstrip("\n")

    padrao_vazia = re.compile(rf"(?m)^{re.escape(chave)}\s*:\s*\[\s*\]\s*$")
    if padrao_vazia.search(fm_antigo):
        fm_novo = padrao_vazia.sub(lambda _m: novo_bloco, fm_antigo, count=1)
    else:
        padrao_bloco = re.compile(
            rf"(?ms)^{re.escape(chave)}\s*:\s*\n(?:[ \t]+-[ \t]+.*\n?)*"
        )
        if padrao_bloco.search(fm_antigo):
            fm_novo = padrao_bloco.sub(lambda _m: novo_bloco + "\n", fm_antigo, count=1)
        else:
            fm_novo = fm_antigo.rstrip("\n") + "\n" + novo_bloco

    inicio_resto = match_fm.end()
    return f"---\n{fm_novo}\n---" + (
        "\n" + conteudo[inicio_resto:].lstrip("\n") if conteudo[inicio_resto:] else ""
    )


class EntidadesWriter:
    """Responsável pela criação e atualização das notas atómicas de entidades no cofre."""

    def __init__(self, core: ObsidianVaultWriter):
        self.core = core

    def ligar_fabricante(self, fabricante: str, artefacto_nome: str, video_link: str) -> None:
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

    def salvar_ou_atualizar_pessoa(
        self,
        pessoa: PessoaMencionada,
        video_link: str,
        obras: List[str],
        aliases: List[str] | None = None,
    ) -> None:
        """Cria ou atualiza a nota de uma pessoa com merge seguro e escrita atómica."""
        if not pessoa or not pessoa.nome or not eh_nome_valido_pessoa(pessoa.nome):
            return

        nome_ficheiro = f"{limpar_nome_ficheiro(pessoa.nome)}.md"
        caminho = self.core.pasta_pessoas / nome_ficheiro
        obras_links = [f"[[{limpar_nome_ficheiro(o)}]]" for o in (obras or []) if o and o.strip()]
        aliases_limpos = [a.strip() for a in (aliases or []) if a and a.strip()]

        if not caminho.exists():
            bio = _sanitizar_blockquote(pessoa.papel_ou_bio) or ">"
            aliases_yaml = _yaml_lista("aliases", aliases_limpos)
            obras_yaml = _yaml_lista("obras", obras_links)
            conteudo = (
                "---\n"
                "tipo: pessoa\n"
                "tags:\n"
                "  - pessoa\n"
                f"{aliases_yaml}"
                f"{obras_yaml}"
                "---\n"
                f"# {pessoa.nome}\n\n"
                f"{bio}\n\n"
                "### 📚 Obras Relacionadas:\n"
            )
            for obra_link in obras_links:
                conteudo += f"- {obra_link}\n"

            conteudo += f"\n### 📹 Mencionada nos Vídeos:\n- {video_link}\n"
            self.core._escrever_atomico(caminho, conteudo)
            return

        conteudo_atual = caminho.read_text(encoding="utf-8")
        conteudo_atual = _fundir_lista_yaml_no_frontmatter(conteudo_atual, "aliases", aliases_limpos)
        conteudo_atual = _fundir_lista_yaml_no_frontmatter(conteudo_atual, "obras", obras_links)

        if video_link:
            conteudo_atual = self.core._adicionar_link_se_nao_existir(
                conteudo_atual, "### 📹 Mencionada nos Vídeos:", video_link
            )
        for obra_link in obras_links:
            conteudo_atual = self.core._adicionar_link_se_nao_existir(
                conteudo_atual, "### 📚 Obras Relacionadas:", obra_link
            )

        self.core._escrever_atomico(caminho, conteudo_atual)

    def salvar_ou_atualizar_organizacao(
        self,
        nome: str,
        video_link: str,
        artefactos_relacionados: List[str] | None = None,
        aliases: List[str] | None = None,
    ) -> None:
        """Cria ou atualiza a nota de uma organização com merge seguro e escrita atómica."""
        if not nome or not nome.strip():
            return

        nome_limpo = nome.strip()
        nome_ficheiro = f"{limpar_nome_ficheiro(nome_limpo)}.md"
        caminho = self.core.pasta_organizacoes / nome_ficheiro
        artefactos_relacionados = [
            a.strip() for a in (artefactos_relacionados or []) if a and a.strip()
        ]
        artefactos_links = [
            f"[[{limpar_nome_ficheiro(a)}]]" for a in artefactos_relacionados
        ]
        aliases_limpos = [a.strip() for a in (aliases or []) if a and a.strip()]

        if not caminho.exists():
            aliases_yaml = _yaml_lista("aliases", aliases_limpos)
            art_yaml = _yaml_lista("artefactos", artefactos_links)
            conteudo = (
                "---\n"
                "tipo: organizacao\n"
                "tags:\n"
                "  - organizacao\n"
                f"{aliases_yaml}"
                f"{art_yaml}"
                "---\n"
                f"# {nome_limpo}\n\n"
                "### 🧩 Artefactos:\n"
            )
            if artefactos_links:
                for link_art in artefactos_links:
                    conteudo += f"- {link_art}\n"
            else:
                conteudo += "_Nenhum artefacto associado ainda._\n"

            conteudo += f"\n### 📹 Mencionada nos Vídeos:\n- {video_link}\n"
            self.core._escrever_atomico(caminho, conteudo)
            return

        conteudo_atual = caminho.read_text(encoding="utf-8")
        conteudo_atual = _fundir_lista_yaml_no_frontmatter(conteudo_atual, "aliases", aliases_limpos)
        conteudo_atual = _fundir_lista_yaml_no_frontmatter(
            conteudo_atual, "artefactos", artefactos_links
        )

        if video_link:
            conteudo_atual = self.core._adicionar_link_se_nao_existir(
                conteudo_atual, "### 📹 Mencionada nos Vídeos:", video_link
            )
        for link_art in artefactos_links:
            conteudo_atual = self.core._adicionar_link_se_nao_existir(
                conteudo_atual, "### 🧩 Artefactos:", link_art
            )

        self.core._escrever_atomico(caminho, conteudo_atual)

    def salvar_ou_atualizar_obra(self, obra: ObraCitada, video_link: str) -> None:
        """Cria ou atualiza a nota de um livro ou artigo com merge seguro e escrita atómica."""
        if not obra or not obra.titulo or not obra.titulo.strip():
            return

        nome_ficheiro = f"{limpar_nome_ficheiro(obra.titulo)}.md"
        caminho = self.core.pasta_livros / nome_ficheiro

        autores_limpos = [a.strip() for a in (obra.autores or []) if a and a.strip()]
        autores_links = [f"[[{limpar_nome_ficheiro(a)}]]" for a in autores_limpos]
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
            self.core._escrever_atomico(caminho, conteudo)
        else:
            conteudo_atual = caminho.read_text(encoding="utf-8")
            conteudo_atual = _fundir_lista_yaml_no_frontmatter(
                conteudo_atual, "autores", autores_links
            )
            if video_link:
                conteudo_atual = self.core._adicionar_link_se_nao_existir(
                    conteudo_atual, "### 📹 Mencionado nos Vídeos:", video_link
                )
            self.core._escrever_atomico(caminho, conteudo_atual)

        for autor in autores_limpos:
            autor_pessoa = PessoaMencionada(
                nome=autor,
                papel_ou_bio=f"Autor(a) da obra [[{limpar_nome_ficheiro(obra.titulo)}]].",
            )
            self.salvar_ou_atualizar_pessoa(autor_pessoa, video_link, [obra.titulo])

    def salvar_ou_atualizar_tema(self, tema: str, video_link: str) -> None:
        """Cria ou atualiza uma nota de tema com os vídeos associados e escrita atómica."""
        if not tema or not tema.strip():
            return

        nome_ficheiro = f"{limpar_nome_ficheiro(tema)}.md"
        caminho = self.core.pasta_temas / nome_ficheiro

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
            self.core._escrever_atomico(caminho, conteudo)
        else:
            conteudo_atual = caminho.read_text(encoding="utf-8")
            if video_link:
                conteudo_atual = self.core._adicionar_link_se_nao_existir(
                    conteudo_atual, "### 📹 Vídeos sobre este tema:", video_link
                )
            self.core._escrever_atomico(caminho, conteudo_atual)

    def salvar_ou_atualizar_artefacto(self, artefacto: ArtefactoIA, video_link: str) -> None:
        """Cria ou atualiza a nota de um artefacto com merge seguro e escrita atómica."""
        if not artefacto or not artefacto.nome or not artefacto.nome.strip():
            return

        nome_ficheiro = f"{limpar_nome_ficheiro(artefacto.nome)}.md"
        caminho = self.core.pasta_artefactos / nome_ficheiro

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
            self.core._escrever_atomico(caminho, conteudo)
        else:
            conteudo_atual = caminho.read_text(encoding="utf-8")
            if video_link:
                conteudo_atual = self.core._adicionar_link_se_nao_existir(
                    conteudo_atual, "### 📹 Mencionada nos Vídeos:", video_link
                )
            self.core._escrever_atomico(caminho, conteudo_atual)

        if fabricante:
            self.ligar_fabricante(fabricante, artefacto.nome, video_link)