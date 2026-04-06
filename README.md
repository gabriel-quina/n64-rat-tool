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
python -m romtool stats
python -m romtool export-strings --out work/strings.jsonl
```

Comandos extras:

```bash
python -m romtool list-strings --limit 20
python -m romtool show-string --id STR_00640534_NUL
python -m romtool dump-range --start 0x640000 --end 0x640040
```

## Heurística de score (MVP)

O scanner:
- percorre bytes da ROM;
- agrupa runs válidos CP932 (ASCII imprimível, single-byte permitido, pares multibyte válidos);
- tenta decode por encoding do profile;
- calcula `confidence` com base em:
  - taxa de caracteres imprimíveis;
  - presença de japonês (kana/kanji/pontuação JP) e alfanuméricos;
  - penalidade por caracteres suspeitos (`\ufffd`, `NUL` em texto).

Classificação:
- `nul_candidate`: run seguida por byte `0x00`.
- `fixed_candidate`: run plausível sem terminador NUL.

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
