"""
Canonicalização determinística de entidades extraídas por LLM.

Resolve o problema de grafias inconsistentes (erros de ASR, variantes do LLM)
antes de as entidades chegarem ao vault_writer. Três vias, por ordem:

  1. Normalização (acentos, caixa, pontuação, espaços)
  2. Dicionário de aliases explícito (aliases.yaml)
  3. Fuzzy match contra os canónicos já conhecidos (rapidfuzz)

Cada fusão é registada em decisoes.jsonl. Pares ambíguos (score médio)
vão para revisao.md. O dicionário aprende: cada fusão confirmada é
gravada em aliases.yaml para resolução determinística futura.

Este módulo é agnóstico em relação ao config: todos os parâmetros
(paths, thresholds, flags) entram pelo __init__. Assim é testável
isoladamente e reutilizável fora do pipeline.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from rapidfuzz import fuzz, process

from models import ArtefactoIA, ObraCitada, PessoaMencionada
from utils import eh_nome_valido_pessoa 

# ---------------------------------------------------------------------------
# Normalização base
# ---------------------------------------------------------------------------

def norm(s: str) -> str:
    """Normaliza uma string para comparação: sem acentos, minúsculas, sem pontuação."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def chave_bloqueio(nome: str) -> str:
    """
    Chave de blocking para reduzir o espaço de comparação fuzzy.
    Usa o último token (sobrenome para pessoas, palavra final para orgs/artefactos).
    """
    tokens = norm(nome).split()
    return tokens[-1] if tokens else ""


# ---------------------------------------------------------------------------
# Estruturas de decisão
# ---------------------------------------------------------------------------

@dataclass
class Decisao:
    tipo: str                  # "pessoa", "artefacto", "obra", "organizacao", "tema"
    raw: str
    canonical: str
    metodo: str                # "exato", "alias", "fuzzy", "fallback"
    score: Optional[int] = None
    incerto: bool = False
    data: str = field(default_factory=lambda: date.today().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tipo": self.tipo,
            "raw": self.raw,
            "canonical": self.canonical,
            "metodo": self.metodo,
            "score": self.score,
            "incerto": self.incerto,
            "data": self.data,
        }


# ---------------------------------------------------------------------------
# Canonicalizer
# ---------------------------------------------------------------------------

