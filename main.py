import os
import sys
import re
import json
import datetime
import argparse
from pathlib import Path
from typing import Optional

# Garante suporte a UTF-8 no terminal Windows para emojis e acentos
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config
from extractor import YouTubeExtractor, extrair_id_youtube
from analyzer import VideoAnalyzer
from vault_writer import ObsidianVaultWriter

DEFAULT_VAULT_PATH = config.DEFAULT_VAULT_PATH
HISTORICO_FILE = Path("historico_processados.json")


def carregar_historico() -> dict:
    if HISTORICO_FILE.exists():
        try:
            return json.loads(HISTORICO_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def gravar_historico(historico: dict):
    HISTORICO_FILE.write_text(json.dumps(historico, indent=2, ensure_ascii=False), encoding="utf-8")


def processar_um_video(
    url: str,
    extractor: YouTubeExtractor,
    analyzer: VideoAnalyzer,
    writer: ObsidianVaultWriter,
    forcar: bool = False,
    data_leitura: str = None,
    modo_conferencia: Optional[str] = None
) -> bool:
    if not data_leitura:
        data_leitura = datetime.date.today().isoformat()

    video_id = extrair_id_youtube(url)
    historico = carregar_historico()

    if not forcar and video_id and video_id in historico:
        titulo_antigo = historico[video_id].get("titulo", "Vídeo")
        print(f"⏭️ [Saltar] '{titulo_antigo}' já foi integrado no Obsidian. (Usa --forcar para reanalisar)")
        return True

    print(f"\n=======================================================")
    print(f"▶️ A processar: {url}")
    print(f"=======================================================")

    dados_video = None
    try:
        print("1/3 📥 A recolher metadados e transcrição do YouTube...")
        dados_video = extractor.extrair_tudo(url)
        print(f"    ✓ Título: {dados_video['titulo']}")
        print(f"    ✓ Canal: {dados_video['canal']}")
        if dados_video.get('transcricao'):
            print(f"    ✓ Transcrição: {len(dados_video['transcricao'].splitlines())} linhas")
        else:
            print("    ✓ Áudio capturado para processamento nativo")

        duracao = dados_video.get("duracao_segundos") or 0
        tem_transcricao = bool(dados_video.get("transcricao"))

        # ------------------------------------------------------------------
        # Deteção e Processamento de Conferências / Múltiplas Palestras (Scout)
        # ------------------------------------------------------------------
        deve_verificar_scout = (
            modo_conferencia == "split" or
            (modo_conferencia != "unico" and duracao > config.LIMIAR_VIDEO_LONGO_SEGUNDOS and tem_transcricao)
        )

        if deve_verificar_scout:
            print("2/3 🧭 Vídeo longo detetado. A executar 'The Scout' para mapear a agenda da conferência...")
            try:
                agenda = analyzer.executar_scout(dados_video)
                if agenda.eh_conferencia and len(agenda.sessoes) > 1:
                    dia_rotulo = agenda.dia_rotulo or f"Dia {agenda.dia or 1}"
                    print(f"    ✓ Conferência detetada: '{agenda.nome_conferencia}' ({dia_rotulo})")
                    print(f"    ✓ Total de palestras identificadas: {len(agenda.sessoes)}")

                    caminho_moc = analyzer.processar_conferencia_completa(dados_video, agenda, writer, data_leitura)

                    if video_id:
                        historico[video_id] = {
                            "titulo": f"{agenda.nome_conferencia} - {dia_rotulo}",
                            "canal": dados_video.get("canal"),
                            "url": url,
                            "data_leitura": data_leitura,
                            "nota": str(caminho_moc),
                            "tipo": "conferencia",
                            "total_palestras": len(agenda.sessoes)
                        }
                        gravar_historico(historico)

                    print("\n🎉 Conferência integrada com sucesso no Obsidian!")
                    return True
                else:
                    print("    ℹ️ O Scout determinou que este vídeo é um conteúdo contínuo (não é conferência de múltiplos oradores).")
            except Exception as e_scout:
                print(f"    ⚠️ Scout encontrou erro ({e_scout}). A prosseguir com o pipeline normal...")

        # ------------------------------------------------------------------
        # Pipeline Normal (Vídeos curtos ou monólogos longos consolidados)
        # ------------------------------------------------------------------
        print("2/3 🧠 A analisar com Gemini Flash (extração de pessoas, livros, temas)...")
        analise = analyzer.analisar(dados_video)
        print(f"    ✓ Título sugerido: {analise.titulo_sugerido}")
        print(f"    ✓ Pessoas identificadas: {len(analise.pessoas)}")
        print(f"    ✓ Obras/Livros citados: {len(analise.obras)}")
        print(f"    ✓ Organizações: {len(analise.organizacoes)}")
        print(f"    ✓ Artefactos: {len(analise.artefactos)}")
        print(f"    ✓ Temas: {len(analise.temas)}")
        if analise.capitulos:
            print(f"    ✓ Sessões/Capítulos: {len(analise.capitulos)}")

        print("3/3 📁 A gerar teia de notas no Obsidian Vault...")
        caminho_nota = writer.salvar_video(dados_video, analise, data_leitura)
        print(f"    ✓ Nota do vídeo criada em: {caminho_nota}")

        # Regista no histórico para não repetir custos de API desnecessários
        if video_id:
            historico[video_id] = {
                "titulo": analise.titulo_sugerido,
                "canal": dados_video.get("canal"),
                "url": url,
                "data_leitura": data_leitura,
                "nota": str(caminho_nota)
            }
            gravar_historico(historico)

        print("🎉 Concluído com sucesso!")
        return True

    except Exception as e:
        print(f"❌ Erro ao processar o vídeo {url}: {str(e)}")
        return False
    finally:
        # Garante que o áudio temporário é sempre apagado, mesmo em caso de erro
        if dados_video and dados_video.get("caminho_audio"):
            caminho_audio = dados_video["caminho_audio"]
            if os.path.exists(caminho_audio):
                try:
                    os.remove(caminho_audio)
                except Exception:
                    pass
def processar_ficheiro_lista(caminho_lista: str, extractor: YouTubeExtractor, analyzer: VideoAnalyzer, writer: ObsidianVaultWriter, forcar: bool = False):
    caminho = Path(caminho_lista)
    if not caminho.exists():
        print(f"❌ Erro: O ficheiro de lista '{caminho_lista}' não foi encontrado.")
        return

    PADRAO_DATA = re.compile(r'^#\s*(\d{4}-\d{2}-\d{2})\s*$')
    data_leitura_atual = datetime.date.today().isoformat()
    entradas = []
    erros_formato = 0

    try:
        linhas = caminho.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        print(f"❌ Erro ao ler o ficheiro '{caminho_lista}': {e}")
        return

    for num_linha, linha in enumerate(linhas, 1):
        linha = linha.strip()
        if not linha:
            continue
            
        match_data = PADRAO_DATA.match(linha)
        if match_data:
            data_str = match_data.group(1)
            # Validação simples da data
            try:
                datetime.date.fromisoformat(data_str)
                data_leitura_atual = data_str
                print(f"📅 Contexto de data alterado para: {data_leitura_atual}")
            except ValueError:
                print(f"⚠️ Aviso (linha {num_linha}): Data inválida encontrada '{data_str}'. A manter a anterior.")
            continue
            
        if linha.startswith("#"):
            # Comentário livre
            continue
            
        # Validar se a linha parece um URL válido do YouTube
        if extractor.validar_url_youtube(linha) or "youtube.com" in linha or "youtu.be" in linha:
            if extractor.validar_url_youtube(linha):
                entradas.append((linha, data_leitura_atual))
            else:
                erros_formato += 1
                print(f"⚠️ Aviso (linha {num_linha}): URL do YouTube aparentemente inválido ou incompleto -> '{linha}'")
        else:
            erros_formato += 1
            print(f"⚠️ Aviso (linha {num_linha}): Linha ignorada por não ser um URL nem um cabeçalho válido -> '{linha}'")

    total = len(entradas)
    print(f"\n📋 Foram validados com sucesso {total} vídeos para processar em lote. (Erros/Avisos ignorados: {erros_formato})\n")

    if total == 0:
        print("ℹ️ Nenhum URL válido encontrado para processar.")
        return

    sucessos = 0
    for idx, (url, data_leitura) in enumerate(entradas, 1):
        print(f"\n[{idx}/{total}]")
        if processar_um_video(url, extractor, analyzer, writer, forcar=forcar, data_leitura=data_leitura):
            sucessos += 1

    print(f"\n=======================================================")
    print(f"🏁 Processamento Concluído: {sucessos}/{total} vídeos integrados com sucesso!")
    print(f"=======================================================\n")
    
def mostrar_revisao_canonicalizacao():
    """Opção 5: mostra o conteúdo de revisao.md (pares ambíguos para confirmação manual)."""
    caminho = config.REVISAO_PATH
    if not caminho.exists():
        print("\n✓ Não há pares para revisão (revisao.md não existe ou está vazio).")
        return
    conteudo = caminho.read_text(encoding="utf-8").strip()
    if not conteudo:
        print("\n✓ revisao.md está vazio — nada para rever.")
        return
    print(f"\n📋 {caminho.resolve()}\n")
    print(conteudo)


def mostrar_config_canonicalizacao():
    """Opção 6: mostra os paths e thresholds usados pela canonicalização."""
    # Usa config se as variáveis existirem; senão recorre aos defaults do Canonicalizer.
    aliases = getattr(config, "ALIASES_PATH", "aliases.yaml")
    decisoes = getattr(config, "DECISOES_PATH", "decisoes.jsonl")
    revisao = getattr(config, "REVISAO_PATH", "revisao.md")
    thr_auto = getattr(config, "CANON_THRESHOLD_FUSAO_AUTO", 95)
    thr_rev = getattr(config, "CANON_THRESHOLD_REVISAO", 85)
    blocking = getattr(config, "CANON_BLOCKING_POR_ULTIMO_TOKEN", True)
    aprender = getattr(config, "CANON_APRENDER_ALIASES", True)

    print("\n📁 Canonicalização — configuração em uso:")
    print(f"   aliases:            {Path(aliases).resolve()}")
    print(f"   decisões (auditoria): {Path(decisoes).resolve()}")
    print(f"   revisão:            {Path(revisao).resolve()}")
    print(f"   threshold fusão:    {thr_auto}   (>= funde automaticamente)")
    print(f"   threshold revisão:  {thr_rev}   (entre este e o de fusão vai para revisao.md)")
    print(f"   blocking:           {'último token' if blocking else 'todos os canónicos'}")
    print(f"   aprender aliases:   {'sim' if aprender else 'não'}")

    # Indica também se os ficheiros já existem (útil para saber se já correu).
    print("\n📄 Estado dos ficheiros:")
    for rotulo, caminho in (("aliases", aliases), ("decisões", decisoes), ("revisão", revisao)):
        p = Path(caminho)
        estado = f"existe ({p.stat().st_size} bytes)" if p.exists() else "não existe"
        print(f"   {rotulo}: {estado}")


def menu_interativo(vault_path: str):
    extractor = YouTubeExtractor()
    analyzer = VideoAnalyzer()
    writer = ObsidianVaultWriter(vault_path)

    while True:
        print("\n" + "="*50)
        print("🧠 YOUTUBE TO OBSIDIAN KNOWLEDGE GRAPH")
        print("="*50)
        print(f"📂 Cofre Atual: {os.path.abspath(vault_path)}")
        print("1. Processar 1 vídeo por URL")
        print("2. Processar lista de vídeos (lista_de_videos.txt)")
        print("3. Processar outro ficheiro de links")
        print("4. Mudar pasta do Vault do Obsidian")
        print("5. Ver fila de revisão de canonicalização (revisao.md)")
        print("6. Ver configuração da canonicalização")
        print("0. Sair")
        print("="*50)

        opcao = input("Escolhe uma opção: ").strip()

        if opcao == "1":
            url = input("\nCola o link do YouTube: ").strip()
            if url:
                processar_um_video(url, extractor, analyzer, writer, forcar=True)
        elif opcao == "2":
            processar_ficheiro_lista("lista_de_videos.txt", extractor, analyzer, writer)
        elif opcao == "3":
            caminho = input("\nNome do ficheiro de texto: ").strip()
            if caminho:
                processar_ficheiro_lista(caminho, extractor, analyzer, writer)
        elif opcao == "4":
            novo_vault = input("\nNovo caminho para a pasta do teu Vault do Obsidian: ").strip()
            if novo_vault:
                vault_path = novo_vault
                writer = ObsidianVaultWriter(vault_path)
                print(f"✓ Caminho do Vault atualizado para: {os.path.abspath(vault_path)}")
        elif opcao == "5":
            mostrar_revisao_canonicalizacao()
        elif opcao == "6":
            mostrar_config_canonicalizacao()
        elif opcao == "0":
            print("\nAté breve!")
            break
        else:
            print("Opção inválida.")


def main():
    parser = argparse.ArgumentParser(description="Extrai conhecimento de vídeos do YouTube diretamente para o Obsidian.")
    parser.add_argument("url", nargs="?", help="URL do vídeo do YouTube a processar")
    parser.add_argument("--lista", "-l", help="Caminho para ficheiro .txt com lista de URLs")
    parser.add_argument("--vault", "-v", default=DEFAULT_VAULT_PATH, help="Caminho para a pasta do Vault do Obsidian")
    parser.add_argument("--forcar", "-f", action="store_true", help="Forçar reprocessamento mesmo se já estiver no histórico")
    parser.add_argument("--split", action="store_true", help="Forçar modo conferência (dividir em notas por palestra)")
    parser.add_argument("--unico", action="store_true", help="Forçar nota única consolidada mesmo se for vídeo longo")
    args = parser.parse_args()

    extractor = YouTubeExtractor()
    analyzer = VideoAnalyzer()
    writer = ObsidianVaultWriter(args.vault)

    modo_conf = "split" if args.split else ("unico" if args.unico else None)

    if args.url:
        processar_um_video(args.url, extractor, analyzer, writer, forcar=args.forcar, modo_conferencia=modo_conf)
    elif args.lista:
        processar_ficheiro_lista(args.lista, extractor, analyzer, writer, forcar=args.forcar)
    else:
        menu_interativo(args.vault)


if __name__ == "__main__":
    main()