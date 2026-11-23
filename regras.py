"""Regras de decisão puras, sem side-effects no import."""
import logging

logger = logging.getLogger("yt_obsidian")


def deve_saltar(video_id, historico, forcar, logger=logger):
    """True se o vídeo já foi integrado e não foi pedido --forcar."""
    if video_id and not forcar and video_id in historico:
        entrada = historico.get(video_id) or {}
        titulo_antigo = entrada.get("titulo", "Vídeo")
        logger.info(
            "⏭️ [Saltar] '%s' já foi integrado no Obsidian. "
            "(Usa --forcar para reanalisar)",
            titulo_antigo,
        )
        return True
    return False