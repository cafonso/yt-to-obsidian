"""
Fachada de compatibilidade para a escrita no cofre Obsidian.

A implementação modular reside em `vault/` (`core`, `entidades`, `videos`, `conferencias`).
Este módulo re-exporta os símbolos públicos e utilitários usados pelo pipeline e pelos testes.
"""

from utils import verificar_link_ativo
from vault.core import (
    ObsidianVaultWriter,
    _correr_async,
    _escapar_yaml_str,
    _sanitizar_blockquote,
    _validar_lista_recursos_async,
    _yaml_lista,
    limpar_nome_ficheiro,
    validar_recursos_externos,
)

__all__ = [
    "ObsidianVaultWriter",
    "limpar_nome_ficheiro",
    "validar_recursos_externos",
    "verificar_link_ativo",
]