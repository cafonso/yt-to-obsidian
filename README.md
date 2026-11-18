# 🧠 YouTube to Obsidian Knowledge Graph

Ferramenta automatizada de PKM (Personal Knowledge Management) para transformar vídeos do YouTube num grafo de conhecimento atómico, denso e bidirecional no **Obsidian**, potenciado pelo **Google Gemini 3.5 Flash**.

---

🧠 YouTube to Obsidian Knowledge Graph

Ferramenta automatizada de PKM (Personal Knowledge Management) para transformar vídeos e conferências do YouTube num grafo de conhecimento atómico, denso e bidirecional no Obsidian, potenciado pelo Google Gemini.

🌟 O que a Ferramenta Extrai Sistematicamente

Para cada vídeo ou palestra processada, é criada uma página estruturada em Videos/ com:

📝 Resumo Executivo: Síntese densa e clara em português (PT-PT).

💡 Principais Takeaways: Os 3 a 7 ensinamentos mais valiosos.

📊 Métricas & Números Chave: Percentagens, ganhos de eficiência, dados financeiros, benchmarks e custos de compute.

⚠️ Tensões, Riscos & Mitos Desmontados: Contraditório, limites técnicos dos modelos e mitos desmistificados.

📅 Agenda & Previsões Futuras: Datas de lançamento anunciadas, conferências, janelas de IPOs ou cronogramas.

👤 Pessoas Mencionadas: Apenas figuras com Nome Completo deduzido (ex: Sarah Friar, Satya Nadella), criando notas biográficas dedicadas.

📚 Livros, Artigos & Papers: Título oficial na língua original conectado diretamente com [[link]] ao(s) respetivo(s) autor(es).

🏢 Organizações & Entidades: Laboratórios, empresas e instituições chave.

🔗 Links & Recursos Mencionados: URLs de papers (Arxiv), repositórios GitHub, blogs e ferramentas citadas.

⏱️ Capítulos / Timestamps: Linha temporal navegável.

🏷️ Temas Abordados: Terminologia técnica internacional (ex: Agentic Context (Contexto Agêntico)).

🧩 Artefactos: Modelos, frameworks, ferramentas, agentes, técnicas, hardware, plataformas e datasets (com fabricante associado).

📦 Instalação & Gestão de Dependências

O projeto utiliza pyproject.toml (padrão PEP 621) gerido nativamente pelo uv.

Na raiz do projeto (d:\discoj\code\py\yt):

# Sincronizar o ambiente virtual e instalar dependências principais e de desenvolvimento
uv sync


(Opcional) Caso precises de exportar um requirements.txt tradicional para compatibilidade:

uv export --no-dev --no-hashes -o requirements.txt


🚀 Como Usar no Dia a Dia

# 1. Abrir o Menu Interativo
uv run python main.py

# 2. Processar 1 vídeo diretamente
uv run python main.py "https://www.youtube.com/watch?v=..."

# 3. Processar vídeos da tua lista (apenas os novos)
uv run python main.py --lista lista_de_videos.txt

# 4. Forçar reprocessamento de vídeos anteriores com as novas regras
uv run python main.py --lista lista_de_videos.txt --forcar

# 5. Forçar modo conferência (dividir em notas por palestra) ou nota única
uv run python main.py "https://www.youtube.com/watch?v=..." --split
uv run python main.py "https://www.youtube.com/watch?v=..." --unico


🧪 Executar Testes Automatizados

O projeto dispõe de uma suite de testes unitários e de integração (com simulação de cofres Obsidian temporários) na pasta tests/.

Para executar toda a suite de testes:

uv run pytest


📅 Integração com o Diário (YYYY-MM-DD.md)

O script regista a entrada no diário na data de visualização (data de hoje por defeito, ou a data indicada na lista com cabeçalho # YYYY-MM-DD), mantendo no metadado do vídeo a data original de publicação.

Preservação Total: Nunca apaga o que já escreveste manualmente no diário, injetando o bloco de metadados imediatamente antes de # Resenha do dia (ou no fim do ficheiro).

🛡️ Arquitetura Anti-Bloqueio & Vídeos Longos

Fallback de Áudio: Se o YouTube bloquear o endpoint de legendas, o sistema descarrega automaticamente o áudio leve (.m4a) via yt-dlp e envia-o diretamente para o Gemini Flash.

Pipeline Map-Reduce & The Scout: Vídeos longos são segmentados automaticamente (ffmpeg para áudio ou fatiamento temporal para texto). Caso o vídeo seja uma conferência com múltiplos oradores, o módulo The Scout mapeia a agenda e gera notas atómicas por palestra ligadas a um Índice MOC.

📁 Estrutura do Projeto & do Vault

Repositório

├── analyzer.py          # Comunicação com Gemini, retries/backoff, Map-Reduce e Scout
├── canonicalizer.py     # Resolução determinística e fuzzy match de entidades
├── config.py            # Configurações centralizadas e thresholds
├── extractor.py         # Extração de metadados, legendas e fatiamento via yt-dlp/ffmpeg
├── main.py              # CLI e menu interativo
├── models.py            # Esquemas Pydantic para Structured Outputs
├── utils.py             # Validadores de nomes de pessoas e organizações
├── vault_writer.py      # Escrita estruturada de notas e diários no Obsidian
├── pyproject.toml       # Configuração do projeto, dependências e pytest
└── tests/               # Testes unitários e de integração
    ├── test_pkm.py
    └── test_vault_writer.py


Cofre Obsidian

Videos/ (e subpastas por conferência com respetivo MOC)

Pessoas/, Organizações/, Livros/, Temas/, Artefactos/

.canonicalizacao/ (aliases.yaml, decisoes.jsonl, revisao.md)

YYYY-MM-DD.md (Notas diárias)
