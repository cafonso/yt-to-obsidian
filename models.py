from typing import List, Optional, Literal
from pydantic import BaseModel, Field

# Subtipos válidos para artefactos
SubtipoArtefacto = Literal[
    "modelo", "framework", "ferramenta", "agente",
    "tecnica", "hardware", "plataforma", "dataset",
]

class PessoaMencionada(BaseModel):
    nome: str = Field(description="Nome completo da pessoa citada ou interveniente.")
    papel_ou_bio: str = Field(description="Mini-biografia ou papel/relevância desta pessoa no contexto abordado.")

class ArtefactoIA(BaseModel):
    nome: str = Field(description="Nome oficial do artefacto (ex: 'GPT-4o', 'LangChain', 'H100 SXM5').")
    subtipo: SubtipoArtefacto = Field(
        description="Um de: 'modelo', 'framework', 'ferramenta', 'agente', 'tecnica', 'hardware', 'plataforma', 'dataset'."
    )
    fabricante_ou_autor: Optional[str] = Field(
        None,
        description="Empresa, organização ou pessoa que criou o artefacto (ex: 'OpenAI', 'Google DeepMind', 'NVIDIA'). None se desconhecido."
    )
    descricao: Optional[str] = Field(
        None,
        description="Papel ou relevância do artefacto no contexto específico do vídeo (1-2 frases em português)."
    )

class ObraCitada(BaseModel):
    titulo: str = Field(description="Título oficial da obra na língua original (NUNCA traduzir, ex: 'Thinking, Fast and Slow', 'Attention Is All You Need').")
    tipo: str = Field(default="Livro", description="Tipo de obra: 'Livro', 'Artigo', 'Paper' ou 'Ensaio'.")
    autores: List[str] = Field(default_factory=list, description="Lista de autor(es) da obra citada.")
    contexto: Optional[str] = Field(None, description="Breve nota sobre porque foi citado ou a ideia central retirada da obra.")

class AnaliseVideo(BaseModel):
    titulo_sugerido: str = Field(description="Título do vídeo na sua língua original (NUNCA traduzir, apenas limpar emojis excessivos ou caps lock de clickbait).")
    resumo_executivo: str = Field(description="Resumo claro dos pontos essenciais discutidos no vídeo em português (2 a 3 parágrafos).")
    takeaways_principais: List[str] = Field(description="Lista com os 3 a 7 ensinamentos ou ideias mais valiosas em português.")
    metricas_e_numeros: List[str] = Field(default_factory=list, description="Números que marcaram o vídeo: percentagens, valores financeiros, métricas de eficiência, benchmarks e dados quantitativos concretos.")
    tensoes_e_riscos: List[str] = Field(default_factory=list, description="Tensões, riscos, limitações apontadas, mitos desmontados ou pontos de ceticismo levantados.")
    agenda_e_previsoes: List[str] = Field(default_factory=list, description="Agenda futura: datas de lançamento esperadas, cronogramas, eventos, conferências ou marcos previstos.")
    recursos_e_links: List[str] = Field(default_factory=list, description="Links reais, papers no Arxiv, repositórios GitHub, ferramentas ou referências mencionadas na descrição ou vídeo.")
    capitulos: List[str] = Field(default_factory=list, description="Capítulos ou marcos temporais principais com timestamp e título, se disponíveis.")
    temas: List[str] = Field(description="Temas e conceitos em terminologia técnica padrão (língua original/inglês; se traduzido para pt, colocar entre parênteses).")
    pessoas: List[PessoaMencionada] = Field(default_factory=list, description="Pessoas relevantes citadas ou presentes no vídeo com nome completo.")
    obras: List[ObraCitada] = Field(default_factory=list, description="Livros, artigos, papers e ensaios citados no vídeo com títulos originais e autores.")
    organizacoes: List[str] = Field(default_factory=list, description="Empresas, instituições, universidades ou entidades mencionadas.")
    artefactos: List[ArtefactoIA] = Field(default_factory=list, description="Modelos de IA, frameworks, ferramentas, agentes, técnicas, hardware especializado, plataformas e datasets mencionados no vídeo.")

class SegmentoAnalise(BaseModel):
    timestamp_inicio: str = Field(description="Timestamp inicial do segmento, ex: '[00:00:00]' ou '[01:30:00]'.")
    timestamp_fim: str = Field(description="Timestamp final do segmento, ex: '[00:35:00]'.")
    titulo_segmento: str = Field(description="Título claro ou tema da apresentação/palestra deste bloco no idioma original.")
    oradores_ou_apresentadores: List[str] = Field(default_factory=list, description="Nome completo dos oradores ou intervenientes principais deste segmento.")
    resumo_bloco: str = Field(description="Resumo claro e aprofundado dos pontos essenciais deste segmento em português (1 a 3 parágrafos).")
    takeaways_bloco: List[str] = Field(default_factory=list, description="Lista com 2 a 5 ensinamentos ou ideias essenciais deste bloco em português.")
    metricas_e_numeros: List[str] = Field(default_factory=list, description="Métricas, percentagens, números de compute, benchmarks ou dados quantitativos citados neste bloco.")
    tensoes_e_riscos: List[str] = Field(default_factory=list, description="Tensões, riscos técnicos, limitações ou mitos desmontados neste bloco.")
    agenda_e_previsoes: List[str] = Field(default_factory=list, description="Previsões, anúncios de lançamentos futuros ou datas neste bloco.")
    recursos_e_links: List[str] = Field(default_factory=list, description="Links reais, papers no Arxiv, repositórios GitHub, blogs ou ferramentas citadas.")
    temas: List[str] = Field(default_factory=list, description="Termos técnicos e conceitos centrais abordados neste segmento.")
    pessoas: List[PessoaMencionada] = Field(default_factory=list, description="Pessoas relevantes citadas com nome completo canónico.")
    obras: List[ObraCitada] = Field(default_factory=list, description="Obras citadas com títulos originais e autores.")
    organizacoes: List[str] = Field(default_factory=list, description="Organizações ou empresas mencionadas neste bloco.")
    artefactos: List[ArtefactoIA] = Field(default_factory=list, description="Modelos, frameworks, ferramentas, agentes, hardware, plataformas ou datasets citados.")

class SinteseGlobal(BaseModel):
    titulo_sugerido: str = Field(description="Título do vídeo na língua original (limpo de clickbait).")
    resumo_executivo: str = Field(description="Resumo executivo global coeso dos pontos essenciais discutidos em todo o vídeo/evento em português (2 a 4 parágrafos).")
    takeaways_principais: List[str] = Field(description="Lista com os 5 a 10 ensinamentos ou conclusões transversais mais valiosas de todo o evento em português.")
