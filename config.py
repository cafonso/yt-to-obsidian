import os
from pathlib import Path

# Caminho predefinido para o teu cofre do Obsidian
DEFAULT_VAULT_PATH = os.environ.get("OBSIDIAN_VAULT_PATH", r"D:\Obsidian Files")

# Pastas organizadas dentro do cofre (nomes limpos e universais)
PASTA_VIDEOS = "Videos"
PASTA_PESSOAS = "Pessoas"
PASTA_LIVROS = "Livros"
PASTA_TEMAS = "Temas"
PASTA_ARTEFACTOS = "Artefactos"
PASTA_ORGANIZACOES = "Organizações"

# Subtipos válidos para artefactos (usado para normalização defensiva)
SUBTIPOS_ARTEFACTO = {
    "modelo", "framework", "ferramenta", "agente",
    "tecnica", "hardware", "plataforma", "dataset",
}

# Modelo Gemini predefinido
MODELO_GEMINI = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Parâmetros para processamento de vídeos longos (fatiamento Map-Reduce)
LIMIAR_VIDEO_LONGO_SEGUNDOS = int(os.environ.get("LIMIAR_VIDEO_LONGO", 45 * 60))  # 45 minutos
DURACAO_CHUNK_SEGUNDOS = int(os.environ.get("DURACAO_CHUNK", 30 * 60))             # 30 minutos por fatia

