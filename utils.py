import re

PALAVRAS_ORGANIZACAO = {
    "inc", "corp", "corporation", "labs", "lab", "university", "universidade",
    "institute", "instituto", "foundation", "fundação",
    "research", "school", "escola", "college", "center", "centre",
    "centro", "group", "grupo", "technologies", "technology",
    "systems", "sistemas", "solutions", "solucoes",
    "ai", "ia", "llc", "ltd", "gmbh", "sa", "plc", "holdings",
    "ventures", "capital", "partners", "studio", "studios",
    "media", "network", "networks", "cloud", "compute", "semiconductor", "Lda",
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

def eh_nome_valido_pessoa(nome: str) -> bool:
    """Valida se o nome parece um nome de pessoa real (Nome + Apelido) e não uma organização."""
    nome_limpo = nome.strip()
    if not nome_limpo:
        return False
    partes = [p for p in nome_limpo.split() if p]
    if len(partes) < 2:
        return False
    return not eh_organizacao(nome_limpo)