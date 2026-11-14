import os
import re
import datetime
from pathlib import Path
from typing import Dict, Any, List, Set
from models import AnaliseVideo, ObraCitada, PessoaMencionada, ArtefactoIA
import config

# ---------------------------------------------------------------------------
# Heurísticas para distinguir Pessoas de Organizações
# ---------------------------------------------------------------------------

# Palavras que, se aparecerem no nome, indicam quase certamente uma organização.
PALAVRAS_ORGANIZACAO = {
    "inc", "corp", "corporation", "labs", "lab", "university", "universidade",
    "institute", "instituto", "foundation", "fundação", "foundation",
    "research", "research", "school", "escola", "college", "center", "centre",
    "centro", "group", "grupo", "technologies", "technology", "technologies",
    "systems", "sistemas", "solutions", "solucoes", "solutions",
    "ai", "ia", "llc", "ltd", "gmbh", "sa", "plc", "holdings",
    "ventures", "capital", "partners", "studio", "studios",
    "media", "network", "networks", "cloud", "compute", "semiconductor",
}

# Organizações conhecidas (comparação case-insensitive, também por prefixo).
# Ajuda a apanhar nomes compostos como "Google DeepMind" ou "Hugging Face".
ORGANIZACOES_CONHECIDAS = {
    "openai", "anthropic", "google", "google deepmind", "deepmind",
    "microsoft", "meta", "meta ai", "apple", "nvidia", "amd", "intel",
    "aws", "amazon", "amazon web services", "azure", "google cloud",
    "hugging face", "huggingface", "mistral", "mistral ai", "cohere",
    "stability ai", "midjourney", "runway", "perplexity", "xai", "x.ai",
    "tesla", "spacex", "ibm", "oracle", "salesforce", "databricks",
    "snowflake", "scale ai", "anyscale", "together ai", "replicate",
    "vercel", "supabase", "resend", "github", "gitlab", "atlassian",
    "mit", "stanford", "berkeley", "harvard", "oxford", "cambridge",
    "cmu", "carnegie mellon", "eth zurich", "epfl", "helmholtz",
    "deeplearning.ai", "coursera", "udacity", "kaggle",
    "latent space", "ai engineer", "canonical", "ubuntu", "linux foundation",
}

def eh_nome_valido_pessoa(nome: str) -> bool:
    """Valida se o nome parece um nome de pessoa real (Nome + Apelido) e não uma organização ou nome solto."""
    nome_limpo = nome.strip()
    if not nome_limpo:
        return False
    partes = nome_limpo.split()
    if len(partes) < 2:
        # Rejeita nomes próprios isolados como 'Sarah', 'Tim', 'Zach'
        return False
    return not eh_organizacao(nome_limpo)

def eh_organizacao(nome: str) -> bool:
    """Heurística: determina se um nome corresponde a uma organização."""
    nome_lower = nome.strip().lower()
    if not nome_lower:
        return False

    # 1. Match exato contra a lista de organizações conhecidas
    if nome_lower in ORGANIZACOES_CONHECIDAS:
        return True

    # 2. Match por prefixo (ex: "google deepmind research" -> começa por "google")
    for org in ORGANIZACOES_CONHECIDAS:
        if nome_lower == org or nome_lower.startswith(org + " "):
            return True

    # 3. Presença de palavras-chave típicas de organizações
    palavras = set(re.split(r"[\s\-_.,]+", nome_lower))
    if palavras & PALAVRAS_ORGANIZACAO:
        return True

    return False


def limpar_nome_ficheiro(nome: str) -> str:
    """Remove caracteres inválidos para nomes de ficheiros no Windows e Obsidian."""
    # Substitui caracteres proibidos no Windows: < > : " / \ | ? *
    nome_limpo = re.sub(r'[<>:"/\\|?*]', '', nome)
    # Remove múltiplos espaços
    nome_limpo = re.sub(r'\s+', ' ', nome_limpo).strip()
    return nome_limpo[:120]


