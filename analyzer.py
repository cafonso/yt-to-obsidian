import os
import time
from typing import Dict, Any, List, Optional
from google import genai
from google.genai import types
from models import AnaliseVideo, SegmentoAnalise, SinteseGlobal, PessoaMencionada, ArtefactoIA, ObraCitada, AgendaScout, SessaoScout, PalestraAnalise
import config
from extrator import formatar_tempo
from canonicalizer import Canonicalizer
import random
import re
from config import FALLBACK_MODEL
import unicodedata


INSTRUCOES_EXTRACAO_COMUNS = """
INSTRUÇÕES ESPECÍFICAS DE EXTRAÇÃO:
0. REGRA ESTRITA DE IDIOMAS E TÍTULOS (MUITO IMPORTANTE):
   - TÍTULOS DE VÍDEOS: Mantém SEMPRE o título na sua língua original (geralmente em inglês). NUNCA traduzas o título do vídeo para português! Apenas remove emojis excessivos ou CAPS LOCK de clickbait.
   - TÍTULOS DE OBRAS (Livros, Artigos, Papers): Mantém SEMPRE o título original oficial na língua de publicação. NUNCA traduzas títulos de livros ou papers!
   - NOMES DE ARTEFACTOS: Mantém SEMPRE o nome oficial (ex: 'GPT-4o', 'Claude 3.5 Sonnet', 'H100 SXM5', 'LoRA'). NUNCA traduzas nem abras nomes de modelos/ferramentas.
   - TEMAS: Usa a terminologia técnica padrão original (geralmente em inglês). Se quiseres incluir a tradução portuguesa, coloca-a OBRIGATORIAMENTE entre parênteses. NUNCA uses termos isolados em português do Brasil.
   - SÍNTESE: O resumo executivo, takeaways e bios devem ser redigidos em português claro, formal e correto (PT-PT).

1. Resumo Executivo / Síntese: Sintetiza em português os tópicos e conclusões essenciais (2 a 3 parágrafos ou resumo coeso do segmento).
2. Takeaways Principais: Lista de pontos-chave práticos e de alto valor.
3. Métricas, Números & Dados Quantitativos: Extrai todos os dados concretos citados (ex: percentagens de ganho de eficiência, benchmarks, números financeiros como receitas/burn, contagens de tokens, custos por tarefa, multiplicadores).
4. Tensões, Riscos & Mitos Desmontados: Identifica os pontos de atrito, mitos desmistificados pelos oradores, limitações técnicas dos modelos, riscos de infraestrutura ou pontos de ceticismo qualificado.
5. Agenda & Previsões Futuras: Datas de lançamentos, IPOs, conferências, janelas de publicação ou cronogramas esperados para as próximas semanas/meses.
6. Links, Papers & Recursos Externos: Lista de URLs reais, referências a papers no Arxiv, links no GitHub, posts de blog ou documentação relevante mencionada.
7. Capítulos / Timestamps / Marcos: Lista dos principais marcos temporais ou títulos de secção relevantes.
8. Temas: Conceitos centrais na terminologia técnica original (com tradução opcional entre parênteses).
9. Pessoas (REGRA DO NOME COMPLETO):
   - Extrai APENAS figuras públicas, cientistas, autores, oradores ou executivos de relevância real com o seu NOME COMPLETO CANÓNICO.
   - NUNCA uses apenas o primeiro nome próprio solto (ex: NUNCA 'Sarah', 'Dom', 'Tim', 'Koen', 'Damien', 'Zach').
   - NÃO coloques empresas ou organizações neste campo — vai para o campo 11.
10. Livros, Artigos e Papers Citados: Obras citadas no título original com o(s) respetivo(s) autor(es).
11. Organizações: Empresas, universidades, laboratórios ou instituições chave referidas (ex: 'OpenAI', 'Google DeepMind', 'NVIDIA', 'Anthropic', 'MIT', 'Hugging Face'). Usa o nome oficial e completo da organização.
12. Artefactos (Modelos, Frameworks, Ferramentas, Agentes, Técnicas, Hardware, Plataformas, Dataset):
   - Extrai TODOS os artefactos técnicos mencionados com o nome oficial.
   - Classifica cada um num dos 8 subtipos: 'modelo', 'framework', 'ferramenta', 'agente', 'tecnica', 'hardware', 'plataforma', 'dataset'.
   - Indica o fabricante/autor quando conhecido. Deixa null se desconhecido.
   - Para cada artefacto, escreve 1-2 frases em português sobre o seu papel/relevância NO CONTEXTO específico.

Responde estritamente de acordo com o esquema JSON fornecido.
"""


