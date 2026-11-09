# 54 — `pytest-fixture-graph` (the hidden structure of your fixtures)

> **Difficulty 5/10** · **Effort ~5 days** · **Tier: hard-ish**
> **Prior art: ✅ real gap** — `pytest --fixtures` (a list, no graph), `pytest --setup-plan` (linear plan per test), `vulture` (unused functions, no pytest semantics), `pytest-dependency`, IDE plugins. No tool renders the fixture dependency graph or audits scope.
> **Pivot required?** No. This is one of the best remaining ideas in the list — precise, testable, and obviously useful to anyone with 200+ tests.

## The problem

In a mature pytest suite, fixtures are the architecture. They're also invisible: `conftest.py` files layer 3 deep, a session fixture silently depends on a module fixture, and a `function`-scoped fixture rebuilds a 40 MB object 400 times. Nobody can answer: which fixtures are unused, which are duplicated across conftests, which are scoped wrongly, and what's the actual setup cost chain.

## Design

```bash
pytest-fixture-graph --format mermaid > fixture-graph.mmd
pytest-fixture-graph --format dot | dot -Tsvg > graph.svg
pytest-fixture-graph --unused
pytest-fixture-graph --scope-mismatch
pytest-fixture-graph --costs --top 15        # measured setup time per fixture (from a real run)
pytest-fixture-graph --explain tests/test_x.py::test_y
```

Text output that a human reads before touching `conftest.py`:

```
FIXTURES 148 defined across 11 conftest.py files
UNUSED (9)
  conftest.py:88        big_report_fixture       0 tests, 0 fixtures
  tests/api/conftest.py:12  legacy_client        0 tests  (file last changed 2y ago)
DUPLICATED (4)
  `db`  tests/api/conftest.py:12  ≈  tests/web/conftest.py:9   (91% similar)  → move to tests/conftest.py
SCOPE MISMATCH (6)
  `catalog` function-scoped, 14 consumers, reads a static 40 MB CSV → session/module saves ~9.3 s/run
COST CHAIN (measured)
  session `app` 4.1 s
    └ session `db` 3.6 s
       └ module `redis` 1.2 s     ← rebuilt 7× per run (module scope, 7 modules)
DEEPEST CHAIN  app → db → redis → cache_conn (4 levels)
```

## How to get authoritative data

Do **not** parse fixtures with `ast` as the primary source — pytest resolves overrides, `params`, `indirect`, `autouse`, and `request.getfixturevalue`. Collect from pytest itself:

```python
def pytest_collection_finish(session):
    for item in session.items:
        info = item._fixtureinfo                      # FixtureInfo
        for argname, defs in info.name2fixturedefs.items():
            for fd in defs:                           # FixtureDef: func, scope, argnames/params, baseid
                ...
```

That yields edges `fixture -> fixture` (via `fixturedef.argnames`) and `test -> fixture` (via `name2fixturedefs`), plus `scope`, `line_number`, `baseid` (the conftest path) — everything needed. `item._fixtureinfo` is private API; guard with `getattr` and fail loudly with the pytest version when it changes (pin `pytest>=8` in `requires`).

**Unused**: fixture never appears in any `name2fixturedefs` after collection. Two caveats: (1) `autouse=True` fixtures *do* run — count them as used; (2) `request.getfixturevalue("x")` is dynamic — scan test sources for string literals matching fixture names and mark those "possibly used" (never "unused").

**Costs**: run once with `--durations=0`-style instrumentation: wrap every fixture call in `pytest_fixture_setup` (a hook with `tryfirst`) and time `call_fixture_func`; accumulate per fixture `fixturedef` identity (id stable within a run). Report total setup time per fixture and how many times it was instantiated — the "rebuilt 7×" insight falls out.

**Scope advice** (report only, never auto-change): `function`-scoped fixture, ≥2 consumers, no `tmp_path`/`monkeypatch`/mutation in its body, and a measured setup cost ≥ 100 ms → suggest `module`/`session`. Explicitly refuse to advise when the body yields and mutates (state leakage risk), or when the fixture consumes another function-scoped fixture.

**Mermaid**: `graph LR` with subgraphs per conftest file, node labels `name (scope)`, dashed edges for autouse, and a class for "shared across ≥5 tests" (visually flags the god fixtures). Cap at `--max-nodes 150` with a warning.

## Tests

`pytester` suites covering: fixture override in a subdirectory conftest, autouse fixture, parametrised fixture (`params=[...]`), `indirect` parametrisation, a fixture using `request.getfixturevalue`, a yield fixture with teardown, a scope-mismatch candidate and a legitimately function-scoped one (must not be flagged), and a duplicated fixture. Golden Mermaid output on a small graph.

## Pitfalls

- Fixtures defined but *shadowed* by an override: both exist in the graph — mark the shadowed one and its tests' resolution.
- `usefixtures` marker and `pytestmark = pytest.mark.usefixtures(...)`: include those edges or fixtures look unused.
- Don't include third-party plugin fixtures (they're in every graph and add nothing) — filter by `baseid` being inside the repo, with `--include-plugins`.
- Cost measurement changes behaviour (extra wrapping): make it opt-in (`--costs`) and measure overhead in a self-test.
- `pytest-xdist` splits fixtures across workers — refuse `--costs` under `-n` or aggregate with a clear caveat.

## Definition of done

On a 300-test suite the graph renders in Mermaid and GitHub, `--unused` has no false positives, and at least one scope fix saves >20 % of suite setup time when applied.
