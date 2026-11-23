from pathlib import Path
import pytest
import logging
import config
from utils import configurar_logging, validar_cofre

def test_validar_cofre_existente(tmp_path: Path) -> None:
    cofre_valido = tmp_path / "CofreTeste"
    cofre_valido.mkdir()

    assert validar_cofre(cofre_valido) == cofre_valido


def test_validar_cofre_inexistente_lanca_erro(tmp_path: Path) -> None:
    cofre_inexistente = tmp_path / "CofreQueNaoExiste"

    with pytest.raises(FileNotFoundError):
        validar_cofre(cofre_inexistente)


def test_configurar_logging_troca_de_cofre(tmp_path: Path) -> None:
    cofre_a = tmp_path / "CofreA"
    cofre_b = tmp_path / "CofreB"
    cofre_a.mkdir()
    cofre_b.mkdir()

    nome_log = Path(config.LIVRO_REGISTO).name

    # 1. Configura no CofreA e escreve uma linha
    logger_a = configurar_logging(pasta_cofre=cofre_a)
    logger_a.info("mensagem no cofre A")

    log_a = cofre_a / "logs" / nome_log
    assert log_a.exists()
    assert "mensagem no cofre A" in log_a.read_text(encoding="utf-8")

    handlers_a = [h for h in logger_a.handlers if isinstance(h, logging.FileHandler)]
    assert len(handlers_a) == 1
    handler_antigo = handlers_a[0]

    # 2. Troca para o CofreB e escreve outra linha
    logger_b = configurar_logging(pasta_cofre=cofre_b)
    logger_b.info("mensagem no cofre B")

    log_b = cofre_b / "logs" / nome_log
    assert log_b.exists()
    assert "mensagem no cofre B" in log_b.read_text(encoding="utf-8")
    assert "mensagem no cofre B" not in log_a.read_text(encoding="utf-8")

    # 3. Garante que o handler anterior foi fechado e substituído por um único FileHandler
    assert handler_antigo.stream is None
    handlers_b = [h for h in logger_b.handlers if isinstance(h, logging.FileHandler)]
    assert len(handlers_b) == 1
    assert Path(handlers_b[0].baseFilename) == log_b

    # Limpeza final dos handlers de ficheiro abertos durante o teste
    for h in list(logger_b.handlers):
        if isinstance(h, logging.FileHandler):
            h.close()
            logger_b.removeHandler(h)