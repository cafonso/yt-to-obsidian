import os
import re
import asyncio
import datetime
from pathlib import Path
from typing import Dict, Any, List, Set, Optional
from models import AnaliseVideo, ObraCitada, PessoaMencionada, ArtefactoIA, AgendaScout, SessaoScout, PalestraAnalise
import config
from utils import eh_nome_valido_pessoa, eh_organizacao, verificar_link_ativo


def limpar_nome_ficheiro(nome: str) -> str:
    """Remove caracteres inválidos para nomes de ficheiros no Windows e Obsidian."""
    # Substitui caracteres proibidos no Windows: < > : " / \ | ? *
    nome_limpo = re.sub(r'[<>:"/\\|?*]', '', nome)
    # Remove múltiplos espaços
    nome_limpo = re.sub(r'\s+', ' ', nome_limpo).strip()
    return nome_limpo[:120]


def _verificar_url_sincrono(url: str, timeout: float = 3.5) -> bool:
    """Verifica de forma leve se um URL responde com sucesso (200-399)."""
    if not url or not url.startswith(("http://", "https://")):
        return False

    headers = {"User-Agent": "Mozilla/5.0 (Compatible; ObsidianPKMBot/1.0)"}

    # 1. Tenta pedido HEAD (mais rápido, sem descarregar conteúdo)
    try:
        req_head = urllib.request.Request(url, headers=headers, method="HEAD")
        with urllib.request.urlopen(req_head, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except Exception:
        pass

    # 2. Fallback para GET leve (alguns servidores bloqueiam HEAD)
    try:
        req_get = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req_get, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except Exception:
        return False


async def _validar_lista_recursos_async(recursos: List[str], timeout: float = 3.5) -> List[str]:
    """Verifica todos os links da lista em paralelo e sinaliza os que estiverem inativos."""
    if not recursos:
        return []

    async def processar_item(recurso: str) -> str:
        urls = re.findall(r"https?://[^\s\]\)]+", recurso)
        if not urls:
            return recurso

        # Limpa eventual pontuação final presa ao URL (ex.: ponto final ou vírgula)
        url_alvo = urls[0].rstrip(".,;:")
        ativo = await asyncio.to_thread(verificar_link_ativo, url_alvo, timeout)

        if ativo:
            return recurso
        return f"{recurso} ⚠️ *(Link possivelmente inativo ou inacessível)*"

    tarefas = [processar_item(r) for r in recursos]
    return await asyncio.gather(*tarefas)

def validar_recursos_externos(recursos: List[str], ativar: bool = True) -> List[str]:
    """Ponto de entrada síncrono para validar recursos de forma assíncrona em paralelo."""
    if not recursos or not ativar:
        return recursos
    try:
        return asyncio.run(_validar_lista_recursos_async(recursos))
    except Exception:
        # Em caso de falha inesperada no loop assíncrono, devolve os recursos originais sem quebrar o fluxo
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
            if self.validar_links:
                print("    🌐 A verificar disponibilidade dos links externos...")
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
        data_leitura: str = None
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
        # Limita tamanho se for muito longo
        if len(nome_ficheiro) > 130:
            nome_ficheiro = f"{dia_prefixo} - {sessao.ordem:02d}{orador_limpo} - {titulo_limpo[:80]}.md"

        caminho_palestra = pasta_conf / nome_ficheiro
        palestra_wikilink = f"[[{caminho_palestra.stem}]]"
        moc_conferencia_wikilink = f"[[{limpar_nome_ficheiro(agenda.nome_conferencia)}]]"

        # Deep link para o segundo exato
        video_id = dados_video.get("id")
        deep_link = f"https://youtu.be/{video_id}?t={sessao.segundos_inicio}" if video_id else dados_video.get("url")

        # Pessoas e organizações
        pessoas_validas = [p for p in analise.pessoas if eh_nome_valido_pessoa(p.nome)]
        organizacoes_extra = {p.nome.strip() for p in analise.pessoas if eh_organizacao(p.nome)}
        organizacoes_todas = list({*[o.strip() for o in analise.organizacoes if o and o.strip()], *organizacoes_extra})

        pessoas_links = [f"[[{limpar_nome_ficheiro(p.nome)}]]" for p in pessoas_validas]
        obras_links = [f"[[{limpar_nome_ficheiro(o.titulo)}]]" for o in analise.obras]
        temas_links = [f"[[{limpar_nome_ficheiro(t)}]]" for t in analise.temas]
        artefactos_links = [f"[[{limpar_nome_ficheiro(a.nome)}]]" for a in analise.artefactos]
        organizacoes_links = [f"[[{limpar_nome_ficheiro(o)}]]" for o in organizacoes_todas]

        orador_fmt = f"[[{limpar_nome_ficheiro(sessao.orador_principal)}]]" if sessao.orador_principal else "Vários / Painel"
        org_fmt = f"([[{limpar_nome_ficheiro(sessao.organizacao)}]])" if sessao.organizacao else ""
        tag_conf = limpar_nome_ficheiro(agenda.nome_conferencia).lower().replace(" ", "-")

        nota = f"""---
tipo: video_palestra
conferencia: "{moc_conferencia_wikilink}"
dia: {dia_num}
ordem: {sessao.ordem}
orador: "{sessao.orador_principal or 'Vários'}"
organizacao: "{sessao.organizacao or ''}"
timestamp_inicio: "{sessao.timestamp_inicio}"
timestamp_fim: "{sessao.timestamp_fim}"
url_palestra: "{deep_link}"
data_publicacao: "{dados_video.get('data')}"
data_leitura: "{data_leitura}"
tags:
  - video/palestra
  - conferencia/{tag_conf}
temas: {temas_links}
pessoas: {pessoas_links}
obras: {obras_links}
artefactos: {artefactos_links}
organizacoes: {organizacoes_links}
---
# {analise.titulo_palestra or sessao.titulo_palestra}

> 🏛️ **Conferência:** {moc_conferencia_wikilink} (Dia {dia_num})  
> 👤 **Orador:** {orador_fmt} {org_fmt}  
> ⏱️ **Momento:** `{sessao.timestamp_inicio} -> {sessao.timestamp_fim}`  
> 🔗 **Ver Palestra no YouTube:** [{deep_link}]({deep_link})

---

## 📝 Resumo da Palestra
{analise.resumo_executivo}

---

## 💡 Principais Takeaways
"""
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

        # Grava a nota atómica da palestra
        caminho_palestra.write_text(nota, encoding="utf-8")

        # Propaga entidades para as notas dedicadas (Pessoas, Artefactos, etc.)
        for p in pessoas_validas:
            obras_p = [o.titulo for o in analise.obras if p.nome in o.autores]
            self.salvar_ou_atualizar_pessoa(p, palestra_wikilink, obras_p)

        for o in analise.obras:
            self.salvar_ou_atualizar_obra(o, palestra_wikilink)

        for tm in analise.temas:
            self.salvar_ou_atualizar_tema(tm, palestra_wikilink)

        for org in organizacoes_todas:
            artefactos_org = [
                a.nome for a in analise.artefactos
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
        data_leitura: str = None
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

        # Constrói tabela markdown das palestras deste dia
        tabela_dia = f"""{seccao_cabecalho_dia}

> 🔗 **Transmissão Completa deste Dia:** [{dados_video.get('titulo')}]({dados_video.get('url')})  
> ⏱️ **Duração Total:** {int(dados_video.get('duracao_segundos', 0) // 60)} min | **Total de Palestras:** {len(palestras_processadas)}

| # | Início | Orador | Empresa | Palestra |
|---|---|---|---|---|
"""
        for p in palestras_processadas:
            s: SessaoScout = p["sessao"]
            link_palestra = f"[[{p['caminho'].stem}]]"
            orador_str = f"[[{limpar_nome_ficheiro(s.orador_principal)}]]" if s.orador_principal else "Painel"
            org_str = f"[[{limpar_nome_ficheiro(s.organizacao)}]]" if s.organizacao else "-"
            tabela_dia += f"| {s.ordem:02d} | `{s.timestamp_inicio}` | {orador_str} | {org_str} | {link_palestra} |\n"

        if not caminho_moc.exists():
            tag_conf = limpar_nome_ficheiro(agenda.nome_conferencia).lower().replace(" ", "-")
            conteudo_moc = f"""---
tipo: conferencia_moc
conferencia: "{agenda.nome_conferencia}"
canal: "{dados_video.get('canal')}"
data_primeira_leitura: "{data_leitura}"
tags:
  - conferencia/moc
  - conferencia/{tag_conf}
---
# 🏛️ {agenda.nome_conferencia}

> 📺 **Canal Organizador:** [{dados_video.get('canal')}]({dados_video.get('canal_url', '')})  
> 📂 **Pasta de Palestras:** `{pasta_conf.name}/`

Este ficheiro é o **Mapa de Conteúdo (MOC)** que centraliza todos os dias e palestras da conferência.

---

{tabela_dia}
"""
            caminho_moc.write_text(conteudo_moc, encoding="utf-8")
        else:
            conteudo_existente = caminho_moc.read_text(encoding="utf-8")
            # Se a secção deste dia já existia, substitui-a; caso contrário, acrescenta no fim
            padrao_dia = re.compile(rf"{re.escape(seccao_cabecalho_dia)}[\s\S]*?(?=\n## 📅|\Z)")
            if padrao_dia.search(conteudo_existente):
                novo_conteudo = padrao_dia.sub(tabela_dia.strip(), conteudo_existente)
            else:
                novo_conteudo = conteudo_existente.rstrip() + f"\n\n---\n\n{tabela_dia}\n"
            caminho_moc.write_text(novo_conteudo, encoding="utf-8")

        # Atualiza o Diário com o registo da conferência
        self.atualizar_diario_conferencia(dados_video, agenda, f"[[{caminho_moc.stem}]]", len(palestras_processadas), data_leitura)

        return caminho_moc

    def atualizar_diario_conferencia(
        self,
        dados_video: Dict[str, Any],
        agenda: AgendaScout,
        moc_wikilink: str,
        total_palestras: int,
        data_leitura: str = None
    ):
        """Regista a conferência no Diário (YYYY-MM-DD.md) com link para o MOC e lista das palestras do dia."""
        if not data_leitura:
            data_leitura = datetime.date.today().isoformat()

        caminho_diario = self.vault_path / f"{data_leitura}.md"
        canal_id = dados_video.get("canal_id")
        canal_str = f"{dados_video.get('canal')} (ID: {canal_id})" if canal_id else dados_video.get('canal')
        dia_rotulo = agenda.dia_rotulo or f"Dia {agenda.dia or 1}"

        bloco_novo = f"""===========================
# {moc_wikilink} — {dia_rotulo}
=== METADADOS DA CONFERÊNCIA ===
Conferência: {moc_wikilink} ({dia_rotulo})
Canal: {canal_str}
Data da Sessão: {agenda.data_sessao or dados_video.get('data')}
Data de Leitura: {data_leitura}
Palestras Integradas: {total_palestras} notas atómicas na subpasta [[{moc_wikilink}]]
Link da Transmissão: {dados_video.get('url')}

--- Descrição ---
{dados_video.get('descricao', '').strip()[:800]}...
"""
        if caminho_diario.exists():
            conteudo = caminho_diario.read_text(encoding="utf-8")
            if f"# {moc_wikilink} — {dia_rotulo}" in conteudo:
                return

            if "# Resenha do dia" in conteudo or "# Resenha do Dia" in conteudo:
                padrao = r"(#\s+Resenha do [Dd]ia)"
                substituicao = f"{bloco_novo}\n\\1"
                novo_conteudo, count = re.subn(padrao, substituicao, conteudo, count=1)
                if count > 0:
                    caminho_diario.write_text(novo_conteudo, encoding="utf-8")
                    print(f"    ✓ Diário {data_leitura}.md atualizado com a conferência {moc_wikilink} ({dia_rotulo}).")
                    return

            novo_conteudo = conteudo.rstrip() + f"\n\n{bloco_novo}\n"
            caminho_diario.write_text(novo_conteudo, encoding="utf-8")
            print(f"    ✓ Diário {data_leitura}.md atualizado com a conferência {moc_wikilink} ({dia_rotulo}).")
        else:
            caminho_diario.write_text(bloco_novo + "\n", encoding="utf-8")
            print(f"    ✓ Diário {data_leitura}.md criado com a conferência {moc_wikilink} ({dia_rotulo}).")