# 44 — `pyproject-doctor` (diagnose `pyproject.toml` drift)

> **Difficulty 4/10** · **Effort ~5 days** · **Tier: medium**
> **Prior art: ❌ name already taken and implemented** — PyPI `pyproject-doctor` 0.5.0 ("offline deep validator: file existence, URL/email format, PEP 440 versions…"), `pyproject-fmt` 2.30.6 (formatting), `validate-pyproject` + `validate-pyproject-schema-store`, `ruff`'s `[tool.ruff]` config checks, `mypy`/`pytest`'s own config validation, `check-wheel-contents`, `twine check`.
> **Pivot required?** Yes, and it must be sharp: **cross-tool consistency**, not schema validation.

## What exists (be precise about it)

- `validate-pyproject`: validates against the PEP 621 JSON schema **plus per-tool plugins** (ruff, mypy, black, coverage, setuptools…) — i.e. it already checks that `[tool.ruff]` keys are legal.
- `pyproject-fmt`: formatting (sorting, quoting, one-item-per-line) — must not be re-implemented; depend on it or ignore formatting.
- `pyproject-doctor` (PyPI, 0.5.0): offline validator, dead files, URL/email formats, PEP 440 versions.
- Each tool's runtime: ruff/mypy/pytest error out on unknown keys anyway, though the messages are poor.

## The drift questions none of them ask

1. **Same constraint declared twice, differently.** `requires-python = ">=3.9"` in `[project]` but `[tool.mypy] python_version = "3.8"`, `[tool.ruff] target-version = "py38"`, `[tool.black] target-version = ["py38"]`, a `python_requires` in a legacy `setup.py`, and CI matrix `3.9–3.12`. Which is the truth? This mismatch is extremely common and produces *weird* errors ("ruff suggests a walrus here but mypy rejects it").
2. **Dead tool config.** `[tool.isort]` for a project that switched to ruff; `[tool.pytest.ini_options]` next to a `pytest.ini` (which silently wins); `[tool.coverage]` with `fail_under` that CI never reads; `[tool.black]` while `ruff format` is used.
3. **Dependency duplicates and dead extras.** `requests` in `dependencies` *and* `[project.optional-dependencies].dev`; an extra `docs` that nothing installs; `[dependency-groups]` (PEP 735) overlapping with an extra.
4. **Constraint conflicts inside one file.** `dependencies = ["httpx>=0.28"]` and `optional-dependencies.test = ["httpx<0.28"]`; a direct pin that contradicts a transitive floor implied by another direct pin (needs metadata → optional, network).
5. **Entry point / build backend mismatches.** `[project.scripts] foo = "pkg.cli:main"` where `pkg/cli.py` has no `main`; `build-backend` pointing at a missing module; `package-data` including files that are gitignored; `[tool.setuptools.packages.find]` that would not find `src/` layout.
6. **Deprecated/removed keys**: `[tool.setuptools] license = {file = …}` vs PEP 639 `license-files`; `[project.license]` table form deprecations; `[tool.pytest.ini_options] asyncio_mode` when the plugin isn't installed.

That's a diagnoser, not a validator: it needs to *cross-reference* sections and the filesystem and (optionally) the installed tooling.

## Design

```bash
pyproject-doctor check                        # all rules, severity-tagged
pyproject-doctor explain "tool.mypy.python_version"
pyproject-doctor fix --dry-run                # only mechanical, safe fixes
pyproject-doctor check --format github        # ::warning annotations
```

Rule engine: each rule is a dataclass with `id` (PD001…), `severity`, `needs` (`sections`, `filesystem`, `network`), and a `check(ctx) -> list[Finding]`. Findings include a JSON-pointer path (`/tool/mypy/python_version`), the offending value, a one-line impact, and an optional autofix edit (kept as a `tomlkit`-based *surgical* edit so comments and formatting survive).

Autofix policy: only unambiguous normalisations — unify `requires-python`/`python_version`/`target-version` to the *lowest* declared value, delete config for a tool whose replacement is present and configured, remove duplicate dependency strings. Everything else is a suggestion with a printed patch.

Optionally, **fingerprint the installed tools** (`ruff --version`, `mypy --version`, plugin presence from `importlib.metadata`) so "you configured a plugin you don't have" is detected — that's genuinely useful and no offline validator does it.

## Tests

One fixture `pyproject.toml` per rule (plus a clean one that must produce zero findings). Golden snapshots of the rendered output. A `tomlkit` round-trip test: after `fix`, comments, key order, and quoting are preserved except at the edited key. A test that a `pytest.ini` shadowing `[tool.pytest.ini_options]` is reported with the winning file named.

## Pitfalls

- Never claim a config is "unused" from static analysis alone: tools read configs in non-obvious ways (`tox`, CI overrides, `-c` flags). Phrase as "nothing in this file or CI appears to read this".
- Support `pyproject.toml` discovery per-repo (monorepos have several) — walk and report per file.
- Don't reformat. `pyproject-fmt` exists and users will run both.
- PEP 621 vs PEP 639 vs PEP 735 are all in flux; date-stamp rules that depend on packaging standards and cite the PEP number in `explain`.
- Network rules (transitive floor checks) must be strictly opt-in (`--online`), cached, and never block `check`.

## Definition of done

On a real 4-year-old project, `check` finds at least three genuine inconsistencies (Python version mismatch, dead `[tool.isort]`, duplicate dependency), `fix --dry-run` prints a minimal comment-preserving patch, and the tool composes with `validate-pyproject` rather than replacing it.
