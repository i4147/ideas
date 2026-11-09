# 42 — `dep-why` (why is this installed, and what breaks if I remove it)

> **Difficulty 4/10** · **Effort ~4 days** · **Tier: medium**
> **Prior art: ⚠️ partial** — `pipdeptree` (4.2.14: `--reverse`, `--warn-fail`), `pip show`, PyPI's "Required-by", `uv tree`, `poetry show --tree`, `pip-audit`'s env parsing, `importlib.metadata`.
> **Note:** PyPI `depwhy` 0.1.1 claims "explains Python dependency conflicts in plain English" — a different (conflict-focused) tool. Name collisions: `dep-why` is free.
> **Pivot required?** Yes — the question is not "who requires it" but **"what happens if I drop it"**.

## The problem

`pipdeptree -r -p requests` already answers "who pulls this in". The awkward moment in real life is different: *"I want to remove `pandas` — is it really unused, or is something importing it at runtime?"* and *"I have three versions of `urllib3` constraints fighting; explain it like I'm tired."*

## Design: reverse dependencies + actual usage + removal impact

```bash
dep-why pandas                     # why installed (chain), and who imports it
dep-why --remove pandas            # blast radius: files, functions, and CLI entry points that break
dep-why --conflict urllib3         # why the resolver picked 2.2.3, in plain English
dep-why --unused                   # installed but never imported anywhere in the project
dep-why --tree requests --depth 3 --format markdown
```

Output for the flagship case:

```
$ dep-why --remove pandas
pandas 2.1.3  installed by: your requirements.txt:14 (direct)
imported by (static analysis of 214 files):
  src/report/aggregate.py:9        import pandas as pd
  src/report/aggregate.py:41       pd.read_csv(...)
  scripts/export.py:3              from pandas import DataFrame
  tests/test_aggregate.py:5
transitive deps that would disappear: numpy (also used directly in 4 files ⚠), pytz, python-dateutil
verdict: NOT removable without code changes (3 modules, 6 call sites)
runtime imports not visible statically: none detected
```

The `numpy` line is the value: removing `pandas` would also drop `numpy`, which the project uses directly. `pipdeptree` shows the graph but doesn't cross-reference your own imports.

## Implementation

1. **Installed metadata**: `importlib.metadata.distributions()` → `Requires-Dist` parsing with `packaging.requirements` (handle extras and markers: `; extra == "s3"` and `python_version < "3.11"`, evaluated for the current interpreter).
2. **Resolution**: for lockfiles that pin everything (`uv.lock`, `poetry.lock`), read the pins directly — much more accurate than metadata. Otherwise use installed versions and label the output "installed, not resolved".
3. **Reverse tree**: BFS upward from the target to direct dependencies (roots = packages named in `pyproject.toml`/`requirements*.txt`). If multiple paths exist, print all (that's the "why is there a conflict" answer).
4. **Import scan**: `ast` walk of the project for `import X`, `from X import …`, `importlib.import_module("X")` (collect literals), and `pytest.importorskip("X")`. Map `import name` → distribution via `dist.packages_distributions()` (handles `PIL`→`Pillow`, `yaml`→`PyYAML` — the mapping everyone forgets).
5. **Conflict explanation**: when `packaging` finds incompatible specifiers among the chain, print the *constraint chain* (`a requires urllib3<2`, `b requires urllib3>=2.2`) and the pinned result, with the exact `Requires-Dist` lines as evidence. Add `--explain` for a sentence per constraint.
6. **Size attribution** (the `depweight` idea from the list): `Path(dist.locate_file("")).rglob()` sizes per distribution, sorted, with "shared with N others" impossible to compute exactly — so report unique directory size and say so.

## Tests

Synthetic environments built as `dist-info` directories in `tmp_path` (no installs): a diamond dependency, a version conflict, an extra-gated requirement, and a marker-gated one. Import-scan fixtures: `import PIL`, `from PIL import Image`, `importlib.import_module("yaml")`, a `try/except ImportError` optional import, and an import inside `if TYPE_CHECKING`. Assert the `numpy`-also-used-directly warning fires.

## Pitfalls

- Namespace packages and vendored copies (`pip._vendor.requests`) distort both trees; detect vendored paths and exclude with a note.
- `packages_distributions()` is fast but requires the distribution to be installed *in the analysed environment* — for lockfile mode it won't exist; fall back to a name-normalization heuristic (PEP 503: lowercase, `-`/`_`/`.` interchangeable) and say so.
- Editable installs point at the source tree; size reporting will be wrong (report "editable").
- Conditional/dynamic imports mean "unused" is never certain: phrase it as "no static imports found", never "safe to remove".
- Python version markers must be evaluated against the *target* version, not the running one, when `--python 3.12` is given.

## Definition of done

On a real project, `--remove X` names every affected file:line and warns about co-removed direct dependencies, and `--conflict` explains a version pin in one sentence with quoted evidence.
