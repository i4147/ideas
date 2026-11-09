# 23 — `csv-contract` (catch silent changes in recurring CSV exports)

> **Difficulty 3/10** · **Effort ~3 days** · **Tier: medium**
> **Prior art: ⚠️ partial** — `frictionless`/`tableschema` (validation, but a framework), `csv-diff` (row diff, no learned contract), Great Expectations / Soda (heavy data-quality platforms), `csvkit` (`csvstat`, no expectation memory), `pandera` (DataFrame schemas, needs pandas).
> **Pivot required?** Yes, a narrow one: **learn a contract from one file, check cheaply forever, with zero dependencies.**

## The problem

The bank, the CRM, the supplier portal, and the analytics dashboard all email a CSV every week. One week `Amount` becomes `Amount (CAD)`, or the sign flips (`1,234.50` → `-1234.50`), or `date` changes from `2026-11-09` to `09/11/2026`, or a column becomes 40 % nulls. Your script keeps running and writes garbage into a database. Nobody notices for three weeks.

This is not "validate against a schema I wrote" (nobody writes them for a supplier's export). It's "I have one good file; tell me when the next one differs".

## Design: contract learning + drift classification

```bash
csv-contract init export_2026_10.csv --contract export.contract.json --sample 5000
csv-contract check export_2026_11.csv --contract export.contract.json
csv-contract check exports/*.csv --contract export.contract.json --json --fail-on breaking
```

Learned contract per column:

```json
{"column": "amount", "position": 3,
 "type": "decimal",          // integer|decimal|date|datetime|boolean|string|mixed
 "nullable": false, "null_rate": 0.0,
 "format": {"decimal_sep": ".", "thousands": ",", "sign_position": "leading"},
 "range": {"min": -12000.0, "max": 98000.5},
 "distinct_sample": 0.83,
 "date_format": null,
 "header_seen": "Amount"}
```

`check` classifies each difference and, crucially, prints **what a downstream script will experience**:

```
BREAKING column "amount" renamed to "amount_cad"
BREAKING column "date" format changed 2026-10-03 (ISO) → 03/10/2026 (DMY)
WARNING  column "region" null_rate 0.02 → 0.31
WARNING  row count 4,102 → 3,980 (-3.0%)
INFO     column "notes" max length 120 → 240
INFO     new column "currency" (all "CAD")
```

Severity policy, which is what makes it usable:
- **breaking**: renamed/removed column, type change, date-format change, decimal separator change, sign convention flip, nullability change on a non-null column.
- **warning**: null-rate shift > 10 pp, range violation on > 0.1 % of rows, row-count shift > 20 %, new enum value.
- **info**: new column, wider string length, formatting-only change.

Exit codes `0/1/2` and `--fail-on breaking|warning|never` for CI/cron.

## Implementation notes

**Typing is the hard part.** Infer per column by trying, in order: null → boolean (`true/false/0/1/yes/no`, only if a *consistent* set) → integer (strip thousands sep, handle leading `+`) → decimal (`Decimal`, never float; detect separator by consistency across the file, not by one value) → date (try a fixed ordered list of ~12 formats covering ISO, DMY, MDY, `DD-Mon-YYYY`, ISO-8601 datetime; require 100 % of non-null values to parse with the *same* format, else `mixed`) → string. Store ambiguous cases as `mixed` with the observed format distribution — that's honest and still catches drift.

**Sampling.** `init --sample N` reads at most N rows with `csv.reader`, but format detection (delimiter, quote, encoding, header presence) must inspect the first ~64 KB raw bytes: try `charset-normalizer` for encoding, `csv.Sniffer` for dialect with a hand-rolled fallback (`;` vs `,` vs `\t` decided by per-line field-count stability).

**Dependencies.** Aim for zero required deps; `charset-normalizer` optional. Do not require pandas.

**Contract storage.** One JSON file per export, human-reviewable, committed next to the script. `--merge` to update a contract deliberately after an accepted change (`csv-contract init --update --accept amount_cad`), so the tool can't be "fixed" by everyone silently regenerating the contract weekly — require a diff in review.

## Tests

Synthetic generator producing a base CSV then 20 mutations (one per finding class). Golden assertions on severity. Nasty inputs: BOM, CRLF, quoted newlines, `1.234,56` European decimals, negative in parentheses `(1,234.00)`, leading zeros (must stay strings — zip codes!), dates like `2026-10-13` vs `13/10/2026` that are ambiguous for days ≤ 12, a single-column file, and a 2 GB file (streaming check without loading).

## Pitfalls

- Leading-zero identifiers (`01234`) must never be typed as integers — the classic CSV disaster.
- Never coerce during `check`; only report. A checker that rewrites data will be trusted once and then blamed.
- Locale: `1,234` in one column and `1.234` in another is common; infer per column, not per file.
- Duplicate/blank headers (`"", "amount", "amount"`) — report positionally, not by name.
- Store the *row count* and *file hash* in the report so a re-check is comparable.

## Definition of done

`init` on a real 50k-row export takes <1 s, `check` flags a renamed column and a date-format flip as breaking, and a cron job with `--fail-on breaking` emails you before the bad data lands.
