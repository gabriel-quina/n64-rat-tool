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


## Papel de `dump-range`

`dump-range` é o visualizador de inspeção manual de script e complementa o scanner persistente:

- **raw**: bytes crus com offsets para confirmar ranges e alinhamento.
- **decode**: bytes crus + texto decodificado (CP932/Shift-JIS) por chunk, preservando unicode e tolerando bytes inválidos.
- **annotate**: camada heurística orientada a engenharia reversa para destacar blocos textuais plausíveis e cercas de controle (`prefix/suffix` com tokens neutros como `<CMD_8166>`).

Diferença conceitual:

1. **Bytes crus** (`raw_hex`): fonte da verdade binária.
2. **Texto decodificado** (`decoded`): interpretação de encoding com substituição segura em falhas.
3. **Anotação heurística** (`text_guess`, `prefix_tokens`, `suffix_tokens`): hipótese operacional para acelerar estudo de control codes sem afirmar semântica definitiva.

Comandos auxiliares:

- `find-offset`: encontra candidatos persistidos que cobrem um offset específico.
- `list-range-candidates`: lista candidatos persistidos que intersectam um intervalo.
