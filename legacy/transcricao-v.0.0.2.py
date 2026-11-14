import re
import os
import json
import time  # <--- IMPORTANTE: Adicionado para gerar os atrasos
import random # <--- IMPORTANTE: Adicionado para tornar os atrasos imprevisíveis
from yt_dlp import YoutubeDL
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

def extrair_metadados(url: str) -> dict:
    """Extrai os metadados principais usando yt-dlp simulando um utilizador real."""
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'js_runtimes': {'node': {}},
        
        # --- ESTRATÉGIAS ANTIBLOQUEIO ---
        # 1. Extrair os cookies diretamente do seu navegador (Altere 'chrome' se usar outro navegador)
        'cookiesfrombrowser': ('chrome','Default'), 
        
        # 2. Forçar clientes mais discretos que o YouTube costuma bloquear menos
        'extractor_args': {'youtube': {'player_client': ['web', 'ios']}},
        
        # 3. Cabeçalhos HTTP básicos simulando um browser comum
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'pt-PT,pt;q=0.9,en;q=0.8',
        }
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'titulo': info.get('title', 'N/A'),
                'canal': info.get('uploader', 'N/A'),
                'canal_id': info.get('channel_id', 'N/A'),
                'data_publicacao': info.get('upload_date', 'N/A'),
                'descricao': info.get('description', 'Sem descrição.')
            }
    except Exception as e:
        print(f"-> Aviso: Não foi possível obter os metadados: {str(e)}")
        return None

def exportar_dados_video(url: str, idiomas=None) -> bool:
    """Obtém metadados e transcrição de um vídeo e grava em .txt."""
    if idiomas is None:
        idiomas = ['en']
        
    video_id = extrair_id_youtube(url)
    if not video_id:
        print(f"-> Erro: URL inválido: '{url}'")
        return False

    # 1. Obter Metadados primeiro
    print("A obter os metadados do YouTube...")
    metadados = extrair_metadados(url)

    # 2. Obter Transcrição
    blocos = None
    try:
        print("A obter a transcrição do YouTube...")
        if hasattr(YouTubeTranscriptApi, 'get_transcript'):
            blocos = YouTubeTranscriptApi.get_transcript(video_id, languages=idiomas)
        else:
            api = YouTubeTranscriptApi()
            fetched = api.fetch(video_id, languages=idiomas)
            blocos = fetched.to_raw_data()
    except TranscriptsDisabled:
        print(f"-> Erro: Legendas desativadas para o vídeo {video_id}")
    except NoTranscriptFound:
        print(f"-> Erro: Transcrição não encontrada nos idiomas {idiomas} para o vídeo {video_id}")
    except Exception as e:
        print(f"-> Erro inesperado ao obter transcrição do vídeo {video_id}: {str(e)}")

    # Se não conseguiu metadados nem transcrição, cancela a gravação
    if not metadados and not blocos:
        return False

    # 3. Gravar tudo no Ficheiro de Texto
    nome_ficheiro = f"transcricao_{video_id}.txt"
    try:
        with open(nome_ficheiro, "w", encoding="utf-8") as ficheiro:
            ficheiro.write("=== METADADOS DO VÍDEO ===\n")
            if metadados:
                ficheiro.write(f"Título: {metadados['titulo']}\n")
                ficheiro.write(f"Canal: {metadados['canal']} (ID: {metadados['canal_id']})\n")
                data = metadados['data_publicacao']
                data_formatada = f"{data[:4]}-{data[4:6]}-{data[6:]}" if len(data) == 8 else data
                ficheiro.write(f"Data de Publicação: {data_formatada}\n")
                ficheiro.write(f"Link: https://youtube.com{video_id}\n")
                ficheiro.write(f"\n--- Descrição ---\n{metadados['descricao']}\n")
            else:
                ficheiro.write("Não foi possível extrair os metadados para este vídeo.\n")
                
            ficheiro.write("\n===========================\n")
            ficheiro.write("=== TRANSCRIÇÃO ===\n\n")

            if blocos:
                video_longo = blocos[-1]['start'] >= 3600 if blocos else False
                for bloco in blocos:
                    tempo = formatar_tempo(bloco['start'], longo=video_longo)
                    texto = bloco['text'].replace('\n', ' ')
                    ficheiro.write(f"{tempo} {texto}\n")
            else:
                ficheiro.write("[Transcrição indisponível ou não encontrada nos idiomas selecionados]\n")
                
        print(f"-> Sucesso! Guardado em: {os.path.abspath(nome_ficheiro)}")
        return True
    except Exception as e:
        print(f"-> Erro ao gravar o ficheiro para o vídeo {video_id}: {str(e)}")
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
        if exportar_dados_video(link, idiomas):
            sucessos += 1
            
        # --- PAUSA ALEATÓRIA ENTRE VÍDEOS ---
        # Se ainda houver mais vídeos na lista, espera entre 4 a 9 segundos
        if i < len(links):
            atraso = random.uniform(4.0, 9.0)
            print(f"A aguardar {atraso:.1f} segundos para evitar bloqueios...")
            time.sleep(atraso)
            print("-" * 30)
            
    print(f"\n=== Tarefa Concluída: {sucessos}/{len(links)} ficheiros gerados com sucesso! ===")

# --- Execução com Menu de Opções ---
if __name__ == "__main__":
    print("=== EXTRATOR DE TRANSCRIÇÕES E METADADOS DO YOUTUBE ===")
    print("1. Processar apenas UM link")
    print("2. Processar uma LISTA de links a partir de um ficheiro .txt")
    
    opcao = input("\nEscolha uma opção (1 ou 2): ").strip()
    
    # Dica: Pode mudar para ['pt', 'en'] se quiser dar prioridade a português
    idiomas_padrao = ['en'] 

    if opcao == "1":
        url_video = input("Insira o endereço do vídeo do YouTube: ").strip()
        print()
        exportar_dados_video(url_video, idiomas=idiomas_padrao)
        
    elif opcao == "2":
        print("\nNota: Crie um ficheiro de texto (ex: links.txt) com um link do YouTube por linha.")
        nome_txt = input("Insira o nome ou caminho do ficheiro (ex: links.txt): ").strip()
        processar_ficheiro_links(nome_txt, idiomas=idiomas_padrao)
        
    else:
        print("Opção inválida. A terminar o programa.")
