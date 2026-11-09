# 28 — `csvrepair` (fix broken CSVs, with a change report)

> **Difficulty 3/10** · **Effort ~3 days** · **Tier: medium**
> **Prior art: ⚠️ partial** — `csvkit`'s `csvclean` (unquoted commas / ragged rows), `csv.Sniffer` (stdlib dialect guess), `charset-normalizer`/`chardet`, `iconv`, `miller`'s `--ipp`, Excel/Sheets' "import wizard".
> **Pivot required?** Yes — **repair with a reversible, auditable plan** instead of silent mutation.

## The problem

Somebody's export has: a UTF-8 BOM, `;` delimiter in half the rows because two systems wrote to it, one row with 13 fields where the header has 12 (an unquoted comma in a company name — "Acme, Inc."), quoted newlines inside `notes`, an encoding that is cp1252 for the accented names, and a footer line saying `Total: 41,204` that isn't a record.

`csvclean` fixes two of those. Excel fixes them destructively. What everyone needs is: *fix it, and tell me exactly what you changed, and let me undo it*.

## Design: plan → apply → report

```bash
csvrepair inspect broken.csv            # diagnosis only, no writes
csvrepair repair broken.csv -o fixed.csv --report changes.json
csvrepair repair broken.csv -o fixed.csv --policy 'extra_fields=merge_last,encoding=cp1252,delimiter=auto'
csvrepair verify fixed.csv --rows 41204  # did we keep every row?
```

`inspect` output is a diagnosis, not a dump:

```
broken.csv  8.4 MB  41,209 physical lines
ENCODING  cp1252 (confidence 0.98)  ·  BOM: none  ·  line endings: mixed CRLF/LF (1,204 / 40,005)
DIALECT   csv, delimiter "," (stable on 41,002 lines; 207 lines parse with ";") ← per-row fallback proposed
PROBLEMS
  1,204 rows  trailing CR inside quoted field (would end up in the last column)
    207 rows  wrong delimiter (10 fields expected, 1 found with ",")
     17 rows  too many fields (13 vs 12) — likely unquoted comma in "company"
      2 rows  too few fields (11 vs 12)
      1 row   footer, not a record: "Total: 41,204"
      0 rows  unterminated quote
```

## Repair policy engine

Every repair is a named policy with a default, and the report references it:

| Problem | Default policy | Alternatives |
|---|---|---|
| ragged row, too many fields | `merge_last` (join the excess into the last column) — **only** when the last column is `string` and the excess count ≤ 3 | `drop`, `pad_empty`, `split_by_delimiter`, `quarantine` |
| too few fields | `pad_empty` | `drop`, `quarantine` |
| wrong delimiter row | `sniff_per_row` (re-parse the row with the alternate delimiter) | `quarantine` |
| footer/trailing junk | `drop_nonrecord` (row whose field count is 1 and matches `^(total|grand total|sum)\b`) | `keep` |
| mixed encodings | `decode_with_fallback` (whole-file decode, then per-line retry) | `replace_errors` |
| BOM | `strip` | `keep` |
| quote inside unquoted field | `wrap_field` (re-quote the field) | `escape` |
| duplicate header | `drop_duplicate` | `keep` |

`quarantine` writes offending rows to `broken.quarantine.csv` **verbatim**, with a line number — never silently lose a row. This is the single most important default: destroying data while "repairing" it is unforgivable.

Every changed row in the report:

```json
{"line": 1842, "policy": "merge_last", "before": ["Acme", "Inc.", "…"],
 "after": ["Acme, Inc.", "…"], "reason": "13 fields, header has 12, last column is string"}
```

## Implementation

- Decode raw bytes once, keeping the original line terminators so an unmodified file round-trips byte-identically (`--in-place` on a clean file must be a no-op — test this).
- Prefer a **lenient parser** over `csv.reader`: `csv.reader` raises or silently merges on bad quotes. Write a small state machine (quote state, escaping, delimiter) — ~150 lines — that yields `(fields, terminated_ok)`. Use `csv.reader` in `strict=False` as a cross-check.
- `charset-normalizer` for encoding (better than `chardet`, actively maintained); `--encoding` to override, `errors="strict"` then per-line fallback.
- Delimiter detection: `csv.Sniffer` first, then own score = variance of field counts per line for each candidate of `, ; \t |`.
- Streaming: never load a 2 GB file; write output as you go, accumulating only counts and the first N examples per problem class.

## Tests

Handcrafted byte-level fixtures for each problem, plus a **round-trip property test**: for a valid CSV, `repair` output must be byte-identical. Fuzz with `hypothesis`: random fields containing delimiters, quotes, newlines, BOMs must survive repair unchanged. Also: a file with only a header, an empty file, a 10 MB single-column file, and a file with embedded NUL bytes (which many parsers mishandle).

## Pitfalls

- Never "fix" numbers or dates; this tool is about *structure* only.
- Excel's CSV is cp1252 with `;` in European locales — detect both, never assume comma/UTF-8.
- Writing the output in text mode will re-translate newlines on some platforms: open with `newline=""`.
- If the output path equals the input path, require `--in-place --yes` and write via temp+replace.
- The report must be generated even when `--quiet`; it's the product.

## Definition of done

All 41,209 lines of a nasty export accounted for (`kept + repaired + quarantined = total`, asserted), output loads cleanly in pandas/DuckDB, and `changes.json` explains every single modification.
