# Snapshot dos frontmatters gerados por `vault_writer.ObsidianVaultWriter`

## Pessoas (`salvar_ou_atualizar_pessoa`)

```yaml
---
tipo: pessoa
tags:
  - pessoa
aliases: []
---
# {pessoa.nome}

> {pessoa.papel_ou_bio}

### 📚 Obras Relacionadas:
- [[obra_1]]
- [[obra_2]]

### 📹 Mencionada nos Vídeos:
- {video_link}
```

## Organizações (`salvar_ou_atualizar_organizacao`)

```yaml
---
tipo: organizacao
tags:
  - organizacao
aliases: []
---
# {nome}

### 🧩 Artefactos:
- [[Artefacto 1]]
- [[Artefacto 2]]

### 📹 Mencionada nos Vídeos:
- {video_link}
```

## Obras (`salvar_ou_atualizar_obra`)

```yaml
---
tipo: {obra.tipo.lower()}
autores: {autores_links}
tags:
  - {obra.tipo.lower()}
---
# {obra.titulo}

**Tipo:** {obra.tipo}  
**Autor(es):** {autores_str}

> {obra.contexto}

### 📹 Mencionado nos Vídeos:
- {video_link}
```

## Temas (`salvar_ou_atualizar_tema`)

```yaml
---
tipo: tema
tags:
  - tema
---
# {tema}

### 📹 Vídeos sobre este tema:
- {video_link}
```

## Artefactos (`salvar_ou_atualizar_artefacto`)

```yaml
---
tipo: artefacto
subtipo: {subtipo}
fabricante: {fabricante_link}
tags:
  - artefacto/{subtipo}
---
# {artefacto.nome}

**Subtipo:** {subtipo}  
**Fabricante/Autor:** {fabricante_link or "Desconhecido"}

> {artefacto.descricao}

### 📹 Mencionado nos Vídeos:
- {video_link}
```

> NOTA: Este ficheiro é só um snapshot de referência para rever/ajustar o esquema
> de frontmatter (por ex. compatibilidade com Dataview/Linter). Não é usado pelo
> código em runtime.
