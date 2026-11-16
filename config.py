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

# ---------------------------------------------------------------------------
# Canonicalização de entidades
# ---------------------------------------------------------------------------

# Caminhos dos ficheiros de suporte à canonicalização.
# Por omissão, usam uma subpasta escondida dentro do vault do Obsidian.
# Podes sobrepor tudo com CANON_DIR ou cada var individualmente.
CANON_DIR = Path(os.environ.get("CANON_DIR", Path(DEFAULT_VAULT_PATH) / ".canonicalizacao"))
ALIASES_PATH = Path(os.environ.get("ALIASES_PATH", CANON_DIR / "aliases.yaml"))
DECISOES_PATH = Path(os.environ.get("DECISOES_PATH", CANON_DIR / "decisoes.jsonl"))
REVISAO_PATH = Path(os.environ.get("REVISAO_PATH", CANON_DIR / "revisao.md"))

# Thresholds de fusão fuzzy (0–100). Valores mais altos = menos fusões automáticas.
CANON_THRESHOLD_FUSAO_AUTO = int(os.environ.get("CANON_THRESHOLD_FUSAO_AUTO", 95))
CANON_THRESHOLD_REVISAO = int(os.environ.get("CANON_THRESHOLD_REVISAO", 85))

# Se True, o fuzzy só compara nomes que partilham o último token (blocking).
# Se False, compara contra todos os canónicos do tipo (mais lento, mais abrangente).
CANON_BLOCKING_POR_ULTIMO_TOKEN = os.environ.get("CANON_BLOCKING_POR_ULTIMO_TOKEN", "1") == "1"

# Se True, cada fusão confirmada é gravada em aliases.yaml para uso futuro.
CANON_APRENDER_ALIASES = os.environ.get("CANON_APRENDER_ALIASES", "1") == "1"

# Se True, escreve revisao.md (pares ambíguos) e decisoes.jsonl (auditoria).
CANON_ESCREVER_REVISAO = os.environ.get("CANON_ESCREVER_REVISAO", "1") == "1"
CANON_ESCREVER_DECISOES = os.environ.get("CANON_ESCREVER_DECISOES", "1") == "1"

# ---------------------------------------------------------------------------
# Retry / backoff nas chamadas ao Gemini
# ---------------------------------------------------------------------------

# Número máximo de tentativas por chamada (inclui a primeira).
GEMINI_MAX_TENTATIVAS = int(os.environ.get("GEMINI_MAX_TENTATIVAS", 5))

# Backoff exponencial: espera = base * 2^(tentativa-1), limitada ao teto.
GEMINI_BACKOFF_BASE_SEGUNDOS = float(os.environ.get("GEMINI_BACKOFF_BASE", 5.0))
GEMINI_BACKOFF_TETO_SEGUNDOS = float(os.environ.get("GEMINI_BACKOFF_TETO", 120.0))

# Jitter (fração aleatória adicionada/subtraída) para evitar thundering herd.
GEMINI_BACKOFF_JITTER = float(os.environ.get("GEMINI_BACKOFF_JITTER", 0.2))

# Bases específicas por tipo de erro (opcional; se None, usa a base geral).
GEMINI_BACKOFF_BASE_429 = float(os.environ.get("GEMINI_BACKOFF_BASE_429", 15.0))
GEMINI_BACKOFF_BASE_503 = float(os.environ.get("GEMINI_BACKOFF_BASE_503", 5.0))

# Se True, tenta ler o header Retry-After da resposta e respeitá-lo.
GEMINI_RESPEITAR_RETRY_AFTER = os.environ.get("GEMINI_RESPEITAR_RETRY_AFTER", "1") == "1"