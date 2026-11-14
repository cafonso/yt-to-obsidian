import os
import time
from typing import Dict, Any
from google import genai
from google.genai import types
from models import AnaliseVideo

class VideoAnalyzer:
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.model_name = model_name
        self.fallback_model = "gemini-3.5-flash-lite"
        # Usamos v1beta para suporte completo a JSON schema com Pydantic
        self.client = genai.Client(http_options={'api_version': 'v1beta'})

    def _chamar_gemini_com_retry(self, modelo: str, conteudos: list, config: types.GenerateContentConfig, max_tentativas: int = 3):
        for tentativa in range(1, max_tentativas + 1):
            try:
                return self.client.models.generate_content(
                    model=modelo,
                    contents=conteudos,
                    config=config
                )
            except Exception as e:
                erro_str = str(e)
                if "503" in erro_str or "UNAVAILABLE" in erro_str or "429" in erro_str:
                    if tentativa < max_tentativas:
                        espera = tentativa * 3
                        print(f"    ⚠️ Modelo sobrecarregado (503/429). A tentar novamente em {espera}s (tentativa {tentativa}/{max_tentativas})...")
                        time.sleep(espera)
                        continue
                raise e

    def analisar(self, dados_video: Dict[str, Any]) -> AnaliseVideo:
        """Envia transcrição ou áudio + metadados ao Gemini para extração estruturada."""
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
   - TÍTULOS DE VÍDEOS: Mantém SEMPRE o título na sua língua original (geralmente em inglês). NUNCA traduzas o título do vídeo para português! Apenas remove emojis excessivos ou CAPS LOCK de clickbait (ex: "NEW Claude Model LEAKED?!" -> "New Claude Model Leaked").
   - TÍTULOS DE OBRAS (Livros, Artigos, Papers): Mantém SEMPRE o título original oficial na língua de publicação (ex: 'Thinking, Fast and Slow', 'Attention Is All You Need', 'The Stacks Project'). NUNCA traduzas títulos de livros ou papers!
   - TEMAS: Usa a terminologia técnica padrão original (geralmente em inglês, ex: 'Artificial Intelligence', 'Agentic Context', 'Large Language Models', 'Reinforcement Learning'). Se quiseres incluir a tradução portuguesa, coloca-a OBRIGATORIAMENTE entre parênteses (ex: 'Agentic Context (Contexto Agêntico)'). NUNCA uses termos isolados em português do Brasil.
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
10. Livros, Artigos e Papers Citados: Obras citadas no título original com o(s) respetivo(s) autor(es).
11. Organizações: Empresas, universidades, laboratórios ou instituições chave referidas.

Responde estritamente de acordo com o esquema JSON fornecido.
"""
        config = types.GenerateContentConfig(
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
                response = self._chamar_gemini_com_retry(self.model_name, conteudos, config)
            except Exception as e:
                if self.fallback_model and self.fallback_model != self.model_name:
                    print(f"    🔄 Modelo {self.model_name} indisponível. A alternar para modelo de contingência {self.fallback_model}...")
                    response = self._chamar_gemini_com_retry(self.fallback_model, conteudos, config)
                else:
                    raise e
        finally:
            # Limpeza: remove o ficheiro da API da Google
            if arquivo_google:
                try:
                    self.client.files.delete(name=arquivo_google.name)
                except Exception:
                    pass
            # Limpeza local: remove o ficheiro de áudio temporário do disco
            if caminho_audio and os.path.exists(caminho_audio):
                try:
                    os.remove(caminho_audio)
                except Exception:
                    pass

        if not response or not response.parsed:
            raise ValueError("O Gemini não devolveu um resultado estruturado válido.")

        return response.parsed
