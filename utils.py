import re

import urllib.request
import urllib.error
from typing import List, Optional

def verificar_link_ativo(url: str, timeout: float = 3.0) -> bool:
    """
    Verifica de forma leve e rápida se um URL está ativo (retorna código HTTP de sucesso ou redirecionamento).
    Usa um pedido HEAD para evitar descarregar o corpo da página.
    """
    if not url or not url.startswith(("http://", "https://")):
        return False

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Compatible; ObsidianPKMBot/1.0)"},
        method="HEAD"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return 200 <= response.status < 400
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, Exception):
        # Em caso de erro num pedido HEAD, tenta um GET rápido (alguns servidores rejeitam HEAD)
        try:
            req_get = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Compatible; ObsidianPKMBot/1.0)"},
                method="GET"
            )
            # Lê apenas os primeiros bytes ou usa timeout curto
            with urllib.request.urlopen(req_get, timeout=timeout) as response:
                return 200 <= response.status < 400
        except Exception:
            return False

def filtrar_recursos_ativos(recursos: List[str]) -> List[str]:
    """
    Filtra uma lista de recursos/links, mantendo apenas aqueles que respondem ativamente.
    Adiciona um comentário subtil ou remove os que falharem, ou preserva-os com um aviso.
    """
    recursos_validados = []
    for recurso in recursos:
        # Extrai URLs se o formato incluir Markdown do tipo [Texto](URL) ou texto livre
        import re
        urls = re.findall(r'https?://[^\s\]\)]+', recurso)
        
        if urls:
            url_alvo = urls[0]
            if verificar_link_ativo(url_alvo):
                recursos_validados.append(recurso)
            else:
                # Opcional: Mantém o recurso mas sinaliza que pode estar inativo
                recursos_validados.append(f"{recurso} ⚠️ *(Link possivelmente inativo)*")
        else:
            recursos_validados.append(recurso)
            
    return recursos_validados

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