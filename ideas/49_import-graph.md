# 49 — `import-graph` (the internal dependency map of a Python codebase)

> **Difficulty 4/10** · **Effort ~3 days (as a gap tool)** · **Tier: medium**
> **Prior art: ❌ mostly solved** — `pydeps` (3.0.9, module dependency graphs with DOT/SVG output), `grimp` (3.19, fast import graph + `find_illegal_dependencies`, used by `import-linter`), `import-linter` (contracts for layers/independence), `tach` (modular boundaries, enforcement), `pycycle` (cycles only), `snakefood`, `code2flow`.
> **Pivot required?** Yes — visualisation and cycle detection are taken. **Debt *prioritisation* by fan-in/fan-out × churn is not.**

## What already exists, precisely

- `pydeps mypkg --max-bacon 2 -T png` draws a graph (and `--show-cycles`).
- `grimp build` + `find_illegal_dependencies` gives layer violations with a config.
- `import-linter` turns those into CI contracts; `tach` enforces module boundaries with a `tach.toml`.
- `pycycle` lists cycles.

So: do not build a graph renderer. Build the report a tech lead needs before a refactor:

```
$ import-graph report src/shop --since 12mo
GOD MODULES (fan-in × fan-out)
  src/shop/core/models.py       fan-in 41  fan-out 27  churn 88 commits/12mo  ⚠⚠
  src/shop/api/base.py          fan-in 33  fan-out 19  churn 41
CYCLES (3, all involving core)
  core.models → api.serializers → core.models
  billing.invoice → core.models → billing.invoice
LAYER VIOLATIONS (config: layers = api > services > core)
  services/orders.py imports api/handlers.py   (upward, 4 sites)
DEAD MODULES (imported by nothing, not a script)
  src/shop/legacy/import_v1.py, src/shop/utils/old_retry.py
REFACTOR TARGETS
  split core/models.py: 6 clusters, largest 480 lines (billing, orders, auth)
```

The cluster suggestion is a small community detection (label propagation or greedy modularity on the undirected import graph, ~60 lines of pure Python) restricted to one file's symbols? No — cluster *modules*: take the subgraph of modules that import `core.models`, cluster by their co-import patterns, and report the natural seams. That's genuinely beyond `pydeps`.

## Implementation

- **Graph**: `grimp` (fast, Rust-backed, handles namespace packages and relative imports) as an optional dependency, with an `ast`-based fallback (imports only, no `__init__` re-export resolution). Do not build your own resolver; relative imports and `from . import x` will eat a week.
- **Metrics**: fan-in/fan-out over the internal graph (exclude stdlib/third-party), instability `I = Ce/(Ca+Ce)`, and a "god module" score = `instability_low × fan-in`. Add **churn** from `git log --since --name-only` (count commits touching the file) — the multiplication is what makes it actionable.
- **Cycles**: Tarjan's SCC over the module graph, then report the *shortest* cycle through each edge (BFS) so the report shows a 2-hop loop, not a 30-module blob.
- **Layers**: config `layers = api > services > core` (or a `pyproject.toml` table), violations = edge from a lower layer to a higher one; list import sites with file:line via a second AST pass.
- **Dead modules**: in-degree 0, not an entry point (`[project.scripts]`, `__main__`, `conftest.py`, `migrations`, `setup.py`), and not referenced by string (django settings, plugin registries — grep for the module string before calling it dead).
- **Output**: `--format mermaid|dot|json|markdown`; mermaid for a README, dot for graphviz, json for `import-linter`-style CI gates.

## Tests

Fixture packages: a 3-cycle, a diamond, a `from . import x` relative chain, an `if TYPE_CHECKING` import (must not count as a runtime edge — offer `--include-type-checking`), a lazy import inside a function (count separately: "runtime deferred"), a namespace package, and a module imported only via `importlib.import_module("pkg.x")` (string → detect and mark). Assert Tarjan output on a known graph and the dead-module false-positive guard.

## Pitfalls

- `__init__.py` re-exports invert the intuitive direction — document whether an edge means "imports from" or "exposed by".
- Conditional imports (`try: import ujson except ImportError`) are real edges; don't drop them.
- Don't draw a 400-node graph; `--max-nodes` with a clear "graph truncated" warning.
- Cycle reporting on a monorepo must be scoped to a package root, or you'll report venv/site-packages cycles.
- Churn requires git history; a shallow clone has none — degrade and say so.

## Definition of done

`report` on a 300-module package names the 3 god modules with churn evidence and produces a Mermaid diagram that renders on GitHub, in <5 s. Otherwise use `pydeps`/`import-linter`.
