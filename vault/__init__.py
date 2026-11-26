# vault\__init__.py
from vault.core import (
    ObsidianVaultWriter,
    limpar_nome_ficheiro,
    validar_recursos_externos,
)

__all__ = [
    "ObsidianVaultWriter",
    "limpar_nome_ficheiro",
    "validar_recursos_externos",
]