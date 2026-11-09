# 68 — `ledger-import` (bank CSVs → plain-text accounting)

> **Difficulty 5/10** · **Effort ~5 days** · **Tier: hard-ish**
> **Prior art: ❌ solved by the accounting tools themselves** — `beancount` 3.2.3 (has `beangulp`/`beancount.ingest` with exactly this: CSV importers, rule-based categorisation, dedupe against existing entries), `hledger` (`hledger-import` with rules files + `--dry-run`), `ledger` + `ledger-autosync`, `piecash` (GnuCash), `plaintextaccounting` community importers, `csv2beancount`, `firefly-iii` (web).
> **Merged from:** `ledger-import` (bank CSV → ledger with TOML rules).
> **Pivot required?** Yes — and the honest pivot is small: **overlap reconciliation between multiple bank exports**.

## What already exists (precisely)

`beangulp` (the modern Beancount importer framework) gives you: a directory of importer classes, `beangulp extract`/`identify`/`archive`, per-institution CSV column mapping, `narration`/`payee` extraction, and rule-based accounts via `rules.py` with regex. `hledger import` does the same with a `.rules` file and dedupes against your journal automatically.

So "convert bank CSV to ledger format with saved regex categories" is a **solved problem with a mature implementation**, in Python, maintained by people who do plain-text accounting as a hobby. Writing it again mostly produces a less-tested `beangulp`.

## The genuinely unsolved slice

People have **multiple sources for the same money**: two bank accounts, a credit card that pays from one of them, a PayPal/Wise export, and a broker statement. Reconciling them is manual:

```bash
ledger-import scan ~/statements/            # identify each CSV's bank + account by fingerprint
ledger-import import ~/statements/*.csv --format beancount --out main.beancount
ledger-import reconcile --since 2026-01-01  # find duplicates across sources
```

`reconcile` finds:

```
TRANSFERS (7)  matched across accounts by amount + date ±2d
  -42.10  2026-03-04  chk-1234  "SQ *COFFEE"   ↔  +42.10  visa-9999  "SQ *COFFEE"
DUPLICATES (3) same tx appearing twice in one export (statement overlap)
  -120.00 2026-02-11  "AMZN Mktp"   lines 88 and 331 of jan-feb.csv
UNMATCHED (14)  card tx with no corresponding payment row  → likely a statement you're missing
```

Plus a **bank fingerprint database**: a small set of heuristics (header names, column count, date format, debit/credit convention, currency column) that maps a CSV to an institution and an account, so a new export needs no configuration. That knowledge is genuinely scattered across blog posts today.

## Design

Do not write a ledger engine. Emit **beancount** (or `hledger` journal) text:

```
2026-03-04 * SQ *COFFEE | Card purchase
  Expenses:Food:Coffee            42.10 CAD
  Liabilities:Visa:9999          -42.10 CAD
```

Use `beancount`'s own loader in tests to validate that the emitted file parses and balances (`beancount.loader.load_file` → assert no errors). That gives you correctness for free and keeps you honest.

Pipeline: fingerprint → parse (column map, date format, sign convention, amount vs debit/credit columns, encoding) → categorise (regex rules in TOML, learned from previous months' *already-categorised* entries if available: `--learn main.beancount`) → dedupe within export → reconcile across exports → emit with `!` flags for anything uncertain and a `meta` line pointing at the source file+line so a human can audit.

## CLI

```bash
ledger-import scan PATH
ledger-import import FILE... --account Liabilities:Visa:9999 --out x.beancount [--rules rules.toml]
ledger-import reconcile --journal main.beancount --format table|json
ledger-import learn --journal main.beancount --from PATH    # derive rules from prior categorisation
```

## Tests

Fixture CSVs from 6 institutions (hand-made, with the real quirks: BOM, `-` vs parentheses negatives, separate debit/credit columns, `DD/MM/YYYY`, a footer summary row, a currency column, embedded commas). Assert: fingerprint identification, correct sign handling (the classic disaster — an expense imported as income), balance validation via `beancount.loader`, dedupe on statement overlap, transfer matching within the date window, and that re-importing the same file is idempotent.

## Pitfalls

- Sign conventions: always validate the total against the statement's closing balance when the CSV provides one — a silent sign flip corrupts years of accounting.
- Never overwrite an existing journal: append to a new `YYYY-MM.beancount` file and print the `include` line the user must add.
- Dates: some banks use statement date, some transaction date — record which in metadata.
- Multi-currency: do not convert. Emit both amounts and let the ledger represent it.
- Personal finance data is sensitive: no network, no telemetry, and no "helpful" cloud categorisation.

## Definition of done

Ten real monthly statements import into Beancount with correct signs and balanced output, `reconcile` finds real cross-account transfers and one duplicated statement overlap, and re-running the import produces no duplicates.