class Canonicalizer:
    """
    Resolve nomes para formas canónicas, com dicionário persistente e fuzzy match.

    Uso típico (dentro do analyzer, no fim do Map-Reduce):

        canon = Canonicalizer()
        pessoas = canon.canonicalizar_pessoas(todas_pessoas)
        artefactos = canon.canonicalizar_artefactos(todos_artefactos)
        ...
        canon.gravar()   # persiste aliases.yaml, decisoes.jsonl, revisao.md
    """

    # Tipos suportados — usado para inicializar a estrutura do dicionário.
    TIPOS = ("pessoa", "artefacto", "obra", "organizacao", "tema")

    def __init__(
        self,
        aliases_path: Path = Path("aliases.yaml"),
        decisoes_path: Path = Path("decisoes.jsonl"),
        revisao_path: Path = Path("revisao.md"),
        threshold_fusao_auto: int = 95,
        threshold_revisao: int = 85,
        blocking_por_ultimo_token: bool = True,
        aprender_aliases: bool = True,
        escrever_revisao: bool = True,
        escrever_decisoes: bool = True,
    ):
        self.aliases_path = Path(aliases_path)
        self.decisoes_path = Path(decisoes_path)
        self.revisao_path = Path(revisao_path)

        self.threshold_fusao_auto = threshold_fusao_auto
        self.threshold_revisao = threshold_revisao
        self.blocking_por_ultimo_token = blocking_por_ultimo_token
        self.aprender_aliases = aprender_aliases
        self.escrever_revisao = escrever_revisao
        self.escrever_decisoes = escrever_decisoes

        self._decisoes: List[Decisao] = []
        self._revisao: List[Decisao] = []

        # Estrutura em memória: tipo -> {canonical: [aliases...]}
        self._dict: Dict[str, Dict[str, List[str]]] = self._carregar_aliases()

        # Índices derivados para lookup rápido: tipo -> {norm(alias): canonical}
        self._lookup: Dict[str, Dict[str, str]] = {}
        self._reconstruir_lookup()

    # ------------------------------------------------------------------
    # Persistência
    # ------------------------------------------------------------------

    def _carregar_aliases(self) -> Dict[str, Dict[str, List[str]]]:
        base: Dict[str, Dict[str, List[str]]] = {t: {} for t in self.TIPOS}
        if not self.aliases_path.exists():
            return base
        raw = yaml.safe_load(self.aliases_path.read_text(encoding="utf-8")) or {}
        for tipo, entries in raw.items():
            if not isinstance(entries, dict):
                continue
            for canonical, data in entries.items():
                aliases: List[str] = []
                if isinstance(data, dict):
                    aliases = list(data.get("aliases", []) or [])
                elif isinstance(data, list):
                    aliases = list(data)
                base.setdefault(tipo, {})[canonical] = aliases
        return base

    def _reconstruir_lookup(self):
        self._lookup = {}
        for tipo, entries in self._dict.items():
            idx: Dict[str, str] = {}
            for canonical, aliases in entries.items():
                idx[norm(canonical)] = canonical
                for a in aliases:
                    idx[norm(a)] = canonical
            self._lookup[tipo] = idx

    def gravar(self):
        """Persiste aliases.yaml, decisoes.jsonl e revisao.md (respeitando os flags)."""
        # Garante que os diretórios existem antes de escrever
        for p in {self.aliases_path, self.decisoes_path, self.revisao_path}:
            p.parent.mkdir(parents=True, exist_ok=True)

        # 1. aliases.yaml — reescreve o estado atual do dicionário
        if self.aprender_aliases:
            self.aliases_path.write_text(
                yaml.safe_dump(self._dict, allow_unicode=True, sort_keys=True),
                encoding="utf-8",
            )

        # 2. decisoes.jsonl — append (auditoria)
        if self.escrever_decisoes and self._decisoes:
            with self.decisoes_path.open("a", encoding="utf-8") as f:
                for d in self._decisoes:
                    f.write(json.dumps(d.to_dict(), ensure_ascii=False) + "\n")

       
        # 3. revisao.md — acrescenta apenas pares ambíguos inéditos
        if self.escrever_revisao and self._revisao:
            cabecalho = "# Revisão de canonicalização"
            linhas_existentes: List[str] = []

            if self.revisao_path.exists():
                conteudo_atual = self.revisao_path.read_text(encoding="utf-8")
                linhas_existentes = [
                    l.strip() for l in conteudo_atual.splitlines()
                    if l.strip() and l.strip() != cabecalho
                ]

            # Conjunto para deduplicar pela assinatura do par (ignora variações de score)
            pares_registados = set()
            for linha in linhas_existentes:
                # Extrai a parte "- **tipo**: `raw` → `canonical`"
                chave = linha.split(" (score ")[0]
                pares_registados.add(chave)

            novas_linhas = []
            for d in self._revisao:
                assinatura = f"- **{d.tipo}**: `{d.raw}` → `{d.canonical}`"
                if assinatura not in pares_registados:
                    pares_registados.add(assinatura)
                    novas_linhas.append(f"{assinatura} (score {d.score}, método {d.metodo})")

            if novas_linhas or not self.revisao_path.exists():
                todas_linhas = [cabecalho, ""] + linhas_existentes + novas_linhas
                self.revisao_path.write_text("\n".join(todas_linhas) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------
    # Núcleo: resolução de um nome
    # ------------------------------------------------------------------

    def _resolver(self, tipo: str, nome: str) -> Tuple[str, Decisao]:
        """
        Resolve `nome` para canónico. Devolve (canonical, decisao).
        Não grava no dicionário — isso é feito pelo chamador via _registar_fusao.
        """
        nome = (nome or "").strip()
        if not nome:
            return "", Decisao(tipo, nome, nome, "fallback")

        n = norm(nome)

        # Via 1: match exato ou por alias no dicionário
        if n in self._lookup.get(tipo, {}):
            canonical = self._lookup[tipo][n]
            metodo = "exato" if norm(canonical) == n else "alias"
            return canonical, Decisao(tipo, nome, canonical, metodo)

        # Via 2: fuzzy contra os canónicos conhecidos, com blocking opcional
        candidatos = list(self._dict.get(tipo, {}).keys())
        if candidatos:
            if self.blocking_por_ultimo_token:
                kb = chave_bloqueio(nome)
                restritos = [c for c in candidatos if chave_bloqueio(c) == kb] or candidatos
            else:
                restritos = candidatos

            match = process.extractOne(nome, restritos, scorer=fuzz.token_sort_ratio)
            if match:
                candidato, score, _ = match
                if score >= self.threshold_fusao_auto:
                    return candidato, Decisao(tipo, nome, candidato, "fuzzy", int(score))
                if score >= self.threshold_revisao:
                    d = Decisao(tipo, nome, candidato, "fuzzy", int(score), incerto=True)
                    self._revisao.append(d)
                    self._decisoes.append(d)
                    # Não funde automaticamente — devolve o raw como canónico próprio
                    return nome, Decisao(tipo, nome, nome, "fallback")

        # Via 3: fallback — nome novo, fica como está
        return nome, Decisao(tipo, nome, nome, "fallback")


    def _registar_fusao(self, tipo: str, canonical: str, raw: str, decisao: Decisao):
        if self.aprender_aliases and norm(raw) != norm(canonical):
           entry = self._dict.setdefault(tipo, {}).setdefault(canonical, [])
           # Só grava se não houver já um alias equivalente após normalização
           existentes_norm = {norm(a) for a in entry} | {norm(canonical)}
           if norm(raw) not in existentes_norm:
              entry.append(raw)
           self._lookup.setdefault(tipo, {})[norm(raw)] = canonical
        self._decisoes.append(decisao)
        
    # ------------------------------------------------------------------
    # API por tipo — pessoas
    # ------------------------------------------------------------------

    def canonicalizar_pessoas(self, pessoas: List[PessoaMencionada]) -> List[PessoaMencionada]:
        """
        Funde pessoas com a mesma identidade canónica.
        Preserva a bio mais longa (como no desduplicar_pessoas original).
        """
        grupos: Dict[str, PessoaMencionada] = {}
        for p in pessoas:
            if not p.nome or not eh_nome_valido_pessoa(p.nome):
                continue
            canonical, decisao = self._resolver("pessoa", p.nome)
            if not canonical:
                continue
            self._registar_fusao("pessoa", canonical, p.nome, decisao)

            if canonical not in grupos:
                grupos[canonical] = PessoaMencionada(
                    nome=canonical, papel_ou_bio=p.papel_ou_bio or ""
                )
            else:
                atual = grupos[canonical]
                if len(p.papel_ou_bio or "") > len(atual.papel_ou_bio or ""):
                    atual.papel_ou_bio = p.papel_ou_bio
        return list(grupos.values())


    # ------------------------------------------------------------------
    # API por tipo — artefactos
    # ------------------------------------------------------------------

    def canonicalizar_artefactos(self, artefactos: List[ArtefactoIA]) -> List[ArtefactoIA]:
        """
        Funde artefactos com o mesmo nome canónico.
        Preserva o subtipo mais específico (não-modelo ganha a modelo),
        o fabricante preenchido e a descrição mais longa.
        """
        grupos: Dict[str, ArtefactoIA] = {}
        for a in artefactos:
            if not a.nome or not a.nome.strip():
                continue
            canonical, decisao = self._resolver("artefacto", a.nome)
            if not canonical:
                continue
            self._registar_fusao("artefacto", canonical, a.nome, decisao)

            if canonical not in grupos:
                grupos[canonical] = ArtefactoIA(
                    nome=canonical,
                    subtipo=a.subtipo,
                    fabricante_ou_autor=a.fabricante_ou_autor,
                    descricao=a.descricao,
                )
            else:
                atual = grupos[canonical]
                if atual.subtipo == "modelo" and a.subtipo != "modelo":
                    atual.subtipo = a.subtipo
                if not atual.fabricante_ou_autor and a.fabricante_ou_autor:
                    atual.fabricante_ou_autor = a.fabricante_ou_autor
                if not atual.descricao and a.descricao:
                    atual.descricao = a.descricao
                elif a.descricao and len(a.descricao) > len(atual.descricao or ""):
                    atual.descricao = a.descricao
        return list(grupos.values())

    # ------------------------------------------------------------------
    # API por tipo — obras
    # ------------------------------------------------------------------

    def canonicalizar_obras(self, obras: List[ObraCitada]) -> List[ObraCitada]:
        grupos: Dict[str, ObraCitada] = {}
        for o in obras:
            if not o.titulo or not o.titulo.strip():
                continue
            canonical, decisao = self._resolver("obra", o.titulo)
            if not canonical:
                continue
            self._registar_fusao("obra", canonical, o.titulo, decisao)

            if canonical not in grupos:
                grupos[canonical] = ObraCitada(
                    titulo=canonical,
                    tipo=o.tipo,
                    autores=list(o.autores or []),
                    contexto=o.contexto,
                )
            else:
                atual = grupos[canonical]
                if not atual.autores and o.autores:
                    atual.autores = list(o.autores)
                if not atual.contexto and o.contexto:
                    atual.contexto = o.contexto
        return list(grupos.values())

    # ------------------------------------------------------------------
    # API por tipo — organizações e temas (strings simples)
    # ------------------------------------------------------------------

    def canonicalizar_strings(self, tipo: str, itens: List[str]) -> List[str]:
        """
        Para organizações e temas. `tipo` deve ser "organizacao" ou "tema".
        Devolve strings canónicas, sem duplicados, preservando ordem de primeira aparição.
        """
        if tipo not in ("organizacao", "tema"):
            raise ValueError(f"canonicalizar_strings: tipo inválido '{tipo}' (use 'organizacao' ou 'tema')")

        vistos: Dict[str, str] = {}   # canonical_norm -> canonical
        resultado: List[str] = []
        for item in itens:
            if not item or not item.strip():
                continue
            canonical, decisao = self._resolver(tipo, item)
            if not canonical:
                continue
            self._registar_fusao(tipo, canonical, item, decisao)
            chave = norm(canonical)
            if chave not in vistos:
                vistos[chave] = canonical
                resultado.append(canonical)
        return resultado