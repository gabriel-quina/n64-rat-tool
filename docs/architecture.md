# Arquitetura

## Objetivo

Criar base estável para análise incremental de ROM N64 com persistência em SQLite, exportação para tradução e reuso de resultados.

## Estrutura

```text
romtool/
  cli.py
  db.py
  models.py
  rom.py
  scanner.py
  exporter.py
  profiles/
    base.py
    generic_n64.py
```

## Modelo de dados

### `rom`
- fingerprint (MD5/SHA1), tamanho, formato, byte order, caminho.

### `analysis_run`
- execução de análise (profile, versões, status, timestamps).
- usada para cache determinístico e auditoria.

### `string_candidate`
- candidatos de texto:
  - offsets
  - bytes crus (`raw_hex`)
  - texto decodificado / normalizado
  - score / tipo
  - `string_uid` estável (ex.: `STR_00640534_NUL`)

### `segment`
- reservado para metadados de faixas (extensão futura).

## Fluxo de scan

1. Carrega ROM importada mais recente.
2. Resolve profile (`generic_n64` por padrão).
3. Verifica cache (`analysis_run` sucesso com mesmas versões/profile/rom).
4. Se cache miss (ou `--force`):
   - percorre ROM byte a byte;
   - agrupa runs válidos CP932;
   - tenta decode;
   - pontua e classifica (`nul_candidate`/`fixed_candidate`);
   - persiste resultados sem duplicar (`INSERT OR IGNORE` + UID estável).

## Profiles

`profiles/base.py` define interface/configuração.

Para novo profile:
1. Criar módulo em `romtool/profiles/<nome>.py`.
2. Instanciar `BaseProfile` com:
   - `encodings`
   - `heuristic`
   - `exclude_ranges`
3. Integrar seleção de profile na CLI (futuro: `--profile`).

## Decisões de MVP

- SQLite nativo (`sqlite3`), sem ORM.
- Estruturas tipadas com `dataclasses`.
- CLI com `argparse`.
- Scanner explícito em funções pequenas para facilitar extensão e testes.
