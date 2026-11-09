# 43 — `venv-diff` (what changed between two environments, and does it matter)

> **Difficulty 4/10** · **Effort ~4 days** · **Tier: medium**
> **Prior art: ⚠️ partial** — `pipdeptree`, `pip-diff` (2019, unmaintained, py2-era), `pip-compile --dry-run`, `uv pip sync --dry-run`, `poetry lock --check`, `diffoscope` on lockfiles, plain `diff` of `pip freeze`.
> **Pivot required?** Yes — a version diff is easy; **impact classification** is the product.

## The problem

"It worked yesterday." Between yesterday and today, `pip freeze` differs by 9 lines. Which of them matters? Which are direct vs transitive? Which flipped a licence or bumped `Requires-Python` above yours? Which are major versions with breaking changes? Which dragged in 3 new packages as transitive dependencies?

`pip-diff` prints added/removed lines. Nothing classifies.

## Design

```bash
venv-diff .venv-old .venv-new
venv-diff uv.lock poetry.lock --format markdown
venv-diff --from-freeze old.txt --to-freeze new.txt --fail-on major,license,python
```

Output:

```
9 changes in 128 packages
MAJOR      sqlalchemy 1.4.52 → 2.0.36        direct   ⚠ 8 breaking changes in changelog
MAJOR      pydantic 1.10 → 2.9               direct   ⚠ migration guide required
MINOR      httpx 0.27.0 → 0.28.1             direct
PATCH      urllib3 2.2.2 → 2.2.3             transitive ← from httpx
ADDED      anyio 4.6.0 (transitive, new path: httpx → anyio)
REMOVED    sniffio 1.3.1 (no longer required)
PYTHON     black 24.4 requires-python >=3.9 → >=3.10   ⚠ your floor is 3.9
LICENSE    some-lib MIT → Apache-2.0                     ⚠ policy check
```

Classification rules (deterministic, testable):

- semver-ish comparison on `packaging.version.Version` (`1.4 → 2.0` = major; `0.x` bump = "pre-1.0 major", a real trap for `0.27 → 0.28`)
- **direct vs transitive**: cross-reference roots with the same logic as file 42
- **new transitive path**: a package present in both but now reachable via a different parent (this is how a "no version changed" upgrade still breaks)
- **requires-python delta**: compare `Requires-Python` of old and new versions against `project.requires-python`
- **licence delta**: normalise to SPDX (see file 36)
- **yanked/abandoned flags**: from PyPI JSON (`yanked`), last release date

## Implementation

```
venv_diff/
  sources.py  # venv dir (importlib.metadata), uv.lock, poetry.lock, requirements.txt, pip freeze text
  graph.py    # build parent->child edges (metadata Requires-Dist, or lockfile edges)
  classify.py # Change list with kind/severity
  enrich.py   # optional: PyPI JSON for requires-python, licence, upload dates, changelog URL
  render.py   # table | markdown | json | github-annotations
```

Reading a venv without activating it: `importlib.metadata.distributions(path=[site_packages])`. Find site-packages via `<venv>/lib/python*/site-packages` (*not* by running the venv's python — it may be broken, which is often the reason you're diffing).

Lockfile parsing: `uv.lock` and `poetry.lock` are TOML with explicit `dependencies` edges — parse directly with `tomllib` (stdlib) rather than resolving anything. This is where most of your accuracy comes from.

## CI mode

`--fail-on major,license,python` with GitHub annotations (`::warning file=pyproject.toml::…`) and a sticky-comment markdown table. Renovate/Dependabot give you a version diff per PR; this gives you an *impact* summary, which is the missing half of automated dependency PRs.

## Tests

Fixture lockfiles: a major bump, a `0.x` minor bump (must classify as breaking), a transitive reparent with no version change, a direct→transitive demotion, a package with `requires-python` crossing your floor, a licence change, extras/markers changing reachability, and a package present in both with different hashes but the same version (a repackaged wheel — report it, it's real). Golden outputs for each format.

## Pitfalls

- Version strings are not always semver (`2024.1`, `1.0.0rc1`, `calver`) — never crash on `VersionInvalid`, fall back to string difference with a "unknown significance" label.
- Don't claim a changelog URL is a breaking-change list: link to it, and use PyPI's project URLs (`Changelog`, `Changes`) rather than guessing.
- Markers: a package "removed" may simply be excluded by a marker on a different platform — say "not present in this environment", not "removed".
- Comparing a venv against a lockfile is a mixed abstraction: warn, and compare only shared fields.
- `--fail-on` defaults must be conservative (major only), or CI never goes green.

## Definition of done

Diffing two real venvs (128 packages) produces a 9-line, correctly classified report in <2 s, and CI fails only on a genuinely major or licence change.
