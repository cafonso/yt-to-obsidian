import main


def test_menu_interativo_opcao1_usa_forcar_false_por_defeito(monkeypatch):
    entradas = iter(["1", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "0"])
    chamadas = []

    monkeypatch.setattr("builtins.input", lambda _="": next(entradas))

    for attr in ("YouTubeExtractor", "VideoAnalyzer", "ObsidianVaultWriter", "ObsidianWriter"):
        if hasattr(main, attr):
            monkeypatch.setattr(main, attr, lambda *args, **kwargs: object())

    if hasattr(main, "carregar_historico"):
        monkeypatch.setattr(main, "carregar_historico", lambda *args, **kwargs: {})

    monkeypatch.setattr(
        main,
        "processar_um_video",
        lambda url, *args, **kwargs: chamadas.append(
            {
                "url": url,
                "forcar": kwargs.get("forcar"),
                "vault_path": kwargs.get("vault_path"),
                "args": args,
            }
        ),
    )

    main.menu_interativo(vault_path="D:\\Obsidian Files")

    assert len(chamadas) == 1
    assert chamadas[0]["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert chamadas[0]["forcar"] is False