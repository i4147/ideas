# 25 — `fixture-slim` (find bloated, duplicated, and unused test fixtures)

> **Difficulty 3/10** · **Effort ~4 days** · **Tier: medium**
> **Prior art: ✅ near-gap** — `vulture` finds unused *code* (including fixture functions, but with no scope understanding), `pytest --fixtures` lists fixtures, `pytest --collect-only` gives tests. Nothing computes fixture cost, duplication, or safe replacements.
> **Pivot required?** No, but scope must be tight: pytest only, report-only by default.

## The problem

A test suite that takes 90 s has three causes, and fixtures are two of them:

1. **Size**: `tests/fixtures/catalog.csv` is 40 MB and is read by two tests; a 12 MB PNG is committed for a snapshot test that never compares pixels.
2. **Duplication**: six conftest.py files each define a near-identical `db` fixture, so the suite opens six engines' worth of setup for the same thing.
3. **Unused**: `big_report_fixture` was written in 2023, the test that used it was deleted, and pytest still builds it on every run because it's module-scoped and something else pulls it in transitively. (Actually unused fixtures are *never* instantiated by pytest — but they still cost review time, import time, and confusion; and unused fixture *data files* cost disk, clone time and wheel size.)

Plus a subtler cost: a `function`-scoped fixture that rebuilds a 20 MB object 400 times. Nothing tells you it could be `session`-scoped.

## What it must produce

```
$ fixture-slim tests/ --data-dir tests/fixtures

DATA FILES  41 files, 118.4 MB
  40.1 MB  catalog.csv        used by tests/test_catalog.py::test_import (1 test)
  12.0 MB  sample.png         used by tests/test_media.py::test_upload
   8.2 MB  dump.sqlite       UNUSED  (no test opens it)
  3.1 MB  expected.json      duplicate of expected_copy.json (sha256 match)

FIXTURES  64 defined, 9 unused, 4 duplicated, 6 suspect-scope
  unused      conftest.py:88  big_report_fixture
  duplicate   tests/api/conftest.py:12 `db`  ≈  tests/web/conftest.py:9 `db`  (91% AST-similar)
  scope       tests/test_orders.py:22 `catalog` is function-scoped but reads a static 40 MB CSV → session
  slow-chain  session `app` → session `db` → module `redis` → function `cache_conn`  (rebuilds per test)

SUGGESTIONS (apply with --apply, all reversible)
  rm tests/fixtures/dump.sqlite            (unused, 8.2 MB)
  ln -s? no → replace catalog.csv with a 200-row head + `pytest.mark.slow` keeping the full file
  read catalog once: session-scoped cached reader in conftest
```

## How to do it correctly

**Data file usage detection** cannot be a grep for the filename — paths are often built: `Path(__file__).parent / "fixtures" / f"{case}.csv"`. Approach: collect all string literals in test files (and conftests) via `ast`, then (a) exact matches, (b) directory matches (`FIXTURE_DIR / "x"` where `FIXTURE_DIR` is resolvable by simple constant folding), (c) **glob/dynamic detection**: if a test contains `glob(`, `iterdir()`, `listdir(`, or an f-string over the fixture dir, mark every file in that directory as "possibly used" — never recommend deleting those. Run the *collected* suite with `--collect-only` to know which tests actually exist (deleted tests ⇒ orphaned files).

**Fixture graph from pytest itself**, not from parsing: use a plugin that reads `pytest.FixtureDef` objects at `pytest_collection_finish` (`item._fixtureinfo.name2fixturedefs`), giving you: name, defining file, line, scope, `argnames` (dependencies), and which tests request it directly/transitively. That's authoritative and handles parametrisation, `indirect=True`, and dynamic `request.getfixturevalue` (which makes a fixture "possibly used" — flag it, don't call it unused).

**Duplication** = normalised AST hash of the fixture body (strip docstrings, normalise names/literals? no — keep literals, they matter) + Jaccard similarity of import sets. Report ≥85 % similarity as "likely duplicate", with a `--threshold`.

**Scope advice** heuristics: a `function`-scoped fixture with no `tmp_path`/mutation and ≥2 consumers, where the body contains no `yield`-based teardown that mutates, is a candidate for `module`/`session`. Never auto-change scope — report only; a wrong scope change causes cross-test contamination, the worst kind of test bug.

## CLI

```bash
fixture-slim tests/ [--data-dir DIR] [--json] [--min-size 1MB]
fixture-slim tests/ --unused-only
fixture-slim tests/ --apply --yes        # only deletions of provably-unused data files → send2trash
```

Deletion goes to the trash (`send2trash`), not `rm`, and prints the exact `git` command to undo the *commit* too.

## Tests

Fixture test-suite(s) inside `tests/fixtures/projects/`: a mini project with a known unused CSV, a duplicated `db` fixture, a dynamically-globbed data dir (must be reported as possibly-used), a `request.getfixturevalue` fixture, a parametrised fixture, and an `importorskip`-guarded module. Assert exact findings.

## Pitfalls

- Never modify test code automatically — the failure mode is silently skipped tests.
- `conftest.py` fixtures can be shadowed by same-name fixtures in a subdirectory: report the resolution, not the name.
- Fixture files may be used by non-pytest tooling (docs, scripts, benchmarks): scan the whole repo, not just `tests/`.
- Size accounting: git stores compressed; report both `st_size` and an estimate from `git cat-file -s`.
- Big fixtures are often deliberate (golden-file tests). Tone of the report matters: "review" not "delete".

## Definition of done

On a real 500-test suite, the report names ≥3 concrete savings (MB or seconds) with file:line evidence, and `--apply` is limited to provably unused data files, recoverable from trash.
