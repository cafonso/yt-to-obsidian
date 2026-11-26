from pathlib import Path
from types import SimpleNamespace

import main
from models import PalestraAnalise, VideoCitado
from vault.conferencias import ConferenciasWriter
from vault.core import ObsidianVaultWriter
from vault.entidades import EntidadesWriter
from vault.videos import VideosWriter


def test_obsidian_vault_writer_expoe_especialistas_modulares(tmp_path: Path):
    writer = ObsidianVaultWriter(str(tmp_path), validar_links=False)

    assert isinstance(writer.entidades, EntidadesWriter)
    assert isinstance(writer.videos, VideosWriter)
    assert isinstance(writer.conferencias, ConferenciasWriter)


def test_palestra_conferencia_cria_nota_pessoa_para_orador_de_video_citado(tmp_path: Path):
    writer = ObsidianVaultWriter(str(tmp_path), validar_links=False)

    dados_video = {
        "id": "confVid001",
        "url": "https://youtu.be/confVid001",
        "titulo": "Conferência IA 2026",
        "data": "2026-11-25",
        "canal": "Canal Conf",
        "canal_url": "https://youtube.com/@canalconf",
    }
    agenda = SimpleNamespace(
        nome_conferencia="Conf IA 2026",
        dia=1,
        dia_rotulo="Dia 1",
        data_sessao="2026-11-25",
    )
    sessao = SimpleNamespace(
        ordem=1,
        titulo_palestra="Agentes Confiáveis",
        orador_principal="Carla Mendes",
        organizacao="Lab Norte",
        timestamp_inicio="00:05:00",
        timestamp_fim="00:35:00",
        segundos_inicio=300,
    )
    analise = PalestraAnalise(
        titulo_palestra="Agentes Confiáveis",
        resumo_executivo="Resumo da sessão.",
        takeaways_principais=["Takeaway 1"],
        videos_citados=[
            VideoCitado(
                titulo_ou_assunto="Benchmarking Agent Loops",
                canal_ou_orador="Henrique Rocha",
                url_ou_id=None,
                contexto="Referência metodológica",
            )
        ],
    )

    caminho_palestra = writer.salvar_palestra_conferencia(
        dados_video,
        agenda,
        sessao,
        analise,
        data_leitura="2026-11-25",
        historico={},
    )

    nota_pessoa = tmp_path / "Pessoas" / "Henrique Rocha.md"
    assert nota_pessoa.exists()
    conteudo_pessoa = nota_pessoa.read_text(encoding="utf-8")
    assert f"[[{caminho_palestra.stem}]]" in conteudo_pessoa
    assert "Benchmarking Agent Loops" in conteudo_pessoa


def test_menu_canonicalizacao_respeita_vault_path_ativo(tmp_path: Path, capsys):
    cofre_a = tmp_path / "CofreA"
    cofre_b = tmp_path / "CofreB"
    (cofre_a / ".canonicalizacao").mkdir(parents=True)
    (cofre_b / ".canonicalizacao").mkdir(parents=True)

    (cofre_a / ".canonicalizacao" / "revisao.md").write_text(
        "# Revisão de canonicalização\n\n- **pessoa**: `Ana S.` → `Ana Silva` (score 90, método fuzzy)\n",
        encoding="utf-8",
    )

    main.mostrar_revisao_canonicalizacao(cofre_a)
    saida_a = capsys.readouterr().out
    assert "Ana Silva" in saida_a

    main.mostrar_revisao_canonicalizacao(cofre_b)
    saida_b = capsys.readouterr().out
    assert "Não há pares para revisão" in saida_b

    main.mostrar_config_canonicalizacao(cofre_b)
    saida_cfg = capsys.readouterr().out
    assert str((cofre_b / ".canonicalizacao" / "aliases.yaml").resolve()) in saida_cfg