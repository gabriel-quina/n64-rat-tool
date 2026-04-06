# romtool

MVP em Python para análise de ROM `.z64` (Nintendo 64) focado em fluxo de tradução/hacking com estratégia **analisar uma vez e reutilizar sempre**.

## Visão geral

O `romtool` implementa pipeline ponta a ponta:

1. Inicializa workspace e banco SQLite.
2. Importa ROM e registra fingerprint (MD5/SHA1 + metadados).
3. Escaneia candidatos de texto CP932/Shift-JIS com heurísticas explícitas.
4. Persiste candidatos com `string_uid` estável.
5. Exporta em JSONL para tradução/revisão.
6. Evita reanálise via cache por combinação:
   - fingerprint da ROM
   - profile
   - `schema_version`
   - `analysis_version`

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Uso rápido

```bash
python -m romtool init
python -m romtool import-rom --rom roms/base.z64
python -m romtool scan-text
python -m romtool scan-text --start 0x00640400 --end 0x00640950
python -m romtool stats
python -m romtool export-strings --out work/strings.jsonl
```

Comandos extras:

```bash
python -m romtool list-strings --limit 20
python -m romtool show-string --id STR_00640534_NUL
python -m romtool find-offset --offset 0x00640534
python -m romtool dump-range --start 0x640000 --end 0x640040
python -m romtool dump-range --start 0x640000 --end 0x640040 --mode raw
python -m romtool dump-range --start 0x640400 --end 0x640950 --mode decode --encoding cp932
python -m romtool dump-range --start 0x640400 --end 0x640950 --mode annotate --encoding cp932
python -m romtool find-offset --offset 0x6404AC
python -m romtool list-range-candidates --start 0x640400 --end 0x640950
```

## Heurística de scanner (foco em precisão)

O scanner:
- exige **âncora plausível de início** (início do range, pós-NUL, pós-byte não textual ou transição de janela binária→textual);
- valida runs CP932 e aplica score de composição;
- mede `useful_chars` e score por tipo de candidata;
- seleciona apenas melhores candidatas com estratégia de **non-overlap / longest-match**.

Classificação:
- `nul_candidate`: run seguida por byte `0x00`.
- `fixed_candidate`: run sem terminador NUL com threshold mais alto (mais conservador).

### Thresholds por profile

No profile `generic_n64` (arquivo `romtool/profiles/generic_n64.py`) você pode ajustar:
- `min_useful_chars_nul` / `min_score_nul`;
- `min_useful_chars_fixed` / `min_score_fixed`;
- regras de âncora (`anchor_*`);
- janela de transição binária (`binary_window`, `binary_textish_ratio_max`);
- `max_overlap_bytes`;
- `exclude_ranges`.

### Scan por range e cache

- Full scan (`scan-text` sem range) usa cache por `rom + profile + schema + analysis_version`.
- Scan com `--start/--end` **não usa cache de full scan** e registra a faixa em `analysis_run.notes`.

Exemplo:

```bash
python -m romtool scan-text --start 0x00640400 --end 0x00640950 --force
```

### Como interpretar melhor o resultado

- Prefira começar por `stats` para ver total por tipo, médias de tamanho e top scores.
- Use `list-strings` para inspeção rápida da qualidade textual.
- Use `find-offset` para validar offsets conhecidos de bancos de texto.

## Limitações (MVP)

- Não detecta ponteiros/referências de texto.
- Não faz reinserção de texto.
- Não manipula compressão/patch/checksum N64.
- Scanner heurístico simples (determinístico e extensível, mas não “perfeito”).

## Roadmap

- Profiles específicos por jogo (faixas excluídas e heurísticas calibradas).
- Segmentação por blocos conhecidos.
- Pipeline de reinserção segura.
- Suporte a encodings múltiplos por profile.
- Análise de ponteiros.


## dump-range como visualizador de script

O comando `dump-range` agora tem modos explícitos orientados a reverse engineering:

- `--mode raw`: hexdump com offset por linha (`--chunk-size` configurável).
- `--mode decode`: mostra `raw` + `decoded` por chunk, com decode seguro (`errors=replace`).
- `--mode annotate`: visão heurística de script com `prefix`, `text_guess` e `suffix` para ajudar a separar texto de bytes de controle.

Flags úteis:

- `--encoding cp932` (default atual).
- `--chunk-size 16` (ou 32, etc.) para `raw/decode`.
- `--only-text` para esconder trechos pouco textuais em `decode/annotate`.
- `--json` para saída estruturada em tooling.

Exemplo de saída (`annotate`, simplificado):

```text
0x006404AC
raw: 8166824f824f...
decoded: ’００わかりました。それでは...
prefix: <CMD_8166><TEXTLIKE_824F><TEXTLIKE_824F>
text_guess: わかりました。それでは...
suffix: <TEXTLIKE_8142><CMD_8170><CMD_8184>
```
