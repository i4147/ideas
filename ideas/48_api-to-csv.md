# 48 — `api-to-csv` (stream a nested API array into CSV/Parquet)

> **Difficulty 4/10** · **Effort ~4 days** · **Tier: medium**
> **Prior art: ⚠️ partial** — `jq` + `csvkit` (`… | jq -r '.items[]' | in2csv -f json`), `miller` (`mlr --json --ocsv`), `DuckDB` (`read_json_auto`, `read_csv`), `sqlite-utils insert --nl`, `Steampipe`, `Airbyte`/Meltano (heavy), `xsv`.
> **Pivot required?** Yes — pagination, JSONPath, and schema-stable output are what the one-liners can't do.

## The problem

An analyst has an API with a token, a nested response (`data.results[*].attributes`), and 400 pages. `curl | jq | in2csv` works for page 1 and falls apart on: pagination (`Link` headers / `next_cursor`), a nested array inside an object, inconsistent fields across rows (CSV needs a stable header), and rate limits.

## Design

```bash
api-to-csv https://api.example.com/v1/orders \
  --path 'data.results[*]' --flatten '.' \
  --paginate link-header --max-pages 500 \
  --header "Authorization: Bearer $TOKEN" \
  --out orders.csv

api-to-csv … --infer-from 3     # sample 3 pages, then fix the schema before writing
api-to-csv … --out orders.parquet --compression zstd
```

Pipeline:

1. **Fetch**: `httpx` async, one page at a time (ordered), with `--rate 5/s`, `Retry-After` handling, and a `--max-bytes` guard.
2. **Paginate**: strategies `none | page-param (page=) | offset-param | cursor-field (JSONPath to next cursor) | link-header (parse RFC 8288 `rel="next")` | next-url-field`. All declarative in the config, because every API invents its own.
3. **Select**: JSONPath via `jsonpath-ng` (or a hand-rolled subset) to the array of records.
4. **Flatten**: nested objects → `a.b.c` columns (`--flatten sep=.`); arrays → either a JSON string cell (default) or `--explode` into rows; nulls → empty; booleans → `true/false`; timestamps preserved as strings (never silently localise).
5. **Schema stability**: CSV needs the header before the first row is written. Two-pass is impossible for a stream, so: `--infer-from N` (default 2) pages first, union the keys in discovery order, write the header, then stream; *new keys appearing later* are appended to a `.extra-columns` note and either dropped (`--on-new-field drop`) or written to a sidecar JSONL (`--on-new-field sidecar`). Silently dropping data is the failure mode to design around.
6. **Write**: `csv` (with `quoting=QUOTE_MINIMAL`, `newline=""`), Parquet via `pyarrow` only when asked (optional extra).

## Config file

`--config orders.yaml` with the same fields plus `token_env: API_TOKEN` (never a token in the file), so a daily pull is a 3-line crontab entry.

## Tests

`respx` fixtures with: 3 pages of `Link` headers, cursor pagination, a page where one record has an extra key, a record where a field is a nested array of objects, 429 with `Retry-After: 2`, a page with `null` timestamps, and an empty final page. Assert CSV has a stable header from page 1, `--explode` yields the right row count, rate limiting is respected (fake clock), and Parquet output round-trips through `pyarrow` with correct types.

## Pitfalls

- Excel mangles CSV: warn when a value looks like a long number (account IDs get scientific notation) and offer `--excel-safe` (quote as text, UTF-8 BOM option).
- Timezones: keep ISO-8601 strings; converting to naive local time silently corrupts analysis.
- Nested arrays of objects in one cell can be huge (100 KB per row); cap with `--max-cell-bytes`.
- Don't buffer the whole response for huge pages: stream the body, but you must parse JSON fully per page — cap page size and refuse pages over `--max-page-bytes`.
- Secrets must never land on the command line in shell history (see file 22): prefer `--token-env`.

## Definition of done

A 400-page, 120k-row API pull produces a CSV that loads into DuckDB/pandas with the expected dtypes, no dropped fields, and a one-line summary (pages, rows, retries, elapsed) at the end.
