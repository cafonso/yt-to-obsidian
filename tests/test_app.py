import inspect
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from main import _resolver_caminho_historico, carregar_historico


class _DummyCtx:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeStreamlit:
    """Stub mínimo do Streamlit para executar app.py em testes sem servidor UI."""

    def __init__(self, vault_dir: Path, urls_input: str = "", clicar_iniciar: bool = False):
        self.vault_dir = str(vault_dir)
        self.urls_input = urls_input
        self.clicar_iniciar = clicar_iniciar
        self.sidebar = _DummyCtx()
        self.infos = []
        self.successes = []
        self.warnings = []
        self.errors = []
        self.dataframes = []

    def set_page_config(self, **kwargs):
        pass

    def header(self, *args, **kwargs):
        pass

    def title(self, *args, **kwargs):
        pass

    def subheader(self, *args, **kwargs):
        pass

    def caption(self, *args, **kwargs):
        pass

    def divider(self):
        pass

    def markdown(self, *args, **kwargs):
        pass

    def metric(self, *args, **kwargs):
        pass

    def text_input(self, label, value="", **kwargs):
        if "Vault" in label:
            return self.vault_dir
        return value

    def date_input(self, label, value=None, **kwargs):
        return value

    def selectbox(self, label, options, index=0, **kwargs):
        return options[index]

    def checkbox(self, label, value=False, **kwargs):
        return value

    def text_area(self, label, **kwargs):
        return self.urls_input

    def columns(self, spec):
        n = len(spec) if isinstance(spec, (list, tuple)) else int(spec)
        return [_DummyCtx() for _ in range(n)]

    def tabs(self, labels):
        return [_DummyCtx() for _ in labels]

    def button(self, label, **kwargs):
        if "Iniciar" in label:
            return self.clicar_iniciar
        return False

    def progress(self, *args, **kwargs):
        return SimpleNamespace(progress=lambda *a, **k: None)

    def empty(self):
        return SimpleNamespace(
            code=lambda *a, **k: None,
            info=lambda msg: self.infos.append(msg),
            success=lambda msg: self.successes.append(msg),
            warning=lambda msg: self.warnings.append(msg),
        )

    def info(self, msg):
        self.infos.append(msg)

    def success(self, msg):
        self.successes.append(msg)

    def warning(self, msg):
        self.warnings.append(msg)

    def error(self, msg):
        self.errors.append(msg)

    def dataframe(self, data, **kwargs):
        self.dataframes.append(data)

    def rerun(self):
        pass


def test_carregar_historico_exige_caminho():
    sig = inspect.signature(carregar_historico)
    assert "caminho_historico" in sig.parameters
    with pytest.raises(TypeError):
        carregar_historico()


def test_app_usa_vault_path_da_sidebar_em_todas_as_abas(tmp_path: Path, monkeypatch):
    vault_custom = tmp_path / "VaultCustom"
    vault_custom.mkdir()

    # Prepara um ficheiro de histórico no cofre customizado
    hist_path = _resolver_caminho_historico(str(vault_custom))
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    hist_path.write_text(
        '{"abc123def45": {"titulo": "Vídeo Teste", "canal": "Canal", "data_leitura": "2026-11-22"}}',
        encoding="utf-8",
    )

    fake_st = _FakeStreamlit(
        vault_dir=vault_custom,
        urls_input="https://www.youtube.com/watch?v=abc123def45",
        clicar_iniciar=True,
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    chamadas_processar = []

    def fake_processar_um_video(**kwargs):
        chamadas_processar.append(kwargs)
        return True

    import main as main_mod
    import analyzer as analyzer_mod
    import extrator as extrator_mod

    vault_passado_ao_analyzer = []

    def fake_video_analyzer(vault_path=None, **kwargs):
        vault_passado_ao_analyzer.append(vault_path)
        return SimpleNamespace(estado_pipeline=SimpleNamespace(carregar=lambda _d: None))

    monkeypatch.setattr(main_mod, "processar_um_video", fake_processar_um_video)
    monkeypatch.setattr(extrator_mod, "YouTubeExtractor", lambda: object())
    monkeypatch.setattr(analyzer_mod, "VideoAnalyzer", fake_video_analyzer)

    app_file = Path(__file__).resolve().parent.parent / "app.py"
    runpy.run_path(str(app_file), run_name="__main__")

    # 1. Verifica se VideoAnalyzer recebeu o vault_path da sidebar
    assert len(vault_passado_ao_analyzer) == 1
    assert str(vault_passado_ao_analyzer[0]) == str(vault_custom)

    # 2. Verifica se processar_um_video recebeu o vault_path da sidebar
    assert len(chamadas_processar) == 1
    assert chamadas_processar[0]["vault_path"] == str(vault_custom)

    # 3. Verifica se a aba Histórico carregou o registo do cofre customizado sem TypeError
    assert len(fake_st.dataframes) == 1
    assert fake_st.dataframes[0][0]["ID"] == "abc123def45"