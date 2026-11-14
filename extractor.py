import re
import os
from typing import Optional, Dict, Any, List
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import yt_dlp

def extrair_id_youtube(url: str) -> Optional[str]:
    """Extrai o ID de 11 caracteres de URLs do YouTube."""
    padrao = r'(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/|^)([A-Za-z0-9_-]{11})'
    match = re.search(padrao, url)
    return match.group(1) if match else None

def formatar_tempo(segundos: float) -> str:
    """Converte segundos para formato [HH:MM:SS] ou [MM:SS]."""
    horas = int(segundos // 3600)
    minutos = int((segundos % 3600) // 60)
    segs = int(segundos % 60)
    if horas > 0:
        return f"[{horas:02d}:{minutos:02d}:{segs:02d}]"
    return f"[{minutos:02d}:{segs:02d}]"

class YouTubeExtractor:
    def __init__(self, idiomas_preferenciais: Optional[List[str]] = None):
        self.idiomas = idiomas_preferenciais or ['pt', 'pt-PT', 'pt-BR', 'en', 'en-US', 'es']

    def obter_metadados(self, url: str) -> Dict[str, Any]:
        """Recolhe título, canal, data e descrição via yt-dlp sem fazer download do vídeo."""
        opcoes = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'extract_flat': False
        }
        if os.path.exists("cookies.txt"):
            opcoes['cookiefile'] = "cookies.txt"

        with yt_dlp.YoutubeDL(opcoes) as ydl:
            info = ydl.extract_info(url, download=False)
            
            data_upload = info.get('upload_date') # Formato YYYYMMDD
            if data_upload and len(data_upload) == 8:
                data_formatada = f"{data_upload[:4]}-{data_upload[4:6]}-{data_upload[6:]}"
            else:
                data_formatada = "Desconhecida"

            return {
                "id": info.get("id"),
                "titulo": info.get("title", "Sem título"),
                "canal": info.get("uploader") or info.get("channel", "Desconhecido"),
                "canal_id": info.get("channel_id") or info.get("uploader_id", ""),
                "canal_url": info.get("uploader_url") or info.get("channel_url"),
                "data": data_formatada,
                "duracao_segundos": info.get("duration", 0),
                "url": info.get("webpage_url", url),
                "descricao": info.get("description", "")
            }

    def obter_transcricao(self, video_id: str) -> Optional[str]:
        """Tenta obter a transcrição de texto. Devolve None se falhar ou estiver bloqueada."""
        try:
            if hasattr(YouTubeTranscriptApi, 'get_transcript'):
                blocos = YouTubeTranscriptApi.get_transcript(video_id, languages=self.idiomas)
            else:
                api = YouTubeTranscriptApi()
                fetched = api.fetch(video_id, languages=self.idiomas)
                blocos = fetched.to_raw_data()
            
            linhas = []
            for b in blocos:
                timestamp = formatar_tempo(b['start'])
                texto = b['text'].replace('\n', ' ').strip()
                if texto:
                    linhas.append(f"{timestamp} {texto}")
            return "\n".join(linhas)

        except Exception:
            # Fallback secundário para legendas geradas automaticamente
            try:
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                for transcript in transcript_list:
                    blocos = transcript.fetch()
                    linhas = [f"{formatar_tempo(b['start'])} {b['text'].replace(chr(10), ' ').strip()}" for b in blocos]
                    return "\n".join(linhas)
            except Exception:
                return None

    def descarregar_audio(self, url: str, video_id: str) -> str:
        """Descarrega apenas o stream de áudio comprimido em formato leve (m4a)."""
        caminho_audio = f"temp_audio_{video_id}.m4a"
        opcoes = {
            'format': 'ba[ext=m4a]/ba',
            'outtmpl': caminho_audio,
            'quiet': True,
            'no_warnings': True,
        }
        if os.path.exists("cookies.txt"):
            opcoes['cookiefile'] = "cookies.txt"

        with yt_dlp.YoutubeDL(opcoes) as ydl:
            ydl.download([url])
        return caminho_audio

    def extrair_tudo(self, url: str) -> Dict[str, Any]:
        """Combina metadados e transcrição ou ativa o áudio fallback em caso de bloqueio."""
        video_id = extrair_id_youtube(url)
        if not video_id:
            raise ValueError(f"URL inválido do YouTube: {url}")
        
        metadados = self.obter_metadados(url)
        transcricao = self.obter_transcricao(video_id)
        caminho_audio = None

        if not transcricao:
            print("    ⚠️ Legendas de texto bloqueadas ou indisponíveis no YouTube.")
            print("    🎧 A descarregar áudio leve para análise direta pelo Gemini Flash...")
            caminho_audio = self.descarregar_audio(url, video_id)

        return {
            **metadados,
            "transcricao": transcricao,
            "caminho_audio": caminho_audio
        }
