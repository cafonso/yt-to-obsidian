import os
import time
from typing import Dict, Any, List, Optional
from google import genai
from google.genai import types
from models import AnaliseVideo, SegmentoAnalise, SinteseGlobal, PessoaMencionada, ArtefactoIA, ObraCitada
import config
from extractor import formatar_tempo
from canonicalizer import Canonicalizer
import random
import re

def _extrair_retry_after(erro_str: str) -> Optional[float]:
    """
    Tenta extrair um valor de Retry-After (segundos) da mensagem de erro.
    O SDK do google-genai às vezes inclui o header na string de exceção.
    Devolve None se não encontrar.
    """
    # Formatos comuns: "retry_after: 30", "Retry-After: 30", "retryDelay: 30s"
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

    # Jitter multiplicativo (±20% por defeito)
    if config.GEMINI_BACKOFF_JITTER > 0:
        fator = 1.0 + random.uniform(-config.GEMINI_BACKOFF_JITTER, config.GEMINI_BACKOFF_JITTER)
        espera = max(1.0, espera * fator)

    # Retry-After explícito do servidor tem prioridade (mas respeita o teto)
    if config.GEMINI_RESPEITAR_RETRY_AFTER:
        ra = _extrair_retry_after(erro_str)
        if ra is not None:
            espera = min(ra, config.GEMINI_BACKOFF_TETO_SEGUNDOS)

    return espera

def eh_nome_valido_pessoa(nome: str) -> bool:
    if not nome or not nome.strip():
        return False
    partes = nome.strip().split()
    return len(partes) >= 2


def desduplicar_strings(lista: List[str]) -> List[str]:
    """Deduplicação simples para textos livres (métricas, tensões, agenda, recursos).
    Não usar para entidades — essas passam pelo Canonicalizer."""
    vistos = set()
    resultado = []
    for item in lista:
        if not item or not item.strip():
            continue
        item_limpo = item.strip()
        chave = item_limpo.lower()
        if chave not in vistos:
            vistos.add(chave)
            resultado.append(item_limpo)
    return resultado

    
