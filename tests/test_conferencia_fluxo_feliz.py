from pathlib import Path

from analyzer import VideoAnalyzer
from models import AgendaScout, PalestraAnalise, SessaoScout


class _WriterFake:
    """Simula o ObsidianVaultWriter para validar chamadas sem depender de detalhes internos."""

    def __init__(self, vault_dir: Path) -> None:
        self.vault_dir = vault_dir
        self.palestras_salvas: list[tuple[str, str, int]] = []
        self.moc_chamado: tuple[str, int] | None = None

    def salvar_palestra_conferencia(
        self,
        dados_video: dict,
        agenda: AgendaScout,
        sessao: SessaoScout,
        analise: PalestraAnalise,
        data_leitura: str | None = None,
    ) -> Path:
        self.palestras_salvas.append(
            (sessao.titulo_palestra, analise.titulo_palestra, sessao.segundos_inicio)
        )
        pasta = self.vault_dir / "Videos" / agenda.nome_conferencia
        pasta.mkdir(parents=True, exist_ok=True)
        caminho = pasta / f"palestra_{sessao.segundos_inicio}.md"
        caminho.write_text(f"# {analise.titulo_palestra}\n", encoding="utf-8")
        return caminho

    def salvar_ou_atualizar_moc_conferencia(
        self,
        dados_video: dict,
        agenda: AgendaScout,
        palestras_processadas: list[dict],
        data_leitura: str | None = None,
    ) -> Path:
        self.moc_chamado = (agenda.nome_conferencia, len(palestras_processadas))
        caminho_moc = self.vault_dir / "Videos" / agenda.nome_conferencia / "MOC.md"
        caminho_moc.write_text("# MOC\n", encoding="utf-8")
        return caminho_moc


def test_processar_conferencia_completa_fluxo_feliz(tmp_path: Path, monkeypatch) -> None:
    analyzer = VideoAnalyzer(vault_path=tmp_path)
    writer = _WriterFake(tmp_path)

    dados_video = {
        "video_id": "abc123XYZ09",
        "titulo": "AI Engineer Summit 2026 - Dia 1",
        "canal": "AI Engineer",
        "duracao_segundos": 3600,
        "transcricao_blocos": [
            {"start": 0.0, "duration": 900.0, "text": "Introdução e keynote sobre agentes."},
            {"start": 900.0, "duration": 900.0, "text": "Avaliação de sistemas LLM em produção."},
            {"start": 1800.0, "duration": 900.0, "text": "Encerramento e perguntas."},
        ],
    }

    sessoes = [
        SessaoScout(
            ordem=1,
            timestamp_inicio="[00:00:00]",
            segundos_inicio=0,
            timestamp_fim="[00:15:00]",
            segundos_fim=900,
            orador_principal="Ana Silva",
            organizacao="Lab IA",
            titulo_palestra="Agents in Production",
            tipo_sessao="keynote",
        ),
        SessaoScout(
            ordem=2,
            timestamp_inicio="[00:15:00]",
            segundos_inicio=900,
            timestamp_fim="[00:30:00]",
            segundos_fim=1800,
            orador_principal="Bruno Costa",
            organizacao="Tech Corp",
            titulo_palestra="Evals That Actually Matter",
            tipo_sessao="palestra",
        ),
    ]

    agenda = AgendaScout(
        nome_conferencia="AI Engineer Summit 2026",
        dia=1,
        dia_rotulo="Dia 1",
        data_sessao="2026-11-23",
        eh_conferencia=True,
        sessoes=sessoes,
    )

    def fake_analisar_palestra(
        agenda_arg: AgendaScout,
        sessao_arg: SessaoScout,
        texto_fatia: str,
        canon,
    ) -> PalestraAnalise:
        return PalestraAnalise(
            titulo_palestra=sessao_arg.titulo_palestra,
            resumo_executivo="Resumo de teste da palestra.",
            takeaways_principais=["Ponto-chave 1", "Ponto-chave 2"],
        )

    monkeypatch.setattr(analyzer, "analisar_palestra", fake_analisar_palestra)

    resultado = analyzer.processar_conferencia_completa(
        dados_video=dados_video,
        agenda=agenda,
        writer=writer,
        data_leitura="2026-11-23",
    )

    assert len(writer.palestras_salvas) == 2
    assert writer.palestras_salvas[0] == ("Agents in Production", "Agents in Production", 0)
    assert writer.palestras_salvas[1] == ("Evals That Actually Matter", "Evals That Actually Matter", 900)
    assert writer.moc_chamado == ("AI Engineer Summit 2026", 2)
    assert Path(resultado).exists()