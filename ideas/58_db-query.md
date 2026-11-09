# 58 — `db-query` (named SQL shortcuts, pretty results)

> **Difficulty 5/10** · **Effort ~5 days** · **Tier: hard-ish**
> **Prior art: ⚠️ crowded on the client, thin on the shortcut** — `harlequin` (TUI, excellent), `usql` (multi-DB shell), `sqlite-utils` (`--csv`, `:memory:` queries), `duckdb` CLI, `q` (Python, "run SQL on CSV/TSV"), `csvq`, `dsq`, `pgcli`/`mycli`, `dbt` (models, not shortcuts), `sqlfluff` (linting), `jq`-style `sqlite3 -json`.
> **Merged from:** "interactive SQL shortcut runner", "CLI SQL-to-JSON converter", `csvq` (SQL over files), `db-query` (the `duckdb`-backed analysis idea).
> **Pivot required?** Yes — saved, parameterised, versioned queries; not another client.

## The problem

Analysts and devs re-type the same 30-line query weekly. Shell history is the "shortcut system" today: unreadable, unversioned, no parameters. Meanwhile the querying tools are all *clients* (you type SQL into them), not *runners* (you name a query and get a table).

## Design

Queries live in a directory, one file each, in version control:

```sql
-- queries/monthly_churn.sql
-- name: monthly-churn
-- desc: Monthly churn by plan
-- param: start_date date = date_trunc('month', current_date - interval '1 month')
-- param: plan string = '%'
-- col: month | label: Month
-- col: customers | fmt: integer
select date_trunc('month', cancelled_at) as month,
       count(distinct customer_id) as customers
from cancellations
where cancelled_at >= :start_date and plan like :plan
group by 1 order by 1;
```

```bash
db-query monthly-churn                                   # uses defaults
db-query monthly-churn start_date=2026-01-01 plan=pro
db-query list                                            # names, descriptions, params
db-query run queries/churn.sql --set plan=pro --format table|json|csv|markdown
db-query explain monthly-churn                           # rendered SQL + param values + engine plan
db-query init                                            # scaffold db-query.toml + a sample query
```

Output: a real table in the terminal (aligned, right-justified numerics, thousands separators, NULL as a dim `∅`, humanised durations), `--format json` for piping, and `--out file.csv`. That alone is 80 % of the daily value.

## Engine strategy (choose deliberately)

Two modes, both worth having:

1. **Files**: `duckdb` in-process (`duckdb.connect()` then `read_csv_auto`/`read_parquet`) so `db-query 'select * from read_csv_auto('sales.csv') where amount > 100'` works with no server. DuckDB does the heavy lifting; this is the `csvq`/`q` niche done with a better formatter and saved queries.
2. **Servers**: `sqlalchemy` URLs (`postgresql+psycopg://…`, `mysql+pymysql://…`, `sqlite:///…`) so the same runner works against a real DB. Use SQLAlchemy only as the connection layer and pass the query through (`text()`), or use the driver directly to avoid SQLAlchemy's `:name` paramstyle conflicts — the `--set` values must be bound parameters, never string interpolation (SQL injection in a personal tool is still injection, and worse: a typo'd `plan=pro'; drop …` should not execute).

**Parameter binding detail**: named parameters with a per-engine syntax (`:name` for SQLite/Postgres via SQLAlchemy `text`; `%s` for MySQL) is a rabbit hole. Normalise on `:name` in the file and translate per dialect with `sqlglot` (30.30.0) — it's the right tool and handles the quoting too. Always bind, never interpolate.

## Safety and ergonomics

- **Read-only by default**: refuse statements starting with `INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|CREATE` unless `--write` is passed (detect with `sqlglot.parse` and the AST node type, not a regex). Analysts run this against production replicas; a mis-typed `drop` must be blocked.
- **Row cap** `--limit 1000` appended when the query has no explicit `LIMIT` (parse with `sqlglot`), with a clear "showing 1,000 of N (use --limit 0)" footer. Count separately so the number is honest.
- **Timeouts** per engine (statement_timeout on Postgres, `set progress_bar` / interrupt for DuckDB).
- **Secrets**: connection strings from `db-query.toml` referencing env vars (`url = "${DATABASE_URL}"`), never inline; `--show-url` masks passwords.
- **Deterministic output**: column order from the query, timestamps in ISO-8601 UTC unless `--tz`.

## Build

```
db_query/
  registry.py  # discover .sql files, parse the -- metadata header into a QuerySpec
  params.py    # defaults, type coercion (date/decimal/bool), validation with clear errors
  engine.py    # duckdb + sqlalchemy adapters: connect(url), run(sql, params) -> (cols, rows, meta)
  render.py    # table/json/csv/markdown; rich Table with numeric alignment, NULL styling
  guard.py     # sqlglot parse -> readonly check, limit injection
  cli.py
```

Deps: `sqlglot` (required), `duckdb` (optional extra `[files]`), `sqlalchemy` + drivers (optional extra `[pg]`), `rich` (optional). Keep the core importable without a DB driver installed — a CLI that fails to start because `psycopg` is missing is a bad CLI.

## Tests

- Engine tests against SQLite in `tmp_path` and DuckDB over fixture CSVs (no external servers); a `@pytest.mark.pg` suite for Postgres, skipped by default, run in CI with a service container.
- Guard tests: `WITH x AS (DELETE ... RETURNING *) SELECT * FROM x` must be blocked (this is the bypass every regex-based guard misses — `sqlglot`'s AST catches it); a `SELECT` with a `LIMIT` must not get a second one; a comment containing "DROP" must not trip the guard.
- Render tests: numeric alignment, NULL rendering, a 200-column result, unicode widths, and `--format json` with `Decimal`/`datetime` serialisation.
- Param tests: missing required param, wrong type, `:name` inside a string literal (must not be substituted — `sqlglot` parsing distinguishes it).

## Pitfalls

- Don't build a TUI. `harlequin` exists and is better than anything a semester produces.
- DuckDB and Postgres differ on date truncation, `interval` syntax, and case folding — `--dialect` explicit, and never silently "fix" the user's SQL beyond parameter syntax.
- `sqlglot` will fail on vendor-specific SQL (BigQuery `UNNEST`, MySQL hints): on parse failure, warn and skip the guard rather than refuse to run (with `--force` recorded).
- Row streaming: `fetchall()` on a 10 M row query will OOM — use a server-side cursor and stop at the limit + 1.
- Keep query files diffable: one statement per file, no trailing semicolon rewriting, and `init` should generate a commented example.

## Definition of done

A team commits 20 query files, `db-query <name>` renders a readable table against both a CSV set and Postgres, parameters bind safely, and a destructive statement is refused without `--write`.
