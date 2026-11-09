# 60 — `entrypoint-finder` ("which file should I open first?")

> **Difficulty 5/10** · **Effort ~5 days** · **Tier: hard-ish**
> **Prior art: ❌ crowded** — PyPI `codebase-navigator` 0.1.0 (2026-08, *"Fast Git-aware ctags indexing, live watchers, and LanceDB semantic search"*), `ctags`/`universal-ctags` + `fzf`, `ripgrep`, `symbex` (extract symbols for LLM context), `sourcegraph`/`zoekt` (code search), `tree-sitter` (0.26.1), editor tooling (Telescope, `oil.nvim`), `aider`'s repo map, `pydeps`/`grimp` (file 49).
> **Pivot required?** Absolutely — "semantic search over a repo" is a crowded space with VC-backed tools. Only **entry-point inference** is unoccupied.

## The problem

`git clone` someone's 40k-line Django/Click/FastAPI project. You need to answer, in order: where does execution start, which 8 files hold 80 % of the behaviour, which files are boilerplate, and where do I add my change? `rg` answers questions you already know how to ask. Semantic search needs an index, an embedding model, and a query. Neither answers *"open these five files"*.

## The pivot: rank by structural importance, not by similarity

A short, explainable report generated in <2 s with no index, no embeddings, no daemon:

```
$ entrypoint-finder .
PROJECT  shop-api  (Python 3.12, 412 files, 38k LOC, FastAPI + Click)

START HERE
  src/shop/__main__.py        ← console_script "shop" (pyproject) → app.main:cli
  src/shop/app.py             ← FastAPI() instance, 14 routes; ASGI entry
  src/shop/config.py          ← Settings(), 41 env reads; read before anything else
CORE (high fan-in × churn)
  src/shop/core/models.py     ← imported by 41 modules
  src/shop/api/deps.py        ← imported by 28 modules
READ NEXT FOR YOUR CHANGE ("billing" matched 12 files)
  src/shop/billing/invoice.py ← domain logic
  src/shop/api/billing.py     ← routes → invoice.py
  tests/billing/test_invoice.py ← 41 tests, start here to understand intent
SKIP
  src/shop/_vendor/** (3,120 files) · migrations/ (88, generated) · *.pyi (12)
WHY THIS ORDER  entry points from packaging metadata · fan-in from import graph · churn over 90d
```

## How to compute each signal (all cheap, no ML)

1. **Declared entry points**: `[project.scripts]` / `[project.gui-scripts]` in `pyproject.toml`, `setup.py` `entry_points`, `[tool.poetry.scripts]`, `__main__.py` files, `if __name__ == "__main__"` blocks, `Procfile`/`Dockerfile CMD`/`docker-compose.command`, `[tool.pytest]` testpaths, and `manage.py` for Django. This alone beats every "which file" tool.
2. **Framework detection** (cheap, high-value): FastAPI/Flask/Django/Click/Typer/Airflow DAGs. Detect by import + decorator pattern (`@app.get`, `@click.command`, `app = FastAPI(`), then list the *files containing route/handler definitions*. That's the map a newcomer wants.
3. **Fan-in** from the import graph (reuse `grimp` or the approach in file 49): modules imported by many others are core; modules importing many others are coordinators.
4. **Churn × fan-in** from `git log --since=90d --name-only` — files that change often *and* everything depends on are where bugs live.
5. **Tests as documentation**: for a query `billing`, prefer `tests/billing/test_*.py` early — tests are the most readable specification of intent, and no navigator surfaces them first.
6. **Skip lists** that shrink the repo before ranking: `_vendor`, `migrations`, `*.min.js`, generated protos, `.venv`, `node_modules`, `*.pyi`, and any directory > 5,000 files.

## CLI

```bash
entrypoint-finder .                        # the report above
entrypoint-finder . --query billing        # focus a subsystem
entrypoint-finder . --json                 # for editor plugins
entrypoint-finder . --open                 # print (or --exec $EDITOR) the top 5 paths
entrypoint-finder . --why src/shop/app.py  # explain a file's rank
```

`--why` matters: a ranking tool that can't justify itself gets ignored.

## Implementation

```
entrypoint_finder/
  discover.py   # packaging metadata, __main__, framework detection
  graph.py      # imports (grimp optional; ast fallback), fan-in/fan-out
  churn.py      # git log --name-only --since, cached by HEAD
  rank.py       # weighted score with per-signal contributions (explainable)
  render.py     # report, json
```

No network, no index files, no daemon. Cache in `$XDG_CACHE_HOME/entrypoint-finder/<repo-hash>/` keyed by `HEAD` + mtime so repeat runs are ~200 ms.

## Tests

Fixture repos: a Click app with `[project.scripts]`, a FastAPI app with routers in subpackages, a Django app, a library with no entry points (must say so honestly, and fall back to fan-in ranking), a repo with a `_vendor` dir (must be excluded), and a shallow clone with no git history (churn → 0, ranking still works, output notes "no history"). Assert the top-3 for each fixture — these are the regression tests that matter.

## Pitfalls

- Rankings are opinions dressed as data: always show the signal contributions, and never call the output "the" answer.
- Monorepos have multiple projects — detect all pyprojects and report per project with `--project`.
- `.pyi` stubs and `if TYPE_CHECKING` imports distort fan-in; exclude stubs from the graph.
- Dynamic frameworks (Django app registry, plugin entry points) hide edges: parse `INSTALLED_APPS` and `[project.entry-points]` explicitly.
- Startup cost is the product: no `import` of the target project (side effects, missing deps) — static analysis only.

## Definition of done

Dropping the tool into an unfamiliar 40k-LOC repo produces a 5-file reading list that a maintainer agrees with, in <2 s, with no index to maintain. If you can't beat that, use `rg` + the README.