class ObsidianVaultWriter:
    def __init__(self, vault_path: str = config.DEFAULT_VAULT_PATH):
        self.vault_path = Path(vault_path)
        self.pasta_videos = self.vault_path / config.PASTA_VIDEOS
        self.pasta_pessoas = self.vault_path / config.PASTA_PESSOAS
        self.pasta_livros = self.vault_path / config.PASTA_LIVROS
        self.pasta_temas = self.vault_path / config.PASTA_TEMAS
        self.pasta_artefactos = self.vault_path / config.PASTA_ARTEFACTOS
        self.pasta_organizacoes = self.vault_path / config.PASTA_ORGANIZACOES

        # Garante que as subpastas existem no Vault
        for pasta in [
            self.pasta_videos, self.pasta_pessoas, self.pasta_livros,
            self.pasta_temas, self.pasta_artefactos, self.pasta_organizacoes,
        ]:
            pasta.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _adicionar_link_se_nao_existir(self, conteudo: str, seccao_titulo: str, novo_link: str) -> str:
        """Adiciona um item a uma secção do markdown se ele ainda não estiver presente."""
        if novo_link in conteudo:
            return conteudo

        if seccao_titulo in conteudo:
            padrao = re.escape(seccao_titulo) + r"\n+"
            substituicao = f"{seccao_titulo}\n- {novo_link}\n"
            novo_conteudo, count = re.subn(padrao, substituicao, conteudo, count=1)
            if count > 0:
                return novo_conteudo

        # Se a secção não existir no ficheiro, acrescenta no fim
        return conteudo.rstrip() + f"\n\n{seccao_titulo}\n- {novo_link}\n"

    def _ligar_fabricante(self, fabricante: str, artefacto_nome: str, video_link: str):
        """
        Cria a nota adequada para o fabricante de um artefacto:
          - Se for organização -> nota em Organizações/
          - Se for pessoa     -> nota em Pessoas/
          - Caso contrário    -> não cria nada (link fica órfão, resolvido quando o user criar a nota)
        """
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
            conteudo = f"""---
tipo: pessoa
tags:
  - pessoa
aliases: []
---
# {pessoa.nome}

> {pessoa.papel_ou_bio}

### 📚 Obras Relacionadas:
"""
            for obra in obras:
                conteudo += f"- [[{limpar_nome_ficheiro(obra)}]]\n"

            conteudo += f"""
### 📹 Mencionada nos Vídeos:
- {video_link}
"""
            caminho.write_text(conteudo, encoding="utf-8")
        else:
            conteudo_atual = caminho.read_text(encoding="utf-8")
            conteudo_atual = self._adicionar_link_se_nao_existir(conteudo_atual, "### 📹 Mencionada nos Vídeos:", video_link)
            for obra in obras:
                conteudo_atual = self._adicionar_link_se_nao_existir(conteudo_atual, "### 📚 Obras Relacionadas:", f"[[{limpar_nome_ficheiro(obra)}]]")
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
            conteudo = f"""---
tipo: organizacao
tags:
  - organizacao
aliases: []
---
# {nome}

### 🧩 Artefactos:
"""
            if artefactos_relacionados:
                for a in artefactos_relacionados:
                    conteudo += f"- [[{limpar_nome_ficheiro(a)}]]\n"
            else:
                conteudo += "_Nenhum artefacto associado ainda._\n"

            conteudo += f"""
### 📹 Mencionada nos Vídeos:
- {video_link}
"""
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

        autores_links = [f"[[{limpar_nome_ficheiro(a)}]]" for a in obra.autores]
        autores_str = ", ".join(autores_links) if autores_links else "Não especificado"

        if not caminho.exists():
            contexto_str = f"> {obra.contexto}\n\n" if obra.contexto else ""
            conteudo = f"""---
tipo: {obra.tipo.lower()}
autores: {autores_links}
tags:
  - {obra.tipo.lower()}
---
# {obra.titulo}

**Tipo:** {obra.tipo}  
**Autor(es):** {autores_str}

{contexto_str}### 📹 Mencionado nos Vídeos:
- {video_link}
"""
            caminho.write_text(conteudo, encoding="utf-8")
        else:
            conteudo_atual = caminho.read_text(encoding="utf-8")
            conteudo_atual = self._adicionar_link_se_nao_existir(conteudo_atual, "### 📹 Mencionado nos Vídeos:", video_link)
            caminho.write_text(conteudo_atual, encoding="utf-8")

        # Garante que cada autor tem a sua própria nota e está conectado à obra
        for autor in obra.autores:
            autor_pessoa = PessoaMencionada(
                nome=autor,
                papel_ou_bio=f"Autor(a) da obra [[{limpar_nome_ficheiro(obra.titulo)}]]."
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
            conteudo = f"""---
tipo: tema
tags:
  - tema
---
# {tema}

### 📹 Vídeos sobre este tema:
- {video_link}
"""
            caminho.write_text(conteudo, encoding="utf-8")
        else:
            conteudo_atual = caminho.read_text(encoding="utf-8")
            conteudo_atual = self._adicionar_link_se_nao_existir(conteudo_atual, "### 📹 Vídeos sobre este tema:", video_link)
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
            subtipo = "modelo"  # fallback defensivo

        fabricante = (artefacto.fabricante_ou_autor or "").strip() or None
        fabricante_link = f"[[{limpar_nome_ficheiro(fabricante)}]]" if fabricante else "null"

        if not caminho.exists():
            descricao_str = f"> {artefacto.descricao}\n\n" if artefacto.descricao else ""
            conteudo = f"""---
tipo: artefacto
subtipo: {subtipo}
fabricante: {fabricante_link}
tags:
  - artefacto/{subtipo}
---
# {artefacto.nome}

**Subtipo:** {subtipo}  
**Fabricante/Autor:** {fabricante_link if fabricante else "Desconhecido"}

{descricao_str}### 📹 Mencionado nos Vídeos:
- {video_link}
"""
            caminho.write_text(conteudo, encoding="utf-8")
        else:
            conteudo_atual = caminho.read_text(encoding="utf-8")
            conteudo_atual = self._adicionar_link_se_nao_existir(
                conteudo_atual, "### 📹 Mencionado nos Vídeos:", video_link
            )
            caminho.write_text(conteudo_atual, encoding="utf-8")

        # Ligar o fabricante (organização ou pessoa)
        if fabricante:
            self._ligar_fabricante(fabricante, artefacto.nome, video_link)

    # ------------------------------------------------------------------
    # Nota diária
    # ------------------------------------------------------------------

    def formatar_entrada_diario(self, dados_video: Dict[str, Any], video_wikilink: str, data_leitura: str) -> str:
        """Gera o bloco de entrada no diário exatamente no formato personalizado do utilizador."""
        canal_id = dados_video.get("canal_id")
        canal_str = f"{dados_video.get('canal')} (ID: {canal_id})" if canal_id else dados_video.get('canal')
        descricao = dados_video.get('descricao', '').strip()

        return f"""===========================
# {video_wikilink}
=== METADADOS DO VÍDEO ===
Título: {dados_video.get('titulo')}
Canal: {canal_str}
Data de Publicação: {dados_video.get('data')}
Data de Leitura: {data_leitura}
Link: {dados_video.get('url')}

--- Descrição ---
{descricao}
"""

    def atualizar_nota_diaria(self, dados_video: Dict[str, Any], video_wikilink: str, analise: AnaliseVideo, data_leitura: str = None):
        """Regista o bloco do vídeo no diário (YYYY-MM-DD.md) usando a data de leitura."""
        if not data_leitura:
            data_leitura = datetime.date.today().isoformat()

        caminho_diario = self.vault_path / f"{data_leitura}.md"
        bloco_novo = self.formatar_entrada_diario(dados_video, video_wikilink, data_leitura)

        if caminho_diario.exists():
            conteudo = caminho_diario.read_text(encoding="utf-8")
            if video_wikilink in conteudo:
                # Já está registado no diário
                return

            # Se houver secção # Resenha do dia, insere imediatamente antes
            if "# Resenha do dia" in conteudo or "# Resenha do Dia" in conteudo:
                padrao = r"(#\s+Resenha do [Dd]ia)"
                substituicao = f"{bloco_novo}\n\\1"
                novo_conteudo, count = re.subn(padrao, substituicao, conteudo, count=1)
                if count > 0:
                    caminho_diario.write_text(novo_conteudo, encoding="utf-8")
                    print(f"    ✓ Diário {data_leitura}.md atualizado com o bloco de metadados antes da resenha.")
                    return

            # Caso contrário, acrescenta no fim do diário
            novo_conteudo = conteudo.rstrip() + f"\n\n{bloco_novo}\n"
            caminho_diario.write_text(novo_conteudo, encoding="utf-8")
            print(f"    ✓ Diário {data_leitura}.md atualizado com o novo bloco de metadados.")
        else:
            caminho_diario.write_text(bloco_novo + "\n", encoding="utf-8")
            print(f"    ✓ Diário {data_leitura}.md criado com o bloco de metadados.")

    # ------------------------------------------------------------------
    # Nota principal do vídeo
    # ------------------------------------------------------------------

    def salvar_video(self, dados_video: Dict[str, Any], analise: AnaliseVideo, data_leitura: str = None) -> Path:
        """Cria a nota principal do vídeo e dispara a criação/atualização de todas as entidades conectadas."""
        if not data_leitura:
            data_leitura = datetime.date.today().isoformat()

        # Usa o título original limpo diretamente para o nome da nota (sem prefixar a data)
        nome_base = limpar_nome_ficheiro(analise.titulo_sugerido or dados_video.get("titulo", "Video"))
        nome_ficheiro = f"{nome_base}.md"
        caminho_video = self.pasta_videos / nome_ficheiro

        video_wikilink = f"[[{caminho_video.stem}]]"

        # Separa pessoas válidas de organizações que o Gemini possa ter metido no campo errado
        pessoas_validas = [p for p in analise.pessoas if eh_nome_valido_pessoa(p.nome)]
        organizacoes_extra = {p.nome.strip() for p in analise.pessoas if eh_organizacao(p.nome)}
        organizacoes_todas = list({*[o.strip() for o in analise.organizacoes if o and o.strip()], *organizacoes_extra})

        # Constrói listas de links para o frontmatter
        pessoas_links = [f"[[{limpar_nome_ficheiro(p.nome)}]]" for p in pessoas_validas]
        obras_links = [f"[[{limpar_nome_ficheiro(o.titulo)}]]" for o in analise.obras]
        temas_links = [f"[[{limpar_nome_ficheiro(t)}]]" for t in analise.temas]
        artefactos_links = [f"[[{limpar_nome_ficheiro(a.nome)}]]" for a in analise.artefactos]
        organizacoes_links = [f"[[{limpar_nome_ficheiro(o)}]]" for o in organizacoes_todas]

        # Preserva o data_leitura original se a nota já existir
        data_leitura_final = data_leitura
        if caminho_video.exists():
            conteudo_existente = caminho_video.read_text(encoding="utf-8")
            match = re.search(r'^data_leitura:\s*"?([0-9]{4}-[0-9]{2}-[0-9]{2})"?', conteudo_existente, re.MULTILINE)
            if match:
                data_leitura_final = match.group(1)

        nota = f"""---
tipo: video
titulo: "{dados_video.get('titulo')}"
canal: "{dados_video.get('canal')}"
data_publicacao: "{dados_video.get('data')}"
data_leitura: "{data_leitura_final}"
url: "{dados_video.get('url')}"
tags:
  - video/youtube
temas: {temas_links}
pessoas: {pessoas_links}
obras: {obras_links}
artefactos: {artefactos_links}
organizacoes: {organizacoes_links}
---
# {analise.titulo_sugerido}

> 📺 **Canal:** [{dados_video.get('canal')}]({dados_video.get('canal_url', '')})  
> 📅 **Data:** {dados_video.get('data')}  
> 🔗 **Ver no YouTube:** [{dados_video.get('url')}]({dados_video.get('url')})

---

## 📝 Resumo Executivo
{analise.resumo_executivo}

---

## 💡 Principais Takeaways
"""
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
                autores_fmt = ", ".join(f"[[{limpar_nome_ficheiro(a)}]]" for a in o.autores) if o.autores else "Autor desconhecido"
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
            nota += "\n---\n\n## 🔗 Links & Recursos Mencionados\n"
            for recurso in analise.recursos_e_links:
                nota += f"- {recurso}\n"

        if analise.capitulos:
            nota += "\n---\n\n## ⏱️ Capítulos / Linha Temporal\n"
            for cap in analise.capitulos:
                nota += f"- {cap}\n"

        nota += "\n---\n\n## 🏷️ Temas Abordados\n"
        for t in analise.temas:
            nota += f"- [[{limpar_nome_ficheiro(t)}]]\n"

        # Grava a nota do vídeo
        caminho_video.write_text(nota, encoding="utf-8")

        # Regista automaticamente a chamada deste vídeo na Nota Diária (YYYY-MM-DD.md)
        self.atualizar_nota_diaria(dados_video, video_wikilink, analise, data_leitura_final)

        # ------------------------------------------------------------------
        # Propagação para entidades relacionadas
        # ------------------------------------------------------------------

        # Pessoas (filtra as que na verdade são organizações)
        for p in pessoas_validas:
            obras_desta_pessoa = [o.titulo for o in analise.obras if p.nome in o.autores]
            self.salvar_ou_atualizar_pessoa(p, video_wikilink, obras_desta_pessoa)

        # Obras
        for o in analise.obras:
            self.salvar_ou_atualizar_obra(o, video_wikilink)

        # Temas
        for t in analise.temas:
            self.salvar_ou_atualizar_tema(t, video_wikilink)

        # Organizações (inclui as que foram resgatadas do campo pessoas)
        for org in organizacoes_todas:
            artefactos_da_org = [
                a.nome for a in analise.artefactos
                if a.fabricante_ou_autor and a.fabricante_ou_autor.strip().lower() == org.lower()
            ]
            self.salvar_ou_atualizar_organizacao(org, video_wikilink, artefactos_da_org)

        # Artefactos (e ligação ao fabricante)
        for a in analise.artefactos:
            self.salvar_ou_atualizar_artefacto(a, video_wikilink)

        return caminho_video