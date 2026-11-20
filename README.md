# 🧠 YouTube to Obsidian Knowledge Graph

Ferramenta automatizada de PKM (*Personal Knowledge Management*) para transformar vídeos e conferências do YouTube num grafo de conhecimento atómico, denso e bidirecional no Obsidian, potenciado pelo Google Gemini.

## 🌟 O que a Ferramenta Extrai Sistematicamente

Para cada vídeo ou palestra processada, é criada uma página estruturada em `Videos/` com:

- **📝 Resumo Executivo:** Síntese densa e clara em português (PT-PT).
- **💡 Principais Takeaways:** Os 3 a 7 ensinamentos mais valiosos.
- **📊 Métricas & Números Chave:** Percentagens, ganhos de eficiência, dados financeiros, benchmarks e custos de *compute*.
- **⚠️ Tensões, Riscos & Mitos Desmontados:** Contraditório, limites técnicos dos modelos e mitos desmistificados.
- **📅 Agenda & Previsões Futuras:** Datas de lançamento anunciadas, conferências, janelas de IPOs ou cronogramas.
- **👤 Pessoas Mencionadas:** Apenas figuras com Nome Completo deduzido (ex.: Sarah Friar, Satya Nadella), criando notas biográficas dedicadas.
- **📚 Livros, Artigos & Papers:** Título oficial na língua original conectado diretamente com `[[link]]` ao(s) respetivo(s) autor(es).
- **🏢 Organizações & Entidades:** Laboratórios, empresas e instituições chave.
- **🔗 Links & Recursos Mencionados:** URLs de *papers* (arXiv), repositórios GitHub, blogs e ferramentas citadas.
- **⏱️ Capítulos / Timestamps:** Linha temporal navegável.
- **🏷️ Temas Abordados:** Terminologia técnica internacional (ex.: *Agentic Context*).
- **🧩 Artefactos:** Modelos, *frameworks*, ferramentas, agentes, técnicas, *hardware*, plataformas e *datasets* (com fabricante associado).

## 📦 Instalação & Gestão de Dependências

O projeto utiliza `pyproject.toml` (padrão PEP 621) gerido nativamente pelo `uv`. Na raiz do projeto, podes usar os seguintes comandos:

### Sincronizar o ambiente virtual e instalar dependências principais e de desenvolvimento

```bash
uv sync
```

### 1. Abrir o Menu Interativo

```bash
uv run python main.py
```

### 2. Processar 1 vídeo diretamente

```bash
uv run python main.py "https://www.youtube.com/watch?v=..."
```

### 3. Processar vídeos da tua lista (apenas os novos)

```bash
uv run python main.py --lista lista_de_videos.txt
```

### 4. Forçar reprocessamento de vídeos anteriores com as novas regras

```bash
uv run python main.py --lista lista_de_videos.txt --forcar
```

### 5. Forçar modo conferência (dividir em notas por palestra) ou nota única

```bash
uv run python main.py "https://www.youtube.com/watch?v=..." --split
uv run python main.py "https://www.youtube.com/watch?v=..." --unico
```

### 6. Usar a interface web

```bash
uv run streamlit run app.py
```

### 7. 🧪 Executar Testes Automatizados

A suíte de testes unitários e de integração (com simulação de cofres Obsidian temporários) está em `tests/`:

```bash
uv run pytest
```

## 📅 Integração com o Diário (`YYYY-MM-DD.md`)

- **Data de leitura vs. publicação:** Regista a entrada na data de visualização (hoje por defeito, ou a data indicada na lista com `# YYYY-MM-DD`), mantendo no metadado do vídeo a data original de publicação.
- **Preservação total:** Nunca apaga o que escreveste manualmente; injeta o bloco antes de `# Resenha do dia` (ou no fim do ficheiro).

## 🛡️ Arquitetura Anti-Bloqueio & Vídeos Longos

- **Fallback de áudio:** Se o YouTube bloquear o *endpoint* de legendas, descarrega o áudio leve (`.m4a`) via `yt-dlp` e envia para o Gemini.
- **Pipeline Map-Reduce & The Scout:** Vídeos longos são segmentados (`ffmpeg` para áudio ou fatiamento temporal para texto). Se for conferência com vários oradores, o *The Scout* mapeia a agenda e gera notas por palestra ligadas a um Índice MOC.

## 📁 Estrutura da aplicação

```text
├── app.py               # Interface web em Streamlit (processar, revisão, histórico)
├── analyzer.py          # Comunicação com Gemini, retries/backoff, Map-Reduce e Scout
├── canonicalizer.py     # Resolução determinística e fuzzy match de entidades
├── config.py            # Configurações centralizadas e thresholds
├── extractor.py         # Extração de metadados, legendas e fatiamento via yt-dlp/ffmpeg
├── main.py              # CLI, menu interativo e orquestração do pipeline
├── models.py            # Esquemas Pydantic para Structured Outputs
├── README.md            # Documentação do projeto
├── utils.py             # Validadores de nomes de pessoas, organizações e utilitários
├── vault_writer.py      # Escrita estruturada de notas, validação de links e diários
├── pyproject.toml       # Configuração do projeto, dependências e pytest
├── scripts/             # Utilitários auxiliares fora do pipeline principal
│   ├── listar_modelos.py
│   └── resumir_projecto.py
└── tests/               # Testes unitários e de integração
    ├── test_pkm.py
    └── test_vault_writer.py
```

## 🗂️ Cofre Obsidian

- `Videos/` (e subpastas por conferência com respetivo MOC)
- `Pessoas/`, `Organizações/`, `Livros/`, `Temas/`, `Artefactos/`
- `.canonicalizacao/` (`aliases.yaml`, `decisoes.jsonl`, `revisao.md`)
- `YYYY-MM-DD.md` (Notas diárias)