class VideoAnalyzer:
    def __init__(self, model_name: str = None):
        self.model_name = model_name or config.MODELO_GEMINI
        self.fallback_model = "gemini-3.5-flash-lite"
        # Usamos v1beta para suporte completo a JSON schema com Pydantic
        self.client = genai.Client(http_options={'api_version': 'v1beta'})

    def _chamar_gemini_com_retry(self, modelo: str, conteudos: list, config_obj: types.GenerateContentConfig, max_tentativas: int = None):
        if max_tentativas is None:
            max_tentativas = config.GEMINI_MAX_TENTATIVAS

        for tentativa in range(1, max_tentativas + 1):
            try:
                return self.client.models.generate_content(
                    model=modelo,
                    contents=conteudos,
                    config=config_obj,
                )
            except Exception as e:
                erro_str = str(e)
                transitorio = (
                    "503" in erro_str
                    or "UNAVAILABLE" in erro_str
                    or "429" in erro_str
                    or "RESOURCE_EXHAUSTED" in erro_str
                )
                if not transitorio or tentativa >= max_tentativas:
                    raise e

                espera = _calcular_espera(tentativa, erro_str)
                print(
                    f"    ⚠️ Erro transitório ({'429' if '429' in erro_str else '503'}). "
                    f"A aguardar {espera:.1f}s antes da tentativa {tentativa + 1}/{max_tentativas}..."
                )
                time.sleep(espera)

    def _fatiar_transcricao(self, blocos: List[Dict[str, Any]], capitulos_originais: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """Divide a transcrição em segmentos temporais (~30 minutos) respeitando capítulos se existirem."""
        duracao_chunk = config.DURACAO_CHUNK_SEGUNDOS
        if not blocos:
            return []

        # Se houver capítulos oficiais estruturados, agrupa-os em fatias equilibradas
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

        # Fatiamento temporal direto contínuo (~30 minutos por fatia)
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
        """Executa a extração estruturada de um segmento específico de vídeo longo."""
        ts_inicio = segmento["ts_inicio"]
        ts_fim = segmento["ts_fim"]
        texto_segmento = segmento["texto"]
        dica_titulo = f"\n- Tema/Capítulo sugerido nos metadados: {segmento['titulo_sugerido']}" if segmento.get('titulo_sugerido') else ""

        prompt = f"""
És um assistente especializado em Gestão de Conhecimento Pessoal (PKM) e síntese técnica para o Obsidian.
Estás a analisar o BLOCO {idx}/{total} de um evento ou conferência técnica longa do YouTube.

CONTEXTO GLOBAL DO VÍDEO:
- Título do Vídeo: {dados_video.get('titulo')}
- Canal: {dados_video.get('canal')}
- Intervalo deste Bloco: {ts_inicio} a {ts_fim}{dica_titulo}

TRANSCRIÇÃO DESTE BLOCO ({ts_inicio} a {ts_fim}):
{texto_segmento}

INSTRUÇÕES DE EXTRAÇÃO PARA ESTE BLOCO:
0. REGRA ESTRITA DE IDIOMAS E NOMES:
   - TÍTULOS DE PALESTRAS/OBRAS: Mantém o título original oficial sem traduzir.
   - NOMES DE PESSOAS: Apenas pessoas com NOME COMPLETO canónico (ex: 'Sarah Friar', 'Satya Nadella'). NUNCA apenas primeiro nome.
   - NOMES DE ARTEFACTOS: Mantém o nome oficial original (ex: 'GPT-4o', 'Claude 3.5 Sonnet', 'Cursor', 'LoRA').
   - TEMAS: Usa a terminologia técnica padrão original (ex: 'Agentic Context', 'Reinforcement Learning'). Se traduzido para pt, coloca entre parênteses.
   - RESUMO: Redige em português claro, formal e correto (PT-PT).

1. Título do Segmento: Título descritivo ou tema da palestra/sessão que decorre neste intervalo ({ts_inicio} - {ts_fim}).
2. Oradores: Nomes completos dos apresentadores ou intervenientes principais deste segmento específico.
3. Resumo do Bloco: 1 a 3 parágrafos densos e claros em português (PT-PT) sobre o conteúdo debatido nesta sessão.
4. Takeaways do Bloco: 2 a 5 ensinamentos essenciais desta sessão.
5. Métricas & Números: Todos os dados quantitativos, percentagens, custos ou benchmarks citados nesta sessão.
6. Tensões, Riscos & Limitações: Dificuldades técnicas, mitos desmontados ou críticas levantadas neste bloco.
7. Agenda & Previsões: Prazos, anúncios futuros ou datas mencionadas nesta sessão.
8. Recursos & Links: Papers, repositórios GitHub ou ferramentas mencionadas.
9. Pessoas: Pessoas relevantes citadas com NOME COMPLETO canónico.
10. Obras: Livros, artigos ou papers citados com títulos originais e autores.
11. Organizações: Empresas ou instituições chave referidas neste segmento.
12. Artefactos: Modelos, ferramentas, frameworks, agentes, hardware, técnicas, plataformas ou datasets citados neste segmento (com os 8 subtipos e fabricante).

Responde estritamente de acordo com o esquema JSON fornecido.
"""
        config_obj = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SegmentoAnalise,
            temperature=0.2,
        )

        try:
            resp = self._chamar_gemini_com_retry(self.model_name, [prompt], config_obj)
        except Exception:
            if self.fallback_model and self.fallback_model != self.model_name:
                resp = self._chamar_gemini_com_retry(self.fallback_model, [prompt], config_obj)
            else:
                raise

        if not resp or not resp.parsed:
            raise ValueError(f"Falha ao analisar o bloco {idx}/{total}.")
        return resp.parsed

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

        for seg in segmentos_analisados:
            todas_pessoas.extend(seg.pessoas)
            todas_obras.extend(seg.obras)
            todas_orgs.extend(seg.organizacoes)
            todos_artefactos.extend(seg.artefactos)
            todos_temas.extend(seg.temas)
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
            resp_sintese = self._chamar_gemini_com_retry(self.model_name, [prompt_sintese], config_obj)
        except Exception:
            if self.fallback_model and self.fallback_model != self.model_name:
                resp_sintese = self._chamar_gemini_com_retry(self.fallback_model, [prompt_sintese], config_obj)
            else:
                raise

        sintese: SinteseGlobal = resp_sintese.parsed

        # ------------------------------------------------------------------
        # Canonicalização de entidades (substitui as desduplicar_* de entidades)
        # ------------------------------------------------------------------
        canon = Canonicalizer()

        pessoas_canon = canon.canonicalizar_pessoas(todas_pessoas)
        artefactos_canon = canon.canonicalizar_artefactos(todos_artefactos)
        obras_canon = canon.canonicalizar_obras(todas_obras)
        organizacoes_canon = canon.canonicalizar_strings("organizacao", todas_orgs)
        temas_canon = canon.canonicalizar_strings("tema", todos_temas)

        canon.gravar()  # persiste aliases.yaml, decisoes.jsonl, revisao.md

        return AnaliseVideo(
            titulo_sugerido=sintese.titulo_sugerido or dados_video.get('titulo'),
            resumo_executivo=sintese.resumo_executivo,
            takeaways_principais=sintese.takeaways_principais,
            metricas_e_numeros=desduplicar_strings(todas_metricas),
            tensoes_e_riscos=desduplicar_strings(todas_tensoes),
            agenda_e_previsoes=desduplicar_strings(todas_agendas),
            recursos_e_links=desduplicar_strings(todos_recursos),
            capitulos=capitulos,
            temas=temas_canon,
            pessoas=pessoas_canon,
            obras=obras_canon,
            organizacoes=organizacoes_canon,
            artefactos=artefactos_canon
        )

    def analisar_video_longo(self, dados_video: Dict[str, Any]) -> AnaliseVideo:
        """Processa um vídeo longo dividindo-o em blocos e consolidando as entidades no final (Map-Reduce)."""
        blocos = dados_video.get("transcricao_blocos") or []
        capitulos_originais = dados_video.get("capitulos_originais") or []
        segmentos = self._fatiar_transcricao(blocos, capitulos_originais)

        duracao_min = (dados_video.get('duracao_segundos') or 0) // 60
        print(f"    🧩 Vídeo longo ({duracao_min} min). A ativar pipeline Map-Reduce em {len(segmentos)} blocos temporais...")

        segmentos_analisados = []
        for i, seg in enumerate(segmentos, 1):
            print(f"       -> [{i:02d}/{len(segmentos):02d}] A analisar bloco: {seg['ts_inicio']} a {seg['ts_fim']}...")
            analise_bloco = self._analisar_segmento(dados_video, seg, i, len(segmentos))
            segmentos_analisados.append(analise_bloco)
            # Pequeno compasso de espera para respeitar cotas de chamadas por minuto
            time.sleep(1)

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

        prompt += """
INSTRUÇÕES ESPECÍFICAS DE EXTRAÇÃO:
0. REGRA ESTRITA DE IDIOMAS E TÍTULOS (MUITO IMPORTANTE):
   - TÍTULOS DE VÍDEOS: Mantém SEMPRE o título na sua língua original (geralmente em inglês). NUNCA traduzas o título do vídeo para português! Apenas remove emojis excessivos ou CAPS LOCK de clickbait.
   - TÍTULOS DE OBRAS (Livros, Artigos, Papers): Mantém SEMPRE o título original oficial na língua de publicação. NUNCA traduzas títulos de livros ou papers!
   - NOMES DE ARTEFACTOS: Mantém SEMPRE o nome oficial (ex: 'GPT-4o', 'Claude 3.5 Sonnet', 'H100 SXM5', 'LoRA'). NUNCA traduzas nem abras nomes de modelos/ferramentas.
   - TEMAS: Usa a terminologia técnica padrão original (geralmente em inglês). Se quiseres incluir a tradução portuguesa, coloca-a OBRIGATORIAMENTE entre parênteses. NUNCA uses termos isolados em português do Brasil.
   - SÍNTESE: O resumo executivo, takeaways e bios devem ser redigidos em português claro, formal e correto (PT-PT).

1. Resumo Executivo: Sintetiza em português os tópicos e conclusões essenciais (2 a 3 parágrafos).
2. Takeaways Principais: Lista de 3 a 7 pontos-chave práticos e de alto valor.
3. Métricas, Números & Dados Quantitativos: Extrai todos os dados concretos citados (ex: percentagens de ganho de eficiência, benchmarks, números financeiros como receitas/burn, contagens de tokens, custos por tarefa, multiplicadores).
4. Tensões, Riscos & Mitos Desmontados: Identifica os pontos de atrito, mitos desmistificados pelos oradores, limitações técnicas dos modelos, riscos de infraestrutura ou pontos de ceticismo qualificado.
5. Agenda & Previsões Futuras: Datas de lançamentos, IPOs, conferências, janelas de publicação ou cronogramas esperados para as próximas semanas/meses.
6. Links, Papers & Recursos Externos: Lista de URLs reais, referências a papers no Arxiv, links no GitHub, posts de blog ou documentação relevante mencionada no vídeo ou na descrição.
7. Capítulos / Timestamps: Lista dos principais capítulos/marcos temporais do vídeo (ex: "00:00 Intro", "03:20 Reading Anthropic S-1"), se presentes na descrição ou transcrição.
8. Temas: 3 a 8 conceitos centrais na terminologia técnica original (com tradução opcional entre parênteses).
9. Pessoas (REGRA DO NOME COMPLETO):
   - Extrai APENAS figuras públicas, cientistas, autores, oradores ou executivos de relevância real com o seu NOME COMPLETO CANÓNICO.
   - NUNCA uses apenas o primeiro nome próprio solto (ex: NUNCA 'Sarah', 'Dom', 'Tim', 'Koen', 'Damien', 'Zach').
   - NÃO coloques empresas ou organizações neste campo — vai para o campo 11.
10. Livros, Artigos e Papers Citados: Obras citadas no título original com o(s) respetivo(s) autor(es).
11. Organizações: Empresas, universidades, laboratórios ou instituições chave referidas (ex: 'OpenAI', 'Google DeepMind', 'NVIDIA', 'Anthropic', 'MIT', 'Hugging Face'). Usa o nome oficial e completo da organização.
12. Artefactos (Modelos, Frameworks, Ferramentas, Agentes, Técnicas, Hardware, Plataformas, Datasets):
   - Extrai TODOS os artefactos técnicos mencionados com o nome oficial.
   - Classifica cada um num dos 8 subtipos: 'modelo', 'framework', 'ferramenta', 'agente', 'tecnica', 'hardware', 'plataforma', 'dataset'.
   - Indica o fabricante/autor quando conhecido. Deixa null se desconhecido.
   - Para cada artefacto, escreve 1-2 frases em português sobre o seu papel/relevância NO CONTEXTO específico do vídeo.

Responde estritamente de acordo com o esquema JSON fornecido.
"""
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
            try:
                response = self._chamar_gemini_com_retry(self.model_name, conteudos, config_obj)
            except Exception as e:
                if self.fallback_model and self.fallback_model != self.model_name:
                    print(f"    🔄 Modelo {self.model_name} indisponível. A alternar para modelo de contingência {self.fallback_model}...")
                    response = self._chamar_gemini_com_retry(self.fallback_model, conteudos, config_obj)
                else:
                    raise e
        finally:
            if arquivo_google:
                try:
                    self.client.files.delete(name=arquivo_google.name)
                except Exception:
                    pass
            if caminho_audio and os.path.exists(caminho_audio):
                try:
                    os.remove(caminho_audio)
                except Exception:
                    pass

        if not response or not response.parsed:
            raise ValueError("O Gemini não devolveu um resultado estruturado válido.")

        # ------------------------------------------------------------------
        # Canonicalização de entidades (passo único também beneficia)
        # ------------------------------------------------------------------
        analise: AnaliseVideo = response.parsed
        canon = Canonicalizer()

        analise.pessoas = canon.canonicalizar_pessoas(analise.pessoas)
        analise.artefactos = canon.canonicalizar_artefactos(analise.artefactos)
        analise.obras = canon.canonicalizar_obras(analise.obras)
        analise.organizacoes = canon.canonicalizar_strings("organizacao", analise.organizacoes)
        analise.temas = canon.canonicalizar_strings("tema", analise.temas)

        canon.gravar()

        return analise

    def analisar(self, dados_video: Dict[str, Any]) -> AnaliseVideo:
        """Decide inteligentemente entre passo único (curtos) ou Map-Reduce (longos)."""
        duracao = dados_video.get("duracao_segundos") or 0
        blocos = dados_video.get("transcricao_blocos")

        # Se for um vídeo longo com transcrição rica, ativa o pipeline Map-Reduce
        if duracao > config.LIMIAR_VIDEO_LONGO_SEGUNDOS and blocos and len(blocos) > 200:
            return self.analisar_video_longo(dados_video)
        else:
            return self.analisar_passo_unico(dados_video)