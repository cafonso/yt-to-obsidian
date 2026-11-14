import re
import os
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

def extrair_id_youtube(url: str) -> str:
    """Extrai o ID do vídeo de diferentes formatos de URL do YouTube."""
    padrao = r'(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/|^)([A-Za-z0-9_-]{11})'
    resultado = re.search(padrao, url)
    return resultado.group(1) if resultado else None

def formatar_tempo(segundos: float, longo: bool) -> str:
    """Converte segundos para [HH:MM:SS] (se longo) ou [MM:SS] (se curto)."""
    horas = int(segundos // 3600)
    minutos = int((segundos % 3600) // 60)
    segs = int(segundos % 60)
    
    if longo:
        return f"[{horas:02d}:{minutos:02d}:{segs:02d}]"
    return f"[{minutos:02d}:{segs:02d}]"

def exportar_transcricao(url: str, idiomas=None) -> bool:
    """Obtém a transcrição de um vídeo e grava em .txt. Retorna True se tiver sucesso."""
    if idiomas is None:
        idiomas = ['en']
        
    video_id = extrair_id_youtube(url)
    if not video_id:
        print(f"-> Erro: URL inválido: '{url}'")
        return False

    try:
        print("A obter a transcrição do YouTube...")
        # Suporte universal: versões recentes (>= 1.0.0 com api.fetch) e versões legadas (< 1.0.0 com get_transcript)
        if hasattr(YouTubeTranscriptApi, 'get_transcript'):
            blocos = YouTubeTranscriptApi.get_transcript(video_id, languages=idiomas)
        else:
            api = YouTubeTranscriptApi()
            fetched = api.fetch(video_id, languages=idiomas)
            blocos = fetched.to_raw_data()
        
        video_longo = blocos[-1]['start'] >= 3600 if blocos else False
        nome_ficheiro = f"transcricao_{video_id}.txt"
        
        with open(nome_ficheiro, "w", encoding="utf-8") as ficheiro:
            for bloco in blocos:
                tempo = formatar_tempo(bloco['start'], longo=video_longo)
                texto = bloco['text'].replace('\n', ' ')
                ficheiro.write(f"{tempo} {texto}\n")
                
        print(f"-> Sucesso! Guardado em: {os.path.abspath(nome_ficheiro)}")
        return True

    except TranscriptsDisabled:
        print(f"-> Erro: Legendas desativadas para o vídeo {video_id}")
    except NoTranscriptFound:
        print(f"-> Erro: Transcrição não encontrada nos idiomas {idiomas} para o vídeo {video_id}")
    except Exception as e:
        print(f"-> Erro inesperado no vídeo {video_id}: {str(e)}")
    return False

def processar_ficheiro_links(caminho_ficheiro, idiomas=None):
    """Lê um ficheiro de texto e processa todos os links válidos encontrados."""
    if not os.path.exists(caminho_ficheiro):
        print(f"Erro: O ficheiro '{caminho_ficheiro}' não foi encontrado.")
        return

    with open(caminho_ficheiro, "r", encoding="utf-8") as f:
        links = [linha.strip() for linha in f.readlines() if linha.strip()]

    print(f"\nForam encontrados {len(links)} links para processar.\n")
    
    sucessos = 0
    for i, link in enumerate(links, 1):
        print(f"[{i}/{len(links)}] A processar: {link}")
        if exportar_transcricao(link, idiomas):
            sucessos += 1
            
    print(f"\n=== Tarefa Concluída: {sucessos}/{len(links)} transcrições obtidas com sucesso! ===")

# --- Execução com Menu de Opções ---
if __name__ == "__main__":
    print("=== EXTRATOR DE TRANSCRIÇÕES DO YOUTUBE ===")
    print("1. Processar apenas UM link")
    print("2. Processar uma LISTA de links a partir de um ficheiro .txt")
    
    opcao = input("\nEscolha uma opção (1 ou 2): ").strip()
    
    idiomas_padrao = ['en'] 

    if opcao == "1":
        url_video = input("Insira o endereço do vídeo do YouTube: ").strip()
        print()
        exportar_transcricao(url_video, idiomas=idiomas_padrao)
        
    elif opcao == "2":
        print("\nNota: Crie um ficheiro de texto (ex: links.txt) com um link do YouTube por linha.")
        nome_txt = input("Insira o nome ou caminho do ficheiro (ex: links.txt): ").strip()
        processar_ficheiro_links(nome_txt, idiomas=idiomas_padrao)
        
    else:
        print("Opção inválida. A terminar o programa.")
