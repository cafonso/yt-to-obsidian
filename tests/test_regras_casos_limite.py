import logging
import pytest
from regras import deve_saltar


@pytest.fixture
def logger_teste(caplog):
    logger = logging.getLogger("yt_obsidian_teste")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(caplog.handler)  # sem isto, caplog fica vazio
    caplog.set_level(logging.INFO, logger="yt_obsidian_teste")
    yield logger
    logger.removeHandler(caplog.handler)


def test_duplicado_sem_forcar_salta_e_avisa(logger_teste, caplog):
    historico = {"abc": {"titulo": "Vídeo Antigo"}}
    assert deve_saltar("abc", historico, forcar=False, logger=logger_teste) is True
    msgs = [r.message for r in caplog.records]
    assert any("já foi integrado" in m for m in msgs)
    assert any("Vídeo Antigo" in m for m in msgs)
    assert any("--forcar" in m for m in msgs)


def test_duplicado_com_forcar_nao_salta(logger_teste):
    historico = {"abc": {"titulo": "Vídeo Antigo"}}
    assert deve_saltar("abc", historico, forcar=True, logger=logger_teste) is False


def test_video_novo_nao_salta(logger_teste):
    assert deve_saltar("xyz", {}, forcar=False, logger=logger_teste) is False


def test_video_id_vazio_nao_salta(logger_teste):
    assert deve_saltar("", {"": {"titulo": "X"}}, forcar=False, logger=logger_teste) is False


def test_titulo_em_falta_usa_fallback(logger_teste, caplog):
    assert deve_saltar("abc", {"abc": {}}, forcar=False, logger=logger_teste) is True
    assert any("'Vídeo'" in r.message for r in caplog.records)


def test_historico_com_entrada_none_nao_rebenta(logger_teste, caplog):
    assert deve_saltar("abc", {"abc": None}, forcar=False, logger=logger_teste) is True
    assert any("'Vídeo'" in r.message for r in caplog.records)