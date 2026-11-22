import http.client
import logging
from pathlib import Path
import re
import urllib.error
import urllib.request

import config


def validar_cofre(pasta_cofre: str | Path) -> Path:
    """Garante que o caminho do cofre existe e é um diretório."""
    caminho = Path(pasta_cofre)
    if not caminho.exists() or not caminho.is_dir():
        raise FileNotFoundError(f"A pasta do cofre não existe: {caminho}")
    return caminho


def _resolver_caminho_log(pasta_cofre: str | Path | None = None) -> Path:
    """Resolve o ficheiro de registo dentro da pasta de logs do cofre indicado."""
    base = Path(pasta_cofre) if pasta_cofre else Path(config.COFRE_PADRAO)
    nome_ficheiro = Path(config.LIVRO_REGISTO).name
    return base / "logs" / nome_ficheiro


def configurar_logging(
    pasta_cofre: str | Path | None = None,
    nivel_str: str = config.LOG_LEVEL,
) -> logging.Logger:
    """Configura ou reconfigura o logger partilhado para a pasta de logs do cofre."""
    cofre_validado = validar_cofre(pasta_cofre if pasta_cofre else config.COFRE_PADRAO)
    caminho_log = _resolver_caminho_log(cofre_validado)
    caminho_log.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("yt_obsidian")
    nivel = getattr(logging, str(nivel_str).upper(), logging.INFO)
    logger.setLevel(nivel)
    logger.propagate = False

    formato_ficheiro = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    )
    formato_consola = logging.Formatter("%(message)s")

    tem_consola = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in logger.handlers
    )
    if not tem_consola:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formato_consola)
        logger.addHandler(console_handler)

    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler):
            handler.close()
            logger.removeHandler(handler)

    file_handler = logging.FileHandler(caminho_log, mode="a", encoding="utf-8")
    file_handler.setFormatter(formato_ficheiro)
    logger.addHandler(file_handler)

    return logger