def _extrair_retry_after(erro_str: str) -> Optional[float]:
    """
    Tenta extrair um valor de Retry-After (segundos) da mensagem de erro.
    O SDK do google-genai às vezes inclui o header na string de exceção.
    Devolve None se não encontrar.
    """
    m = re.search(r'retry[_\- ]?after\s*[:=]\s*"?(\d+(?:\.\d+)?)\s*s?"?', erro_str, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _calcular_espera(tentativa: int, erro_str: str) -> float:
    """
    Calcula o intervalo de espera para a tentativa N (1-indexed).

    - Se o erro for 429, usa base específica (mais longa).
    - Se for 503, usa base específica (mais curta).
    - Caso contrário, usa a base geral.
    - Aplica exponencial 2^(tentativa-1), limitada ao teto.
    - Aplica jitter ±GEMINI_BACKOFF_JITTER.
    - Respeita Retry-After se presente e a flag estiver ligada.
    """
    erro_lower = erro_str.lower()

    if "429" in erro_str or "resource_exhausted" in erro_lower:
        base = config.GEMINI_BACKOFF_BASE_429
    elif "503" in erro_str or "unavailable" in erro_lower:
        base = config.GEMINI_BACKOFF_BASE_503
    else:
        base = config.GEMINI_BACKOFF_BASE_SEGUNDOS

    espera = base * (2 ** (tentativa - 1))
    espera = min(espera, config.GEMINI_BACKOFF_TETO_SEGUNDOS)

    if config.GEMINI_BACKOFF_JITTER > 0:
        fator = 1.0 + random.uniform(-config.GEMINI_BACKOFF_JITTER, config.GEMINI_BACKOFF_JITTER)
        espera = max(1.0, espera * fator)

    if config.GEMINI_RESPEITAR_RETRY_AFTER:
        ra = _extrair_retry_after(erro_str)
        if ra is not None:
            espera = min(ra, config.GEMINI_BACKOFF_TETO_SEGUNDOS)

    return espera


def _chave_frase(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[.,;:!?]+$", "", s).strip()
    return s


def desduplicar_strings(lista: List[str]) -> List[str]:
    """Deduplicação simples para textos livres (métricas, tensões, agenda, recursos).
    Não usar para entidades — essas passam pelo Canonicalizer."""
    vistos: set[str] = set()
    resultado: List[str] = []
    for item in lista:
        if not item or not item.strip():
            continue
        item_limpo = item.strip()
        chave = _chave_frase(item_limpo)
        if chave and chave not in vistos:
            vistos.add(chave)
            resultado.append(item_limpo)
    return resultado



def _criar_canonicalizer() -> Canonicalizer:
    """Instancia o Canonicalizer com todas as definições centralizadas no config.py."""
    return Canonicalizer(
        aliases_path=config.ALIASES_PATH,
        decisoes_path=config.DECISOES_PATH,
        revisao_path=config.REVISAO_PATH,
        threshold_fusao_auto=config.CANON_THRESHOLD_FUSAO_AUTO,
        threshold_revisao=config.CANON_THRESHOLD_REVISAO,
        blocking_por_ultimo_token=config.CANON_BLOCKING_POR_ULTIMO_TOKEN,
        aprender_aliases=config.CANON_APRENDER_ALIASES,
        escrever_revisao=config.CANON_ESCREVER_REVISAO,
        escrever_decisoes=config.CANON_ESCREVER_DECISOES,
    )


class VideoAnalyzer:
    def __init__(self, model_name: str = None):
        self.model_name = model_name or config.MODELO_GEMINI
        self.fallback_model = FALLBACK_MODEL
        self.client = genai.Client(http_options={'api_version': 'v1beta', 'timeout': 180000})

    def _chamar_gemini_com_retry(self, modelo: str, conteudos: list, config_obj: types.GenerateContentConfig, max_tentativas: int = None):
        if max_tentativas is None:
            max_tentativas = config.GEMINI_MAX_TENTATIVAS

        for tentativa in range(1, max_tentativas + 1):
            try:
                print(f"    📡 A aguardar resposta do Gemini ({modelo}) [tentativa {tentativa}/{max_tentativas}]...", flush=True)
                return self.client.models.generate_content(
                    model=modelo,
                    contents=conteudos,
                    config=config_obj,
                )
            except Exception as e:
                erro_str = str(e)
                quota_diaria = (
                    "PerDay" in erro_str
                    or "per day" in erro_str.lower()
                    or "GenerateRequestsPerDay" in erro_str
                )
                transitorio = (
                    not quota_diaria
                    and (
                        "503" in erro_str
                        or "UNAVAILABLE" in erro_str
                        or "429" in erro_str
                        or "RESOURCE_EXHAUSTED" in erro_str
                        or "timeout" in erro_str.lower()
                        or "timed out" in erro_str.lower()
                    )
                )
                if not transitorio or tentativa >= max_tentativas:
                    raise e

                espera = _calcular_espera(tentativa, erro_str)
                print(
                    f"    ⚠️ Erro/Timeout ({erro_str[:60]}...). "
                    f"A aguardar {espera:.1f}s antes da tentativa {tentativa + 1}/{max_tentativas}...",
                    flush=True,
                )
                time.sleep(espera)
        

    def _chamar_com_fallback(self, modelo: str, conteudos: list, config_obj: types.GenerateContentConfig):
        """Chama o Gemini com retry no modelo indicado e faz fallback se este falhar."""
        try:
            return self._chamar_gemini_com_retry(modelo, conteudos, config_obj)
        except Exception:
            if self.fallback_model and self.fallback_model != modelo:
                return self._chamar_gemini_com_retry(self.fallback_model, conteudos, config_obj)
            raise

    def _preparar_contexto_scout(self, dados_video: Dict[str, Any]) -> str:
        """
        Prepara o material para o Scout:
        1. Se existirem capítulos oficiais no YouTube, usa-os (rápido e barato).
        2. Caso contrário, compacta a transcrição agrupando blocos a cada 30s
           para reduzir tokens sem perder nenhum minuto de fala.
        """
        capitulos = dados_video.get("capitulos_originais") or []
        if len(capitulos) >= 3:
            linhas_cap = [
                f"- {formatar_tempo(c.get('start_time', 0))} a {formatar_tempo(c.get('end_time', 0))}: {c.get('title', '')}"
                for c in capitulos
            ]
            return "CAPÍTULOS DETETADOS NOS METADADOS DO YOUTUBE:\n" + "\n".join(linhas_cap)

        blocos = dados_video.get("transcricao_blocos") or []
        if not blocos:
            transcricao = dados_video.get("transcricao")
            if not transcricao:
                raise ValueError("Não há capítulos nem transcrição disponíveis para executar o Scout.")
            return f"TRANSCRIÇÃO COMPLETA:\n{transcricao}"

        linhas_compactadas = []
        buffer_texto = []
        ts_janela = None

        for b in blocos:
            if ts_janela is None:
                ts_janela = b["start"]
            buffer_texto.append(b["text"])

            if (b["start"] - ts_janela) >= 30:
                linhas_compactadas.append(f"{formatar_tempo(ts_janela)} {' '.join(buffer_texto)}")
                buffer_texto = []
                ts_janela = None

        if buffer_texto and ts_janela is not None:
            linhas_compactadas.append(f"{formatar_tempo(ts_janela)} {' '.join(buffer_texto)}")

        return "TRANSCRIÇÃO COMPACTADA (JANELAS DE 30s):\n" + "\n".join(linhas_compactadas)

    def _fatiar_transcricao(self, blocos: List[Dict[str, Any]], capitulos_originais: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """Divide a transcrição em segmentos temporais (~30 minutos) respeitando capítulos se existirem."""
        duracao_chunk = config.DURACAO_CHUNK_SEGUNDOS
        if not blocos:
            return []

        if capitulos_originais and len(capitulos_originais) > 1:
            segmentos = []
            chunk_caps = []
            duracao_acumulada = 0

            for cap in capitulos_originais:
                st = cap.get("start_time", 0)
                et = cap.get("end_time", st)
                dur_cap = et - st
                chunk_caps.append(cap)
                duracao_acumulada += dur_cap

                if duracao_acumulada >= duracao_chunk:
                    inicio_s = chunk_caps[0]["start_time"]
                    fim_s = chunk_caps[-1]["end_time"]
                    blocos_fatia = [b for b in blocos if inicio_s <= b['start'] < fim_s]
                    if blocos_fatia:
                        texto = "\n".join([f"{formatar_tempo(b['start'])} {b['text']}" for b in blocos_fatia])
                        titulos_caps = " / ".join([c.get("title", "") for c in chunk_caps if c.get("title")])
                        segmentos.append({
                            "ts_inicio": formatar_tempo(inicio_s),
                            "ts_fim": formatar_tempo(fim_s),
                            "titulo_sugerido": titulos_caps,
                            "texto": texto
                        })
                    chunk_caps = []
                    duracao_acumulada = 0

            if chunk_caps:
                inicio_s = chunk_caps[0]["start_time"]
                fim_s = chunk_caps[-1].get("end_time") or blocos[-1]['start']
                blocos_fatia = [b for b in blocos if inicio_s <= b['start']]
                if blocos_fatia:
                    texto = "\n".join([f"{formatar_tempo(b['start'])} {b['text']}" for b in blocos_fatia])
                    titulos_caps = " / ".join([c.get("title", "") for c in chunk_caps if c.get("title")])
                    segmentos.append({
                        "ts_inicio": formatar_tempo(inicio_s),
                        "ts_fim": formatar_tempo(fim_s),
                        "titulo_sugerido": titulos_caps,
                        "texto": texto
                    })
            if segmentos:
                return segmentos

        segmentos = []
        chunk_atual = []
        tempo_inicio_chunk = blocos[0]['start']

        for b in blocos:
            chunk_atual.append(b)
            tempo_decorrido = b['start'] - tempo_inicio_chunk

            if tempo_decorrido >= duracao_chunk:
                tempo_fim_chunk = b['start'] + b.get('duration', 0)
                texto_formatado = "\n".join([f"{formatar_tempo(x['start'])} {x['text']}" for x in chunk_atual])
                segmentos.append({
                    "ts_inicio": formatar_tempo(tempo_inicio_chunk),
                    "ts_fim": formatar_tempo(tempo_fim_chunk),
                    "titulo_sugerido": None,
                    "texto": texto_formatado
                })
                chunk_atual = []
                tempo_inicio_chunk = tempo_fim_chunk

        if chunk_atual:
            tempo_fim_chunk = chunk_atual[-1]['start'] + chunk_atual[-1].get('duration', 0)
            texto_formatado = "\n".join([f"{formatar_tempo(x['start'])} {x['text']}" for x in chunk_atual])
            segmentos.append({
                "ts_inicio": formatar_tempo(tempo_inicio_chunk),
                "ts_fim": formatar_tempo(tempo_fim_chunk),
                "titulo_sugerido": None,
                "texto": texto_formatado
            })

        return segmentos

    def _analisar_segmento(self, dados_video: Dict[str, Any], segmento: Dict[str, Any], idx: int, total: int) -> SegmentoAnalise:
        """Executa a extração estruturada de um segmento específico (texto ou áudio) de vídeo longo."""
        ts_inicio = segmento["ts_inicio"]
        ts_fim = segmento["ts_fim"]
        texto_segmento = segmento.get("texto")
        caminho_audio_chunk = segmento.get("caminho_audio_chunk")
        dica_titulo = f"\n- Tema/Capítulo sugerido nos metadados: {segmento['titulo_sugerido']}" if segmento.get('titulo_sugerido') else ""

        fonte_bloco = (
            f"TRANSCRIÇÃO DESTE BLOCO ({ts_inicio} a {ts_fim}):\n{texto_segmento}"
            if texto_segmento
            else f"FONTE: Ouve atentamente o ficheiro de áudio anexado correspondente ao intervalo {ts_inicio} a {ts_fim}."
        )

        prompt = f"""
És um assistente especializado em Gestão de Conhecimento Pessoal (PKM) e síntese técnica para o Obsidian.
Estás a analisar o BLOCO {idx}/{total} de um evento ou conferência técnica longa do YouTube.

CONTEXTO GLOBAL DO VÍDEO:
- Título do Vídeo: {dados_video.get('titulo')}
- Canal: {dados_video.get('canal')}
- Intervalo deste Bloco: {ts_inicio} a {ts_fim}{dica_titulo}

{fonte_bloco}

{INSTRUCOES_EXTRACAO_COMUNS}
"""
        config_obj = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SegmentoAnalise,
            temperature=0.2,
        )

        arquivo_google = None
        conteudos = [prompt]

        try:
            if caminho_audio_chunk and os.path.exists(caminho_audio_chunk):
                arquivo_google = self.client.files.upload(file=caminho_audio_chunk)
                conteudos.append(arquivo_google)

            resp = self._chamar_com_fallback(self.model_name, conteudos, config_obj)

            if not resp or not resp.parsed:
                raise ValueError(f"Falha ao analisar o bloco {idx}/{total}.")
            return resp.parsed
        finally:
            if arquivo_google:
                try:
                    self.client.files.delete(name=arquivo_google.name)
                except Exception:
                    pass

    def _consolidar_segmentos(self, dados_video: Dict[str, Any], segmentos_analisados: List[SegmentoAnalise]) -> AnaliseVideo:
        """Funde as entidades recolhidas em todos os blocos e gera o resumo executivo global (Reduce)."""
        todas_pessoas = []
        todas_obras = []
        todas_orgs = []
        todos_artefactos = []
        todos_temas = []
        todas_metricas = []
        todas_tensoes = []
        todas_agendas = []
        todos_recursos = []
        capitulos = []

        resumo_blocos_texto_lista = []
        takeaways_fallback = []

        for seg in segmentos_analisados:
            todas_pessoas.extend(seg.pessoas)
            todas_obras.extend(seg.obras)
            todas_orgs.extend(seg.organizacoes)
            todos_artefactos.extend(seg.artefactos)
            todas_temas.extend(seg.temas)
            todas_metricas.extend(seg.metricas_e_numeros)
            todas_tensoes.extend(seg.tensoes_e_riscos)
            todas_agendas.extend(seg.agenda_e_previsoes)
            todos_recursos.extend(seg.recursos_e_links)

            oradores_str = f" _(Oradores: {', '.join(seg.oradores_ou_apresentadores)})_" if seg.oradores_ou_apresentadores else ""
            takeaways_str = "\n    * " + "\n    * ".join(seg.takeaways_bloco) if seg.takeaways_bloco else ""
            bloco_cap = f"**{seg.timestamp_inicio} - {seg.timestamp_fim}: {seg.titulo_segmento}**{oradores_str}\n  - {seg.resumo_bloco}{takeaways_str}"
            capitulos.append(bloco_cap)

            resumo_blocos_texto_lista.append(
                f"- Bloco [{seg.timestamp_inicio} - {seg.timestamp_fim}] {seg.titulo_segmento}{oradores_str}:\n  {seg.resumo_bloco}"
            )
            takeaways_fallback.extend(seg.takeaways_bloco[:2])

        resumo_blocos_texto = "\n\n".join(resumo_blocos_texto_lista)

        prompt_sintese = f"""
És um assistente especializado em Gestão de Conhecimento Pessoal (PKM) e síntese técnica para o Obsidian.
Analisaste detalhadamente os {len(segmentos_analisados)} blocos de um evento/vídeo técnico longo do YouTube.
Agora, gera o Resumo Executivo Global coeso e os Principais Takeaways transversais de todo o evento.

METADADOS DO VÍDEO:
- Título do Vídeo: {dados_video.get('titulo')}
- Canal: {dados_video.get('canal')}
- Duração: {dados_video.get('duracao_segundos')} segundos

SÍNTESE DE CADA BLOCO DO EVENTO:
{resumo_blocos_texto}

INSTRUÇÕES:
1. Resumo Executivo: Redige uma síntese coesa, densa e clara de todo o evento em 2 a 4 parágrafos em português formal (PT-PT).
2. Takeaways Principais: Lista com os 5 a 10 ensinamentos práticos e estratégicos mais valiosos de todo o evento em português.
3. Título Sugerido: Mantém o título original oficial sem traduções e limpo de clickbait.

Responde estritamente de acordo com o esquema JSON fornecido.
"""
        config_obj = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SinteseGlobal,
            temperature=0.2,
        )

        try:
            resp_sintese = self._chamar_com_fallback(self.model_name, [prompt_sintese], config_obj)
            if not resp_sintese or not resp_sintese.parsed:
                raise ValueError("O Gemini devolveu uma resposta nula ou inválida na síntese global do vídeo longo.")
            sintese: SinteseGlobal = resp_sintese.parsed
            titulo_sugerido = sintese.titulo_sugerido or dados_video.get("titulo")
            resumo_executivo = sintese.resumo_executivo
            takeaways_principais = sintese.takeaways_principais
        except Exception as e_sintese:
            print(f"    ⚠️ Síntese global falhou ({e_sintese}). A gerar consolidação local a partir dos blocos...", flush=True)
            titulo_sugerido = dados_video.get("titulo")
            resumo_executivo = "\n\n".join(seg.resumo_bloco for seg in segmentos_analisados if seg.resumo_bloco)
            takeaways_principais = desduplicar_strings(takeaways_fallback)[:10]

        canon = _criar_canonicalizer()

        pessoas_canon = canon.canonicalizar_pessoas(todas_pessoas)
        artefactos_canon = canon.canonicalizar_artefactos(todos_artefactos)
        obras_canon = canon.canonicalizar_obras(todas_obras)
        organizacoes_canon = canon.canonicalizar_strings("organizacao", todas_orgs)
        temas_canon = canon.canonicalizar_strings("tema", todos_temas)

        canon.gravar()

        return AnaliseVideo(
            titulo_sugerido=titulo_sugerido,
            resumo_executivo=resumo_executivo,
            takeaways_principais=takeaways_principais,
            metricas_e_numeros=desduplicar_strings(todas_metricas),
            tensoes_e_riscos=desduplicar_strings(todas_tensoes),
            agenda_e_previsoes=desduplicar_strings(todas_agendas),
            recursos_e_links=desduplicar_strings(todos_recursos),
            capitulos=capitulos,
            temas=temas_canon,
            pessoas=pessoas_canon,
            obras=obras_canon,
            organizacoes=organizacoes_canon,
            artefactos=artefactos_canon,
        )
    def analisar_video_longo(self, dados_video: Dict[str, Any]) -> AnaliseVideo:
        """Processa um vídeo longo dividindo-o em blocos (texto ou áudio) e consolidando no final."""
        blocos = dados_video.get("transcricao_blocos") or []
        capitulos_originais = dados_video.get("capitulos_originais") or []
        caminho_audio = dados_video.get("caminho_audio")

        segmentos = []
        usar_audio = False

        if blocos:
            segmentos = self._fatiar_transcricao(blocos, capitulos_originais)
        elif caminho_audio and os.path.exists(caminho_audio):
            from extrator import YouTubeExtractor
            print("    ✂️ A fatiar áudio longo com ffmpeg para processamento Map-Reduce...")
            segmentos = YouTubeExtractor().fatiar_audio(caminho_audio)
            usar_audio = True

        if not segmentos:
            raise ValueError("Não há transcrição nem áudio válido para fatiar o vídeo longo.")

        duracao_min = (dados_video.get('duracao_segundos') or 0) // 60
        modo_str = "áudio" if usar_audio else "texto"
        print(f"    🧩 Vídeo longo ({duracao_min} min). A ativar pipeline Map-Reduce ({modo_str}) em {len(segmentos)} blocos...")

        segmentos_analisados = []
        try:
            for i, seg in enumerate(segmentos, 1):
                print(f"       -> [{i:02d}/{len(segmentos):02d}] A analisar bloco: {seg['ts_inicio']} a {seg['ts_fim']}...")
                analise_bloco = self._analisar_segmento(dados_video, seg, i, len(segmentos))
                segmentos_analisados.append(analise_bloco)
                time.sleep(1)
        finally:
            for seg in segmentos:
                chunk_path = seg.get("caminho_audio_chunk")
                if chunk_path and os.path.exists(chunk_path):
                    try:
                        os.remove(chunk_path)
                    except Exception:
                        pass

        print("    🔄 A consolidar entidades e a sintetizar o resumo executivo global...")
        return self._consolidar_segmentos(dados_video, segmentos_analisados)

    def analisar_passo_unico(self, dados_video: Dict[str, Any]) -> AnaliseVideo:
        """Envia transcrição curta ou áudio + metadados ao Gemini numa única passagem."""
        caminho_audio = dados_video.get("caminho_audio")
        transcricao = dados_video.get("transcricao")

        tipo_analise = "a transcrição de texto" if transcricao else "o registo de áudio"
        prompt = f"""
És um assistente especializado em Gestão de Conhecimento Pessoal (PKM) e síntese profunda para o Obsidian.
Analisa {tipo_analise} e os metadados do vídeo do YouTube e extrai todas as entidades essenciais com rigor.

METADADOS DO VÍDEO:
- Título: {dados_video.get('titulo')}
- Canal / Criador: {dados_video.get('canal')}
- Data de Publicação: {dados_video.get('data')}
- URL: {dados_video.get('url')}

DESCRIÇÃO ORIGINAL DO VÍDEO (RECURSOS, LINKS E TIMESTAMPS):
{dados_video.get('descricao', '')}
"""
        if transcricao:
            prompt += f"\nTRANSCRIÇÃO COMPLETA:\n{transcricao}\n"

        prompt += f"\n{INSTRUCOES_EXTRACAO_COMUNS}"

        config_obj = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=AnaliseVideo,
            temperature=0.2,
        )

        arquivo_google = None
        conteudos = [prompt]

        if caminho_audio and os.path.exists(caminho_audio):
            print("    ☁️ A enviar áudio leve diretamente para o Gemini Flash...")
            arquivo_google = self.client.files.upload(file=caminho_audio)
            conteudos.append(arquivo_google)

        response = None
        try:
            response = self._chamar_com_fallback(self.model_name, conteudos, config_obj)
        finally:
            if arquivo_google:
                try:
                    self.client.files.delete(name=arquivo_google.name)
                except Exception:
                    pass

        if not response or not response.parsed:
            raise ValueError("O Gemini não devolveu um resultado estruturado válido.")

        analise: AnaliseVideo = response.parsed
        canon = _criar_canonicalizer()

        analise.pessoas = canon.canonicalizar_pessoas(analise.pessoas)
        analise.artefactos = canon.canonicalizar_artefactos(analise.artefactos)
        analise.obras = canon.canonicalizar_obras(analise.obras)
        analise.organizacoes = canon.canonicalizar_strings("organizacao", analise.organizacoes)
        analise.temas = canon.canonicalizar_strings("tema", analise.temas)

        canon.gravar()

        return analise

    def executar_scout(self, dados_video: Dict[str, Any]) -> AgendaScout:
        """Executa 'The Scout' para mapear a agenda real de uma conferência ou vídeo longo."""
        contexto_scout = self._preparar_contexto_scout(dados_video)

        prompt = f"""
És um assistente especializado em conferências de tecnologia e estruturação de eventos técnicos.
Estás a analisar os metadados e o conteúdo de uma transmissão longa do YouTube ({dados_video.get('duracao_segundos')} segundos).

VÍDEO:
- Título Oficial: {dados_video.get('titulo')}
- Canal: {dados_video.get('canal')}
- Duração: {dados_video.get('duracao_segundos')} segundos
- Descrição do Vídeo:
{dados_video.get('descricao', '')[:3000]}

{contexto_scout}

OBJETIVO DO SCOUT:
1. Determina se este vídeo é uma conferência / evento com múltiplas palestras e oradores (eh_conferencia=True), ou se é um monólogo/conversa com uma única pessoa (eh_conferencia=False).
2. Se for uma conferência, extrai o nome curto e padronizado da conferência (ex: 'AIE CODE 2026', 'AI Engineer Summit 2026') e o Dia se mencionado no título ou descrição (ex: dia=2, dia_rotulo='Dia 2', data_sessao='2026-11-12').
3. Identifica todas as palestras/apresentações individuais que compõem este evento:
   - Timestamp e segundo de início (para deep link do YouTube).
   - Timestamp e segundo de fim.
   - Nome completo canónico do orador (se for apresentação individual).
   - Empresa ou organização do orador (ex: OpenAI, Anthropic, Warp, Cognition).
   - Título descritivo ou tema da palestra na língua original.
   - Classifica o tipo de sessão (palestra, keynote, painel, entrevista). Ignora intervalos vazios ou pausas de almoço.

Responde estritamente de acordo com o esquema JSON fornecido.
"""
        config_obj = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=AgendaScout,
            temperature=0.1,
        )

        resp = self._chamar_com_fallback(config.MODELO_SCOUT, [prompt], config_obj)

        if not resp or not resp.parsed:
            raise ValueError("Falha ao executar o Scout sobre o vídeo.")
        return resp.parsed

    def analisar_palestra(
        self,
        dados_video: Dict[str, Any],
        agenda: AgendaScout,
        sessao: SessaoScout,
        texto_palestra: str,
        canon: Canonicalizer
    ) -> PalestraAnalise:
        """Extrai detalhadamente os pontos e entidades de uma palestra individual da conferência."""
        orador_info = f"{sessao.orador_principal}" if sessao.orador_principal else "Vários / Painel"
        if sessao.organizacao:
            orador_info += f" ({sessao.organizacao})"

        prompt = f"""
És um assistente especializado em Gestão de Conhecimento Pessoal (PKM) e síntese técnica para o Obsidian.
Estás a analisar uma PALESTRA INDIVIDUAL ({sessao.ordem}/{len(agenda.sessoes)}) dentro da conferência '{agenda.nome_conferencia}' ({agenda.dia_rotulo or 'Dia 1'}).

CONTEXTO DA PALESTRA:
- Conferência: {agenda.nome_conferencia}
- Orador: {orador_info}
- Título da Palestra: {sessao.titulo_palestra}
- Intervalo Temporal: {sessao.timestamp_inicio} a {sessao.timestamp_fim}

TRANSCRIÇÃO DESTA PALESTRA:
{texto_palestra}

INSTRUÇÕES DE EXTRAÇÃO:
0. REGRA ESTRITA DE IDIOMAS E NOMES:
   - TÍTULOS: Mantém o título da palestra na língua original (inglês).
   - NOMES DE PESSOAS: Apenas pessoas com NOME COMPLETO canónico (ex: 'Jason Liu', 'Zach Lloyd'). NUNCA apenas primeiro nome.
   - NOMES DE ARTEFACTOS: Mantém o nome oficial original (ex: 'GPT-4o', 'Claude 3.5 Sonnet', 'ArtCraft', 'Warp', 'LoRA').
   - RESUMO E TAKEAWAYS: Redige em português claro, formal e correto (PT-PT).

1. Título da Palestra: Título oficial ou descritivo da apresentação na língua original.
2. Resumo Executivo: 2 a 3 parágrafos densos e claros em português (PT-PT) sobre o conteúdo central debatido por este orador.
3. Takeaways Principais: 3 a 6 ensinamentos essenciais desta palestra.
4. Métricas & Números: Todos os dados quantitativos, percentagens, custos ou benchmarks citados nesta palestra.
5. Tensões & Riscos: Dificuldades técnicas, limitações ou mitos desmontados nesta palestra.
6. Agenda & Previsões: Prazos, anúncios futuros ou datas mencionadas nesta sessão.
7. Recursos & Links: Papers, repositórios GitHub ou ferramentas mencionadas.
8. Pessoas: Pessoas relevantes citadas com NOME COMPLETO canónico.
9. Obras: Livros, artigos ou papers citados com títulos originais e autores.
10. Organizações: Empresas ou instituições chave referidas nesta palestra.
11. Artefactos: Modelos, ferramentas, frameworks, agentes, hardware ou técnicas citados nesta palestra (com os 8 subtipos e fabricante).

Responde estritamente de acordo com o esquema JSON fornecido.
"""
        config_obj = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PalestraAnalise,
            temperature=0.2,
        )

        resp = self._chamar_com_fallback(self.model_name, [prompt], config_obj)

        if not resp or not resp.parsed:
            raise ValueError(f"Falha ao analisar a palestra #{sessao.ordem}: {sessao.titulo_palestra}")

        palestra: PalestraAnalise = resp.parsed

        palestra.pessoas = canon.canonicalizar_pessoas(palestra.pessoas)
        palestra.artefactos = canon.canonicalizar_artefactos(palestra.artefactos)
        palestra.obras = canon.canonicalizar_obras(palestra.obras)
        palestra.organizacoes = canon.canonicalizar_strings("organizacao", palestra.organizacoes)
        palestra.temas = canon.canonicalizar_strings("tema", palestra.temas)

        return palestra

    def processar_conferencia_completa(
        self,
        dados_video: Dict[str, Any],
        agenda: AgendaScout,
        writer,
        data_leitura: str = None
    ) -> str:
        """Processa todas as palestras detetadas pelo Scout e gera as notas atómicas + MOC na subpasta dedicada."""
        blocos = dados_video.get("transcricao_blocos") or []
        dia_rotulo = agenda.dia_rotulo or f"Dia {agenda.dia or 1}"
        total = len(agenda.sessoes)

        print(f"\n🏛️ A processar Conferência: '{agenda.nome_conferencia}' ({dia_rotulo})")
        print(f"📁 Pasta de destino: Videos/{agenda.nome_conferencia}/")
        print(f"📋 Total de palestras a extrair: {total}\n")

        canon = _criar_canonicalizer()
        palestras_processadas = []

        for idx, sessao in enumerate(agenda.sessoes, 1):
            orador_str = sessao.orador_principal or "Painel"
            print(f"   -> [{idx:02d}/{total:02d}] {sessao.timestamp_inicio} {orador_str}: {sessao.titulo_palestra[:45]}...")

            blocos_fatia = [b for b in blocos if sessao.segundos_inicio <= b['start'] <= sessao.segundos_fim]
            if not blocos_fatia:
                blocos_fatia = [b for b in blocos if (sessao.segundos_inicio - 30) <= b['start'] <= (sessao.segundos_fim + 30)]

            texto_fatia = "\n".join([f"{formatar_tempo(b['start'])} {b['text']}" for b in blocos_fatia])
            if not texto_fatia.strip():
                print(f"      ⚠️ Aviso: Transcrição vazia para a sessão #{sessao.ordem}. A avançar...")
                continue

            analise_palestra = self.analisar_palestra(dados_video, agenda, sessao, texto_fatia, canon)

            caminho_nota = writer.salvar_palestra_conferencia(dados_video, agenda, sessao, analise_palestra, data_leitura)
            palestras_processadas.append({
                "sessao": sessao,
                "caminho": caminho_nota,
                "analise": analise_palestra
            })

            time.sleep(1)

        canon.gravar()

        print("\n   📑 A compilar/atualizar o Índice MOC da conferência...")
        caminho_moc = writer.salvar_ou_atualizar_moc_conferencia(dados_video, agenda, palestras_processadas, data_leitura)
        print(f"   ✓ MOC da Conferência: {caminho_moc}")

        return str(caminho_moc)

    def analisar(self, dados_video: Dict[str, Any]) -> AnaliseVideo:
        """Decide inteligentemente entre passo único (curtos) ou Map-Reduce (longos)."""
        duracao = dados_video.get("duracao_segundos") or 0
        blocos = dados_video.get("transcricao_blocos")
        caminho_audio = dados_video.get("caminho_audio")

        eh_longo = duracao > config.LIMIAR_VIDEO_LONGO_SEGUNDOS
        tem_material_longo = (blocos and len(blocos) > 200) or bool(caminho_audio)

        if eh_longo and tem_material_longo:
            return self.analisar_video_longo(dados_video)
        else:
            return self.analisar_passo_unico(dados_video)
