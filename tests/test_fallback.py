import pytest
from analyzer import VideoAnalyzer


def _criar_analyzer_sem_init(fallback_model: str | None) -> VideoAnalyzer:
    analyzer = VideoAnalyzer.__new__(VideoAnalyzer)
    analyzer.fallback_model = fallback_model
    return analyzer


def test_chamar_com_fallback_usa_fallback_quando_principal_falha():
    analyzer = _criar_analyzer_sem_init("gemini-fallback")
    chamadas = []

    def fake_retry(modelo, conteudos, config_obj):
        chamadas.append(modelo)
        if modelo == "gemini-principal":
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return "resposta_ok"

    analyzer._chamar_gemini_com_retry = fake_retry

    resultado = analyzer._chamar_com_fallback("gemini-principal", ["prompt"], None)

    assert resultado == "resposta_ok"
    assert chamadas == ["gemini-principal", "gemini-fallback"]


def test_chamar_com_fallback_preserva_ambos_erros_quando_ambos_falham():
    analyzer = _criar_analyzer_sem_init("gemini-fallback")

    def fake_retry(modelo, conteudos, config_obj):
        if modelo == "gemini-principal":
            raise RuntimeError("429 quota excedida")
        raise ValueError("404 modelo invalido")

    analyzer._chamar_gemini_com_retry = fake_retry

    with pytest.raises(RuntimeError) as exc_info:
        analyzer._chamar_com_fallback("gemini-principal", ["prompt"], None)

    mensagem = str(exc_info.value)
    assert "gemini-principal" in mensagem
    assert "429 quota excedida" in mensagem
    assert "gemini-fallback" in mensagem
    assert "404 modelo invalido" in mensagem
    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_chamar_com_fallback_propaga_erro_original_sem_fallback():
    analyzer = _criar_analyzer_sem_init(None)

    def fake_retry(modelo, conteudos, config_obj):
        raise ValueError("erro original")

    analyzer._chamar_gemini_com_retry = fake_retry

    with pytest.raises(ValueError, match="erro original"):
        analyzer._chamar_com_fallback("gemini-principal", ["prompt"], None)