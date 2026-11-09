# 04 — `env-audit` (reconcile `.env`, `.env.example`, CI, and the code)

> **Difficulty 2/10** · **Effort ~3 days** · **Tier: warm-up**
> **Prior art: ⚠️ partial** — `envcheck` (0.0.9, 2022), `envaudit` (0.1.0, 2026), `python-dotenv`, Rust's `dotenv-linter`, `detect-secrets`.
> **Merged from:** `env-audit`, `envcheck`, `envdiff`, `env-diff`, `env-sync` (file-side only), "Environment Variable Auditor" (×3), "Local secrets drift checker", "Local environment sanity checker" (env half). **This was the single most duplicated idea in the list — 12 entries.**
> **Pivot required?** Yes: everything existing compares *files to files*. The gap is comparing files to *code*.

## The problem

A `.env.example` is a promise the code doesn't keep. Real failure modes:

- code reads `os.environ["STRIPE_WEBHOOK_SECRET"]`, but no `.env.example` entry → new dev gets a `KeyError` 20 minutes in;
- `.env` has 14 keys nobody reads any more → dead config that people keep "just in case";
- `os.getenv("REDIS_URL", "localhost")` has a default, but the docs claim it's required;
- the same key is spelled `DB_HOST` in `.env`, `DATABASE_HOST` in CI, and `db_host` in `docker-compose.yml`;
- someone committed a real `.env` with a live key.

## What already exists

| Tool | Gap |
|---|---|
| `dotenv-linter` (Rust) | syntax/ordering/duplicates; does not read your source |
| `envcheck` (PyPI, 2022) | compares two dotenv files; unmaintained |
| `envaudit` (PyPI, 2026) | "validator and manager" — key-level validation, no AST usage analysis |
| `detect-secrets`, `gitleaks` | entropy/regex secrets, not config completeness |
| `pydantic-settings` | runtime validation only; fails at import time, not in CI |

## The pivot: static usage extraction

Parse the code, don't grep it. Grep gives you ~40 % false positives from tests, docs, and vendored code.

```python
# build a usage table with ast, not regex
class UsageVisitor(ast.NodeVisitor):
    # os.environ["X"]           -> read, required
    # os.environ.get("X", d)    -> read, optional, default=d
    # os.getenv("X")            -> read or write? (only read if not assigned)
    # os.environ["X"] = ...     -> write
    # settings.py: Field(env="X")/BaseSettings fields -> read, optional-by-default
    # subprocess env={...}      -> write
```

Then resolve against **three** inventories: `.env.example` (the contract), `.env` (the local truth), and CI config (`.github/workflows/*.yml`, `docker-compose*.yml`, `Dockerfile ENV`, `k8s/*.yaml`, `fly.toml`).

Findings, each with an exit-code class:

| Code | Finding | Default severity |
|---|---|---|
| E001 | read by code, absent from `.env.example` | error |
| E002 | in `.env.example`, never read anywhere | warning |
| E003 | read with no default and missing from the active `.env` | error |
| E004 | present in `.env` but not in `.env.example` | info (likely local-only) |
| E005 | in CI but not in `.env.example` (or vice versa) | warning |
| E006 | value looks like a live secret **and** the file is git-tracked | error |
| E007 | same concept, different spelling across files (fuzzy: `DB_HOST`/`DATABASE_HOST`) | warning |
| E008 | default in code contradicts documented default | info |

Committed-secret detection is deliberately narrow and non-AI: git-tracked `.env`, high-entropy values ≥ 20 chars, known prefixes (`sk_live_`, `ghp_`, `AKIA`, `-----BEGIN`), plus the repo's own `.gitignore` check.

## CLI surface

```bash
env-audit check                       # auto-discovers everything, uses pyproject config
env-audit check --example .env.example --env .env --strict
env-audit scan --source src/ --redact  # usage table from code alone
env-audit diff .env.staging .env.production --keys-only
env-audit report --format markdown > env-report.md
env-audit init                        # propose a .env.example from code + current .env
```

`init` is the killer feature: it writes a `.env.example` with every read key, its default (if any), and a `# used in src/db.py:41` comment. That turns a chore into one command.

## How to build it

```
env_audit/
  dotenv.py     # tolerant parser: export prefixes, quotes, multi-line, ${VAR} interpolation
  code.py       # ast walker + settings-class detection (pydantic, django-environ, python-decouple)
  ci.py         # yaml loaders for workflows/compose/k8s; Dockerfile ENV/ARG scan
  reconcile.py  # set algebra -> Finding list
  secrets.py    # entropy + prefix checks, git tracking via `git ls-files --error-unmatch`
  cli.py, report.py
```

Config in `pyproject.toml`:

```toml
[tool.env-audit]
example = ".env.example"
required = ["DATABASE_URL"]
ignore = ["CI", "PATH", "HOME", "PYTHONPATH"]
severity = {E002 = "info", E007 = "error"}
```

Ignore `PATH`, `HOME`, `PWD`, `SHELL`, `VIRTUAL_ENV`, `LANG`, `TERM`, `TMPDIR`, and anything prefixed `PYTEST_`. Without a solid ignore-list this tool cries wolf and gets uninstalled.

## Tests

Fixtures are tiny projects (2–5 files) — one per finding code — asserted with `pytest` and `tmp_path`. Critical cases: variable read through an alias (`e = os.environ; e["X"]`), `os.environ.setdefault`, f-string key (`os.environ[f"{PREFIX}_TOKEN"]` — must be reported as *dynamic*, not guessed), and a decoded `.env` with CRLF line endings.

## Pitfalls

- Never print values by default. `--show-values` requires `--yes`.
- Dynamic keys can't be resolved; list them separately as "unverifiable" so the report stays trustworthy.
- False positives kill adoption: keep the ignore-config prominent and make every finding suppressible inline (`# env-audit: ignore E002`).
- Do not position it as a secrets manager or sync tool (that's `env-sync`; see file 44).
- AST across Python 3.9–3.14: use `ast.parse(feature_version=...)`, and don't crash on syntax errors — warn per file.

## Definition of done

On a real Django/FastAPI repo, `check` runs in <1 s, finds a genuinely missing required key, `init` generates an example file that a fresh clone can boot from, and CI fails only on E001/E003/E006.
