import os
import sys
import re
import json
import datetime
import argparse
from pathlib import Path

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

def processar_um_video(url: str, extractor: YouTubeExtractor, analyzer: VideoAnalyzer, writer: ObsidianVaultWriter, forcar: bool = False, data_leitura: str = None) -> bool:
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
    
    try:
        print("1/3 📥 A recolher metadados e transcrição do YouTube...")
        dados_video = extractor.extrair_tudo(url)
        print(f"    ✓ Título: {dados_video['titulo']}")
        print(f"    ✓ Canal: {dados_video['canal']}")
        if dados_video.get('transcricao'):
            print(f"    ✓ Transcrição: {len(dados_video['transcricao'].splitlines())} linhas")
        else:
            print("    ✓ Áudio capturado para processamento nativo")

        print("2/3 🧠 A analisar com Gemini Flash (extração de pessoas, livros, temas)...")
        analise = analyzer.analisar(dados_video)
        print(f"    ✓ Título sugerido: {analise.titulo_sugerido}")
        print(f"    ✓ Pessoas identificadas: {len(analise.pessoas)}")
        print(f"    ✓ Obras/Livros citados: {len(analise.obras)}")
        print(f"    ✓ Temas: {len(analise.temas)}")

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

def processar_ficheiro_lista(caminho_lista: str, extractor: YouTubeExtractor, analyzer: VideoAnalyzer, writer: ObsidianVaultWriter, forcar: bool = False):
    if not os.path.exists(caminho_lista):
        print(f"Erro: O ficheiro '{caminho_lista}' não foi encontrado.")
        return

    # Parser que suporta cabeçalhos de data: # YYYY-MM-DD
    # Todos os outros comentários (# texto livre) são ignorados normalmente.
    PADRAO_DATA = re.compile(r'^#\s*(\d{4}-\d{2}-\d{2})\s*$')
    data_leitura_atual = datetime.date.today().isoformat()  # default: hoje
    entradas = []  # lista de (url, data_leitura)

    with open(caminho_lista, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            match_data = PADRAO_DATA.match(linha)
            if match_data:
                # Cabeçalho de data — atualiza o contexto temporal
                data_leitura_atual = match_data.group(1)
                print(f"📅 Contexto de data alterado para: {data_leitura_atual}")
            elif linha.startswith("#"):
                # Comentário livre — ignora
                continue
            else:
                entradas.append((linha, data_leitura_atual))

    total = len(entradas)
    print(f"\n📋 Foram encontrados {total} vídeos para processar em lote.\n")

    sucessos = 0
    for idx, (url, data_leitura) in enumerate(entradas, 1):
        print(f"\n[{idx}/{total}]")
        if processar_um_video(url, extractor, analyzer, writer, forcar=forcar, data_leitura=data_leitura):
            sucessos += 1

    print(f"\n=======================================================")
    print(f"🏁 Processamento Concluído: {sucessos}/{total} vídeos verificados/integrados no Obsidian!")
    print(f"=======================================================\n")

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
    args = parser.parse_args()

    extractor = YouTubeExtractor()
    analyzer = VideoAnalyzer()
    writer = ObsidianVaultWriter(args.vault)

    if args.url:
        processar_um_video(args.url, extractor, analyzer, writer, forcar=args.forcar)
    elif args.lista:
        processar_ficheiro_lista(args.lista, extractor, analyzer, writer, forcar=args.forcar)
    else:
        menu_interativo(args.vault)

if __name__ == "__main__":
    main()
