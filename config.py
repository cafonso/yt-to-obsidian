import os
from pathlib import Path

# Caminho predefinido para o teu cofre do Obsidian
DEFAULT_VAULT_PATH = os.environ.get("OBSIDIAN_VAULT_PATH", r"D:\Obsidian Files")

# Pastas organizadas dentro do cofre (nomes limpos e universais)
PASTA_VIDEOS = "Videos"
PASTA_PESSOAS = "Pessoas"
PASTA_LIVROS = "Livros"
PASTA_TEMAS = "Temas"

# Modelo Gemini predefinido
MODELO_GEMINI = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
