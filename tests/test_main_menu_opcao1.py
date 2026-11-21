import main


def _preparar_menu(monkeypatch, entradas, chamadas, historico=None, video_id="dQw4w9WgXcQ"):
    it = iter(entradas)
    monkeypatch.setattr("builtins.input", lambda _="": next(it))

    for attr in ("YouTubeExtractor", "VideoAnalyzer", "ObsidianVaultWriter", "ObsidianWriter"):
        if hasattr(main, attr):
            monkeypatch.setattr(main, attr, lambda *args, **kwargs: object())

    if hasattr(main, "extrair_id_youtube"):
        monkeypatch.setattr(main, "extrair_id_youtube", lambda _url: video_id)

    if hasattr(main, "_resolver_caminho_historico"):
        monkeypatch.setattr(main, "_resolver_caminho_historico", lambda _vault: "historico.json")

    if hasattr(main, "carregar_historico"):
        monkeypatch.setattr(main, "carregar_historico", lambda _path: historico or {})

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


def test_menu_interativo_opcao1_reprocessa_quando_responde_sim(monkeypatch):
    video_id = "dQw4w9WgXcQ"
    url = f"https://www.youtube.com/watch?v={video_id}"
    chamadas = []

    _preparar_menu(
        monkeypatch,
        entradas=["1", url, "sim", "0"],
        chamadas=chamadas,
        historico={video_id: {"titulo": "Vídeo Existente"}},
        video_id=video_id,
    )

    main.menu_interativo(vault_path="D:\\Obsidian Files")

    assert len(chamadas) == 1
    assert chamadas[0]["url"] == url
    assert chamadas[0]["forcar"] is True


def test_menu_interativo_opcao1_nao_forca_quando_responde_n(monkeypatch):
    video_id = "dQw4w9WgXcQ"
    url = f"https://www.youtube.com/watch?v={video_id}"
    chamadas = []

    _preparar_menu(
        monkeypatch,
        entradas=["1", url, "n", "0"],
        chamadas=chamadas,
        historico={video_id: {"titulo": "Vídeo Existente"}},
        video_id=video_id,
    )

    main.menu_interativo(vault_path="D:\\Obsidian Files")

    assert len(chamadas) == 1
    assert chamadas[0]["url"] == url
    assert chamadas[0]["forcar"] is False