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

class SessaoScout(BaseModel):
    ordem: int = Field(description="Número de ordem sequencial da palestra (1, 2, ...)")
    timestamp_inicio: str = Field(description="Timestamp aproximado de início no formato [HH:MM:SS] ou [MM:SS]")
    segundos_inicio: int = Field(description="Segundo inteiro de início no vídeo para deep link direto")
    timestamp_fim: str = Field(description="Timestamp de fim no formato [HH:MM:SS] ou [MM:SS]")
    segundos_fim: int = Field(description="Segundo inteiro de fim no vídeo")
    orador_principal: Optional[str] = Field(None, description="Nome completo canónico do orador principal (ex: 'Jason Liu'). None se painel ou introdução.")
    organizacao: Optional[str] = Field(None, description="Empresa ou entidade do orador (ex: 'OpenAI', 'Anthropic', 'Warp').")
    titulo_palestra: str = Field(description="Título ou tema específico da palestra na língua original.")
    tipo_sessao: str = Field(default="palestra", description="'palestra', 'keynote', 'painel', 'entrevista' ou 'intervalo'")

class AgendaScout(BaseModel):
    nome_conferencia: str = Field(description="Nome ou acrónimo da conferência (ex: 'AIE CODE 2026', 'AI Engineer Summit 2026')")
    dia: Optional[int] = Field(default=1, description="Número do dia da conferência se aplicável (ex: 1, 2, 3)")
    dia_rotulo: Optional[str] = Field(default=None, description="Rótulo legível do dia (ex: 'Dia 2', 'Day 2')")
    data_sessao: Optional[str] = Field(default=None, description="Data da sessão se indicada (ex: '2026-11-12')")
    eh_conferencia: bool = Field(description="True se o vídeo contiver múltiplas apresentações/oradores; False se for um único orador/monólogo contínuo.")
    sessoes: List[SessaoScout] = Field(description="Lista ordenada de todas as palestras/sessões detetadas.")

class PalestraAnalise(BaseModel):
    titulo_palestra: str = Field(description="Título oficial da palestra na língua original.")
    resumo_executivo: str = Field(description="Resumo claro, denso e aprofundado dos tópicos debatidos nesta palestra em português (2 a 3 parágrafos em PT-PT).")
    takeaways_principais: List[str] = Field(description="Lista com os 3 a 6 ensinamentos mais valiosos desta palestra em português.")
    metricas_e_numeros: List[str] = Field(default_factory=list, description="Números e métricas quantitativas citadas especificamente nesta palestra.")
    tensoes_e_riscos: List[str] = Field(default_factory=list, description="Tensões, riscos, limitações apontadas ou mitos desmontados nesta palestra.")
    agenda_e_previsoes: List[str] = Field(default_factory=list, description="Anúncios futuros, prazos ou expectativas citadas nesta palestra.")
    recursos_e_links: List[str] = Field(default_factory=list, description="Links reais, repositórios GitHub, papers ou ferramentas citadas nesta palestra.")
    temas: List[str] = Field(default_factory=list, description="Conceitos técnicos centrais desta palestra.")
    pessoas: List[PessoaMencionada] = Field(default_factory=list, description="Pessoas relevantes citadas com nome completo canónico.")
    obras: List[ObraCitada] = Field(default_factory=list, description="Livros, artigos ou papers citados com títulos originais e autores.")
    organizacoes: List[str] = Field(default_factory=list, description="Organizações ou empresas mencionadas nesta palestra.")
    artefactos: List[ArtefactoIA] = Field(default_factory=list, description="Modelos, frameworks, ferramentas, hardware ou plataformas citados nesta palestra.")

