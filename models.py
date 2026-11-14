from typing import List, Optional
from pydantic import BaseModel, Field

class PessoaMencionada(BaseModel):
    nome: str = Field(description="Nome completo da pessoa citada ou interveniente.")
    papel_ou_bio: str = Field(description="Mini-biografia ou papel/relevância desta pessoa no contexto abordado.")

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
