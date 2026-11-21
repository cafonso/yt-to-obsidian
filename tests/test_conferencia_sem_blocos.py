from types import SimpleNamespace
import pytest
from analyzer import VideoAnalyzer


class _WriterSemEscrita:
    def __getattr__(self, nome):
        raise AssertionError(f"Não devia chamar '{nome}' do writer quando 'blocos' está vazio")


def _criar_analyzer_minimo() -> VideoAnalyzer:
    return VideoAnalyzer.__new__(VideoAnalyzer)


@pytest.mark.parametrize(
    "dados_video",
    [
        {"titulo": "Conferência sem legendas", "transcricao_blocos": []},
        {"titulo": "Conferência sem chave de blocos"},
    ],
)
def test_processar_conferencia_completa_sem_blocos_levanta_value_error(dados_video):
    analyzer = _criar_analyzer_minimo()
    agenda = SimpleNamespace(dia=1, dia_rotulo="Dia 1", sessoes=[])
    writer = _WriterSemEscrita()

    with pytest.raises(ValueError, match="Não é possível processar conferência sem transcrição"):
        analyzer.processar_conferencia_completa(dados_video, agenda, writer)