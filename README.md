# 🧠 YouTube to Obsidian Knowledge Graph

Ferramenta automatizada de PKM (Personal Knowledge Management) para transformar vídeos e conferências do YouTube num grafo de conhecimento atómico, denso e bidirecional no Obsidian, potenciado pelo Google Gemini.

## 🌟 O que a Ferramenta Extrai Sistematicamente

Para cada vídeo ou palestra processada, é criada uma página estruturada em `Videos/` com:

* **📝 Resumo Executivo:** Síntese densa e clara em português (PT-PT).
* **💡 Principais Takeaways:** Os 3 a 7 ensinamentos mais valiosos.
* **📊 Métricas & Números Chave:** Percentagens, ganhos de eficiência, dados financeiros, benchmarks e custos de compute.
* **⚠️ Tensões, Riscos & Mitos Desmontados:** Contraditório, limites técnicos dos modelos e mitos desmistificados.
* **📅 Agenda & Previsões Futuras:** Datas de lançamento anunciadas, conferências, janelas de IPOs ou cronogramas.
* **👤 Pessoas Mencionadas:** Apenas figuras com Nome Completo deduzido (ex.: Sarah Friar, Satya Nadella), criando notas biográficas dedicadas.
* **📚 Livros, Artigos & Papers:** Título oficial na língua original conectado diretamente com `[[link]]` ao(s) respetivo(s) autor(es).
* **🏢 Organizações & Entidades:** Laboratórios, empresas e instituições chave.
* **🔗 Links & Recursos Mencionados:** URLs de papers (arXiv), repositórios GitHub, blogs e ferramentas citadas.
* **⏱️ Capítulos / Timestamps:** Linha temporal navegável.
* **🏷️ Temas Abordados:** Terminologia técnica internacional (ex.: Agentic Context).
* **🧩 Artefactos:** Modelos, frameworks, ferramentas, agentes, técnicas, hardware, plataformas e datasets (com fabricante associado).

## 📦 Instalação & Gestão de Dependências

O projeto utiliza `pyproject.toml` (padrão PEP 621) gerido nativamente pelo `uv`. Na raiz do projeto (`d:\discoj\code\py\yt`):

```powershell
# Sincronizar o ambiente virtual e instalar dependências principais e de desenvolvimento
uv sync