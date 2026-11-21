from pathlib import Path
from types import SimpleNamespace
import main


def test_processar_ficheiro_lista_passa_modo_conferencia(tmp_path: Path, monkeypatch):
    lista = tmp_path / "lista.txt"
    lista.write_text("https://www.youtube.com/watch?v=dQw4w9WgXcQ\n", encoding="utf-8")

    chamadas = []

    def fake_processar_um_video(url, extrator, analyzer, writer, **kwargs):
        chamadas.append({"url": url, "kwargs": kwargs})
        return True

    monkeypatch.setattr(main, "processar_um_video", fake_processar_um_video)

    fake_extrator = SimpleNamespace(validar_url_youtube=lambda url: True)

    main.processar_ficheiro_lista(
        str(lista),
        extrator=fake_extrator,
        analyzer=object(),
        writer=object(),
        forcar=False,
        modo_conferencia="split",
        vault_path=str(tmp_path),
    )

    assert len(chamadas) == 1
    assert chamadas[0]["kwargs"]["modo_conferencia"] == "split"