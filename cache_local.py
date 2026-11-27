from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar
from pydantic import BaseModel, Field

import config
from models import EstadoPipeline, ScoutResultado

T = TypeVar("T", bound=BaseModel)


def _resolver_pasta_cache(vault_path: Optional[str | Path] = None) -> Path:
    if vault_path:
        base = Path(vault_path)
        if base.exists() and base.is_dir():
            return base / config.CACHE_DIR_NAME
    return Path(config.CACHE_DIR_NAME)


class CacheLocalLLM:
    def __init__(
        self,
        vault_path: Optional[str | Path] = None,
        ativo: Optional[bool] = None,
        apenas_leitura: bool = False,
    ):
        self.ativo = config.CACHE_ATIVO if ativo is None else ativo
        self.apenas_leitura = apenas_leitura
        self.cache_dir = _resolver_pasta_cache(vault_path)
        if self.ativo and not self.apenas_leitura:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def hash_texto(texto: str) -> str:
        return hashlib.sha256((texto or "").encode("utf-8")).hexdigest()

    @staticmethod
    def hash_ficheiro(caminho: Optional[str | Path]) -> str:
        if not caminho:
            return ""
        p = Path(caminho)
        if not p.exists() or not p.is_file():
            return ""
        h = hashlib.sha256()
        with p.open("rb") as f:
            for bloco in iter(lambda: f.read(65536), b""):
                h.update(bloco)
        return h.hexdigest()

    @staticmethod
    def gerar_chave(
        etapa: str,
        identificador: str,
        modelo: str,
        assinatura_conteudo: str = "",
        versao: Optional[str] = None,
    ) -> str:
        ver = versao or config.CACHE_VERSAO
        raw = f"{ver}|{etapa}|{identificador}|{modelo}|{assinatura_conteudo}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _caminho_json(self, chave: str) -> Path:
        return self.cache_dir / f"{chave}.json"

    def obter(
        self,
        chave: str,
        modelo_pydantic: Type[T],
        ignorar_leitura: bool = False,
    ) -> Optional[T]:
        if not self.ativo or ignorar_leitura:
            return None
        caminho = self._caminho_json(chave)
        if not caminho.exists():
            return None
        try:
            return modelo_pydantic.model_validate_json(caminho.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _chave_estado(self, video_id: str) -> str:
        return self.gerar_chave(
            etapa="pipeline_estado",
            identificador=video_id,
            modelo="__estado__",
            assinatura_conteudo="",
        )

    def obter_estado(self, video_id: str) -> Optional["EstadoPipeline"]:
        if not video_id:
            return None
        return self.obter(self._chave_estado(video_id), EstadoPipeline)

    def guardar_estado(self, estado: "EstadoPipeline") -> None:
        if not estado or not estado.video_id:
            return
        self.guardar(
            self._chave_estado(estado.video_id),
            estado,
            meta={"etapa": "pipeline_estado", "video_id": estado.video_id},
        )
    def guardar(
        self,
        chave: str,
        instancia: BaseModel,
        meta: Optional[dict[str, Any]] = None,
        ignorar_escrita: bool = False,
    ) -> None:
        if not self.ativo or self.apenas_leitura or ignorar_escrita:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        caminho = self._caminho_json(chave)
        tmp = caminho.with_suffix(".json.tmp")
        tmp.write_text(instancia.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, caminho)

        if meta is not None:
            meta_path = self.cache_dir / f"{chave}.meta.json"
            meta_tmp = meta_path.with_suffix(".meta.json.tmp")
            meta_tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(meta_tmp, meta_path)

    def estatisticas(self) -> tuple[int, int]:
        """Devolve (numero_de_entradas, bytes_totais)."""
        if not self.cache_dir.exists():
            return (0, 0)
        itens = [
            p for p in self.cache_dir.iterdir()
            if p.is_file() and p.suffix == ".json" and not p.name.endswith(".meta.json")
        ]
        total_bytes = sum(p.stat().st_size for p in itens)
        return (len(itens), total_bytes)

    def limpar(self) -> int:
        if not self.cache_dir.exists():
            return 0
        removidos = 0
        for p in self.cache_dir.iterdir():
            if p.is_file():
                p.unlink()
                removidos += 1
        return removidos
        

class GestorEstadoPipeline:
    """Gere o estado persistente por vídeo sobre o CacheLocalLLM."""

    def __init__(self, cache: CacheLocalLLM):
        self.cache = cache

    @staticmethod
    def _normalizar_id(dados_video: Dict[str, Any]) -> str:
        return (
            str(dados_video.get("id") or "")
            or str(dados_video.get("video_id") or "")
            or str(dados_video.get("url") or "")
            or str(dados_video.get("titulo") or "sem_id")
        )

    def chave_estado(self, dados_video: Dict[str, Any]) -> str:
        video_id = self._normalizar_id(dados_video)
        return self.cache.gerar_chave(
            etapa="pipeline_estado",
            identificador=video_id,
            modelo="__estado__",
            assinatura_conteudo=f"estado_v1:{video_id}",
        )

    def carregar(self, dados_video: Dict[str, Any], forcar: bool = False) -> EstadoPipeline:
        video_id = self._normalizar_id(dados_video)
        titulo = dados_video.get("titulo")

        if not forcar:
            existente = self.cache.obter(
                self.chave_estado(dados_video),
                EstadoPipeline,
                ignorar_leitura=False,
            )
            if existente is not None:
                if titulo and not existente.titulo:
                    existente.titulo = titulo
                return existente

        return EstadoPipeline(
            video_id=video_id,
            titulo=titulo,
            passo_seguinte="scout",
            timestamp_ultima_execucao=datetime.now(timezone.utc).isoformat(),
        )

    def guardar(
        self,
        dados_video: Dict[str, Any],
        estado: EstadoPipeline,
        passo_concluido: Optional[str] = None,
        proximo_passo: Optional[str] = None,
        concluido: Optional[bool] = None,
        degradado: Optional[bool] = None,
        erro: Optional[str] = None,
    ) -> None:
        if passo_concluido and passo_concluido not in estado.passos_concluidos:
            estado.passos_concluidos.append(passo_concluido)
        if proximo_passo is not None or concluido:
            estado.passo_seguinte = None if concluido else proximo_passo
        if concluido is not None:
            estado.concluido = concluido
        if degradado is not None:
            estado.degradado = degradado
        estado.erro_ultimo_passo = erro
        estado.timestamp_ultima_execucao = datetime.now(timezone.utc).isoformat()

        self.cache.guardar(
            self.chave_estado(dados_video),
            estado,
            meta={
                "etapa": "pipeline_estado",
                "modelo": "__estado__",
                "video_id": estado.video_id,
                "concluido": estado.concluido,
                "degradado": estado.degradado,
            },
        )

    def registar_scout(
        self,
        dados_video: Dict[str, Any],
        estado: EstadoPipeline,
        eh_conferencia: bool,
        nome_conferencia: Optional[str] = None,
        dia: Optional[int] = None,
        dia_rotulo: Optional[str] = None,
        proximo_passo: str = "analisar",
    ) -> None:
        estado.scout = ScoutResultado(
            eh_conferencia=bool(eh_conferencia),
            nome_conferencia=nome_conferencia,
            dia=dia,
            dia_rotulo=dia_rotulo,
        )
        self.guardar(
            dados_video,
            estado,
            passo_concluido="scout",
            proximo_passo=proximo_passo,
        )