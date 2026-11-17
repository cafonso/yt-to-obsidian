import re
import os
from typing import Optional, Dict, Any, List
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import yt_dlp
import subprocess
import glob
import config

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
                "canal_url": info.get('uploader_url') or info.get('channel_url'),
                "data": data_formatada,
                "duracao_segundos": info.get("duration", 0),
                "url": info.get("webpage_url", url),
                "descricao": info.get("description", ""),
                "capitulos_originais": info.get("chapters") or []
            }
    def fatiar_audio(self, caminho_audio: str, duracao_chunk: int = None) -> List[Dict[str, Any]]:
        """
        Divide um ficheiro .m4a longo em segmentos usando ffmpeg (-c copy, sem re-encoding).
        Devolve uma lista de dicionários compatível com o pipeline Map-Reduce.
        """
        if duracao_chunk is None:
            duracao_chunk = config.DURACAO_CHUNK_SEGUNDOS

        base_nome = os.path.splitext(caminho_audio)[0]
        padrao_saida = f"{base_nome}_part_%03d.m4a"

        cmd = [
            "ffmpeg",
            "-y",
            "-i", caminho_audio,
            "-f", "segment",
            "-segment_time", str(duracao_chunk),
            "-c", "copy",
            "-reset_timestamps", "1",
            padrao_saida
        ]

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        ficheiros_partes = sorted(glob.glob(f"{base_nome}_part_*.m4a"))
        segmentos = []
        for idx, ficheiro in enumerate(ficheiros_partes):
            inicio_s = idx * duracao_chunk
            fim_s = (idx + 1) * duracao_chunk
            segmentos.append({
                "ts_inicio": formatar_tempo(inicio_s),
                "ts_fim": formatar_tempo(fim_s),
                "titulo_sugerido": None,
                "texto": None,
                "caminho_audio_chunk": ficheiro
            })

        return segmentos
    def obter_transcricao_blocos(self, video_id: str) -> Optional[List[Dict[str, Any]]]:
        """Tenta obter os blocos brutos da transcrição (start, duration, text)."""
        blocos = None
        # Tentativa 1: get_transcript legado ou api.fetch direta
        try:
            if hasattr(YouTubeTranscriptApi, 'get_transcript'):
                blocos = YouTubeTranscriptApi.get_transcript(video_id, languages=self.idiomas)
            else:
                api = YouTubeTranscriptApi()
                fetched = api.fetch(video_id, languages=self.idiomas)
                blocos = fetched.to_raw_data()
        except Exception:
            pass

        # Tentativa 2: listar transcrições disponíveis (incluindo auto-geradas)
        if not blocos:
            try:
                if hasattr(YouTubeTranscriptApi, 'list_transcripts'):
                    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                else:
                    api = YouTubeTranscriptApi()
                    transcript_list = api.list(video_id)

                for idioma in self.idiomas:
                    try:
                        t = transcript_list.find_transcript([idioma])
                        fetched = t.fetch()
                        blocos = fetched.to_raw_data() if hasattr(fetched, 'to_raw_data') else fetched
                        break
                    except Exception:
                        continue

                if not blocos:
                    for t in transcript_list:
                        fetched = t.fetch()
                        blocos = fetched.to_raw_data() if hasattr(fetched, 'to_raw_data') else fetched
                        break
            except Exception:
                pass

        if not blocos:
            return None

        blocos_limpos = []
        for b in blocos:
            texto = b.get('text', '').replace('\n', ' ').strip()
            if texto:
                blocos_limpos.append({
                    'start': float(b.get('start', 0)),
                    'duration': float(b.get('duration', 0)),
                    'text': texto
                })
        return blocos_limpos if blocos_limpos else None

    def obter_transcricao(self, video_id: str) -> Optional[str]:
        """Tenta obter a transcrição de texto formatada com timestamps."""
        blocos = self.obter_transcricao_blocos(video_id)
        if not blocos:
            return None
        linhas = [f"{formatar_tempo(b['start'])} {b['text']}" for b in blocos]
        return "\n".join(linhas)

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

        try:
            with yt_dlp.YoutubeDL(opcoes) as ydl:
                ydl.download([url])
        except Exception:
            for sufixo in ("", ".part", ".ytdl"):
                if os.path.exists(caminho_audio + sufixo):
                    try:
                        os.remove(caminho_audio + sufixo)
                    except Exception:
                        pass
            raise

        return caminho_audio

    def extrair_tudo(self, url: str) -> Dict[str, Any]:
        """Combina metadados e transcrição ou ativa o áudio fallback em caso de bloqueio."""
        video_id = extrair_id_youtube(url)
        if not video_id:
            raise ValueError(f"URL inválido do YouTube: {url}")

        metadados = self.obter_metadados(url)
        blocos = self.obter_transcricao_blocos(video_id)
        transcricao = "\n".join([f"{formatar_tempo(b['start'])} {b['text']}" for b in blocos]) if blocos else None
        caminho_audio = None

        if not transcricao:
            print("    ⚠️ Legendas de texto bloqueadas ou indisponíveis no YouTube.")
            print("    🎧 A descarregar áudio leve para análise direta pelo Gemini Flash...")
            caminho_audio = self.descarregar_audio(url, video_id)

        # Se a duração for 0 nos metadados mas temos blocos, calcula a partir do último bloco
        duracao = metadados.get("duracao_segundos") or 0
        if duracao == 0 and blocos:
            ultimo = blocos[-1]
            duracao = int(ultimo['start'] + ultimo.get('duration', 0))
            metadados["duracao_segundos"] = duracao

        return {
            **metadados,
            "transcricao": transcricao,
            "transcricao_blocos": blocos,
            "caminho_audio": caminho_audio
        }