def verificar_link_ativo(url: str, timeout: float = 3.5) -> bool:
    """Verifica de forma leve se um URL responde com sucesso (200-399)."""
    if not url or not url.startswith(("http://", "https://")):
        return False

    headers = {"User-Agent": "Mozilla/5.0 (Compatible; ObsidianPKMBot/1.0)"}

    # 1. Tenta pedido HEAD (mais rápido, sem descarregar o corpo)
    try:
        req_head = urllib.request.Request(url, headers=headers, method="HEAD")
        with urllib.request.urlopen(req_head, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except (OSError, http.client.HTTPException):
        pass

    # 2. Fallback para GET leve (alguns servidores bloqueiam HEAD)
    try:
        req_get = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req_get, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except (OSError, http.client.HTTPException):
        return False


PALAVRAS_ORGANIZACAO = {
    "inc", "corp", "corporation", "labs", "lab", "university", "universidade",
    "institute", "instituto", "foundation", "fundação",
    "research", "school", "escola", "college", "center", "centre",
    "centro", "group", "grupo", "technologies", "technology",
    "systems", "sistemas", "solutions", "solucoes",
    "ai", "ia", "llc", "ltd", "gmbh", "sa", "plc", "holdings",
    "ventures", "capital", "partners", "studio", "studios",
    "media", "network", "networks", "cloud", "compute", "semiconductor", "lda",
}

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


def eh_organizacao(nome: str) -> bool:
    """Determina se um nome corresponde a uma organização."""
    nome_lower = nome.strip().lower()
    if not nome_lower:
        return False

    if nome_lower in ORGANIZACOES_CONHECIDAS:
        return True

    for org in ORGANIZACOES_CONHECIDAS:
        if nome_lower == org or nome_lower.startswith(org + " "):
            return True

    palavras = set(re.split(r"[\s\-_.,]+", nome_lower))
    if palavras & PALAVRAS_ORGANIZACAO:
        return True

    return False


# Palavras que, quando compõem a totalidade de um nome, indicam um conceito
# técnico e não uma pessoa. Usadas por `eh_nome_valido_pessoa` para rejeitar
# falsos positivos como "Large Language Model" ou "Mixture of Experts".
PALAVRAS_CONCEITO_TECNICO = {
    # Conceitos gerais de IA/ML
    "model", "models", "language", "languages", "learning", "network", "networks",
    "generation", "generative", "augmented", "retrieval", "transformer", "transformers",
    "attention", "embedding", "embeddings", "agent", "agents", "agentic",
    "prompt", "prompts", "prompting", "context", "contexts", "reasoning",
    "training", "inference", "tuning", "finetuning", "fine-tuning",
    "mixture", "experts", "expert", "chain", "thought", "thoughts",
    "deep", "reinforcement", "supervised", "unsupervised",
    "large", "small", "medium", "vision", "multimodal", "text", "image", "audio",
    "video", "speech", "code", "coding", "programming", "software", "hardware",
    "data", "dataset", "datasets", "token", "tokens", "tokenizer", "tokenization",
    "layer", "layers", "neural", "graph", "graphs", "vector", "vectors",
    "database", "search", "memory", "state", "pipeline", "workflow",
    "orchestration", "framework", "stack", "protocol", "api", "apis",
    "endpoint", "endpoints", "safety", "alignment", "interpretability",
    "evaluation", "benchmark", "throughput", "latency", "scaling", "scale",
    "quantization", "distillation", "pruning", "sparsity", "efficiency",
    "performance", "optimization", "gradient", "loss", "backpropagation",
    "epoch", "batch", "parameter", "parameters", "weights", "bias",
    "activation", "dropout", "convolution", "recurrent", "sequence",
    "diffusion", "autoencoder", "gan", "vae", "rlhf", "dpo", "sft",
    "lora", "qlora", "peft", "adapter", "adapters",
    "in-context", "few-shot", "zero-shot", "one-shot",
    "cot", "scratchpad", "reflection", "critique", "planning",
    "tool", "tools", "tool-use", "function", "functions", "calling",
    "mcp", "rag", "reranking", "rerank", "chunking", "chunk", "chunks",
    "semantic", "lexical", "hybrid", "dense", "sparse",
    "knowledge", "execution", "action", "actions", "observation",
    "observations", "reward", "rewards", "policy", "policies",
    "environment", "environments", "simulation", "simulations",
    # Conectores comuns que aparecem em conceitos técnicos
    "of", "the", "and", "or", "for", "in", "on", "with", "via", "to", "from",
}


def eh_nome_valido_pessoa(nome: str) -> bool:
    """
    Valida se o nome parece um nome de pessoa real (Nome + Apelido) e não
    uma organização ou um conceito técnico.

    Heurísticas aplicadas, por ordem:
      1. Tem de ter ≥ 2 palavras.
      2. Não pode ser uma organização (via `eh_organizacao`).
      3. Todas as palavras não podem ser conceitos técnicos (via
         `PALAVRAS_CONCEITO_TECNICO`), o que rejeita "Large Language Model",
         "Mixture of Experts", "Chain of Thought", etc.
         A capitalização NÃO é usada como critério — nomes de pessoas podem
         vir em minúsculas de transcrições ASR.
    """
    nome_limpo = nome.strip()
    if not nome_limpo:
        return False

    partes = [p for p in nome_limpo.split() if p]
    if len(partes) < 2:
        return False

    if eh_organizacao(nome_limpo):
        return False

    # Se todas as palavras (normalizadas) são conceitos técnicos ou
    # conectores, não é uma pessoa.
    palavras_norm = {
        re.sub(r"[^a-z0-9\-]", "", p.lower())
        for p in partes
        if p
    }
    palavras_norm.discard("")
    if palavras_norm and palavras_norm.issubset(PALAVRAS_CONCEITO_TECNICO):
        return False

    return True