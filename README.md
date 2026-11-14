# 🧠 YouTube to Obsidian Knowledge Graph

Ferramenta automatizada de PKM (Personal Knowledge Management) para transformar vídeos do YouTube num grafo de conhecimento atómico, denso e bidirecional no **Obsidian**, potenciado pelo **Google Gemini 2.5 Flash**.

---

## 🌟 O que a Ferramenta Extrai Sistematicamente

Para cada vídeo processado, é criada uma página estruturada em `Videos/` com:
1. **📝 Resumo Executivo:** Síntese densa e clara em português (PT-PT).
2. **💡 Principais Takeaways:** Os 3 a 7 ensinamentos mais valiosos.
3. **📊 Métricas & Números Chave:** Percentagens, ganhos de eficiência, dados financeiros, benchmarks e custos de compute.
4. **⚠️ Tensões, Riscos & Mitos Desmontados:** Contraditório, limites técnicos dos modelos e mitos desmistificados.
5. **📅 Agenda & Previsões Futuras:** Datas de lançamento anunciadas, conferências, janelas de IPOs ou cronogramas.
6. **👤 Pessoas Mencionadas:** Apenas figuras com **Nome Completo** deduzido (ex: `Sarah Friar`, `Satya Nadella`), criando notas biográficas dedicadas.
7. **📚 Livros, Artigos & Papers:** Título oficial na língua original (sem tradução artificial) conectado diretamente com `[[link]]` ao(s) respetivo(s) autor(es).
8. **🏢 Organizações & Entidades:** Laboratórios, empresas e instituições chave.
9. **🔗 Links & Recursos Mencionados:** URLs de papers (Arxiv), repositórios GitHub, blogs e ferramentas citadas.
10. **⏱️ Capítulos / Timestamps:** Linha temporal navegável.
11. **🏷️ Temas Abordados:** Terminologia técnica internacional (ex: `Agentic Context (Contexto Agêntico)`).
12. **Artefactos:** Modelos, ferramentas 

---

## 📅 Integração com o Diário (`YYYY-MM-DD.md`)

* O script deteta a data do vídeo e escreve tal como característica do vídeo.
* **Preservação Total:** Nunca apaga o que já escreveste manualmente no diário.
* Injeta de forma cirúrgica uma secção:
  ```markdown
  ## 📹 Vídeos Analisados & Resumos
  - [[2026-11-07 - What Is Agentic Context Hermes, Honcho Memory & Obsidian LLM Wiki]] — *Wanderloots*
  ```

---

## 🚀 Como Usar no Dia a Dia

A partir desta pasta (`d:\discoj\code\py\yt`):

```bash
# 1. Abrir o Menu Interativo
uv run python main.py

# 2. Processar 1 vídeo diretamente
uv run python main.py "https://www.youtube.com/watch?v=..."

# 3. Processar vídeos da tua lista (apenas os novos)
uv run python main.py --lista lista_de_videos.txt

# 4. Forçar reprocessamento de vídeos anteriores com as novas regras
uv run python main.py --lista lista_de_videos.txt --forcar

# 5. Se a lista tiver uma linha com data essa será considerada a data da entrado do diário
```

---

## 🛡️ Arquitetura Anti-Bloqueio do YouTube

Se o YouTube bloquear o teu IP no endpoint de legendas:
* O sistema descarrega automaticamente o áudio leve (`.m4a` em 1 segundo) via `yt-dlp`.
* Envia o áudio para o Gemini Flash, que **escuta diretamente o áudio** e faz a extração completa.
* Remove o áudio temporário após o processamento.

---

### Resumo do que foi atualizado face à versão anterior

| Secção | Alteração |
|---|---|
| Lista de extração | Passou de 11 para 12 pontos; **Artefactos** e **Organizações** ganharam destaque. |
| **Nova secção "Artefactos — 8 Subtipos"** | Tabela com os 8 subtipos e exemplos; distinção `ferramenta` vs `agente`; heurística de fabricante. |
| Diário | Corrigido: usa **data de leitura**, não data de publicação; bloco real injetado (antes de `# Resenha do dia`). |
| Como usar | Menciona suporte a cabeçalhos `# YYYY-MM-DD` no `lista_de_videos.txt`. |
| Anti-bloqueio | Atualizado: cascata pt/en/es → fallback legendas automáticas; `cookies.txt` opcional. |
| **Nova secção "Estrutura de Ficheiros"** | Árvore do projeto; nota sobre `transcricao*.py` obsoletos. |
| **Nova secção "Estrutura do Vault"** | Inclui `Artefactos/` e `Organizações/`. |
| **Nova secção "Variáveis de Ambiente"** | Tabela com `OBSIDIAN_VAULT_PATH` e `GEMINI_MODEL`. |
| **Nova secção "Limitações Conhecidas"** | Honestidade sobre falsos positivos e dependência de áudio. |
---

### Resumo do que foi atualizado face à versão anterior

| Secção | Alteração |
|---|---|
| Lista de extração | Passou de 11 para 12 pontos; **Artefactos** e **Organizações** ganharam destaque. |
| **Nova secção "Artefactos — 8 Subtipos"** | Tabela com os 8 subtipos e exemplos; distinção `ferramenta` vs `agente`; heurística de fabricante. |
| Diário | Corrigido: usa **data de leitura**, não data de publicação; bloco real injetado (antes de `# Resenha do dia`). |
| Como usar | Menciona suporte a cabeçalhos `# YYYY-MM-DD` no `lista_de_videos.txt`. |
| Anti-bloqueio | Atualizado: cascata pt/en/es → fallback legendas automáticas; `cookies.txt` opcional. |
| **Nova secção "Estrutura de Ficheiros"** | Árvore do projeto; nota sobre `transcricao*.py` obsoletos. |
| **Nova secção "Estrutura do Vault"** | Inclui `Artefactos/` e `Organizações/`. |
| **Nova secção "Variáveis de Ambiente"** | Tabela com `OBSIDIAN_VAULT_PATH` e `GEMINI_MODEL`. |
| **Nova secção "Limitações Conhecidas"** | Honestidade sobre falsos positivos e dependência de áudio. |
