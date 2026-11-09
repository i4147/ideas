# 62 — `release-captain` (one command: bump, changelog, build, tag, checklist)

> **Difficulty 5/10** · **Effort ~5 days** · **Tier: hard-ish**
> **Prior art: ⚠️ mostly solved, but scattered** — `release-please` (Google, PR-driven versioning), `semantic-release` (Node, plugin-based), `commitizen` (`cz bump` + changelog), `hatch version`/`hatch build`/`hatch publish`, `bump2version`, `towncrier` (news fragments), `twine check`, `build`, `gh release create`, `cibuildwheel`, `nox`/`tox` for matrix builds.
> **Pivot required?** Yes — the gap is not automation but **a pre-flight check that refuses to release a broken package**, plus a human-readable plan.

## The problem

Publishing a small package by hand is 12 steps with 4 ways to get it wrong:

```bash
# the real-world sequence, done from memory every time
sed -i 's/1.4.2/1.4.3/' pyproject.toml              # forgot __init__.__version__
git tag v1.4.3                                       # tagged before committing the bump
python -m build                                      # built from a dirty tree
twine check dist/*                                   # catches a broken README render
twine upload dist/*                                  # uploaded 1.4.2 by mistake (already exists!)
git push --tags                                      # tag pushed, GitHub release forgotten
```

The failures are embarrassing and public: an sdist that doesn't include a data file, a version bump in one file out of three, a `README.md` that renders to nothing on PyPI, a wheel that imports on your machine because of a stray `src/` path, and a tag naming a commit that never contained the bump.

## The pivot: a preflight gate

```bash
release-captain plan --bump minor         # show every action, change nothing
release-captain check                     # 24 blocking validations
release-captain release --bump minor --yes
release-captain check --dist dist/        # validate an existing build (CI use)
```

`check` is the product. Blockers, each with the exact fix:

```
PREFLIGHT  shop-api 1.4.2 → 1.4.3
BLOCKING
  ✗ working tree dirty (3 files)                 commit or stash first
  ✗ version in 3 places: pyproject.toml 1.4.2 · src/shop/__init__.py 1.4.1 · docs/conf.py 1.4.0
  ✗ sdist missing data: package_data lists "static/*.css" but static/app.css is gitignored
  ✗ Python 3.12 classifier missing while requires-python = ">=3.12"
WARNINGS
  ! README renders no long_description_content_type set → PyPI shows plain text
  ! no CHANGELOG entry for 1.4.3 (commitizen detected; 9 commits since v1.4.2)
  ! twine not installed (needed for check/upload)
OK  18 checks: LICENSE file · SPDX licence expression · build backend pinned · wheel imports in a clean venv ·
    metadata URLs reachable (4) · no dev deps in install_requires · tests pass (142, 11.4 s) · tag v1.4.3 free
```

## The checks worth implementing (the differentiating content)

1. **Version consistency** across `pyproject.toml`, `__init__.py`/`__version__`, `docs/conf.py`, `Cargo.toml` (maturin), and any hard-coded user agent. Detect the single-source pattern (`dynamic = ["version"]` + `version = attr:`) and *use* it rather than duplicating.
2. **Built-artifact correctness**: build into a temp dir, then in a **fresh venv** `pip install --no-deps` the wheel, `python -c "import pkg; print(pkg.__version__)"`, and compare the installed `.dist-info` file list against `git ls-files` to find missing/extra files. That single test catches the most common release bug in Python packaging.
3. **sdist completeness**: unpack the sdist, `pip install` from **it** in another fresh venv, and run `import` + a one-line smoke test. sdists are what downstream distros use, and they're tested least.
4. **Metadata sanity**: `twine check dist/*` (README render), `Requires-Python` vs classifiers, `project.urls` HTTP status (`--online`), licence file present and matching `license-files`, no `Development Status :: 7 - Beta` with `1.4.x`.
5. **Hygiene**: no `.env`, no `tests/fixtures/*.db`, no `dist/` in the sdist; wheel size budget; `MANIFEST.in` versus `[tool.setuptools] include-package-data`.
6. **Git state**: clean tree, on the expected branch, no unpushed commits, tag free (local *and* remote: `git ls-remote --tags origin`), no existing PyPI release for the target version (`https://pypi.org/pypi/<name>/<ver>/json` → 404 required).
7. **Tests + lint gate** via configurable commands (`commands = ["pytest -q", "ruff check"]`), run in a subprocess with output captured and a hard timeout.

## Design constraints

- **Idempotent and resumable**: every step is a named stage (`bump`, `changelog`, `build`, `check`, `tag`, `push`, `upload`, `release`) written to `.release-captain/state.json`; `--from tag` resumes after a failed upload. Half-released packages are the norm when a network call fails.
- **Two-phase by default**: `plan` prints the full sequence (commands + file edits) and exits 0; `release` requires `--yes` and refuses if `plan` would have been different (`--recheck`).
- **Never force-push; never `--skip-existing`** unless asked. Upload with `twine upload` (or `--publish tool=uv`) and *verify* afterwards with the PyPI JSON API before tagging the GitHub release.
- **Multi-file bumps are edits, not `sed`**: use `tomlkit` (round-trip) for `pyproject.toml` and `ast`/`libcst` for Python version strings.

## Tests

Fixture repos with planted defects, one per check (dirty tree, three out-of-sync versions, gitignored package data, missing classifier, unreachable URL, tag already on the remote). Use a fake `twine`/`gh` on `PATH` that records invocations, and a fake PyPI JSON endpoint (`respx`). Assert: `plan` performs zero mutations, `release` stops at the failing stage, `--from` resumes, and a fresh-venv import test fails when the wheel omits a data file.

## Pitfalls

- Never publish from CI without an explicit `--yes` + a `PYPI_TOKEN` in the environment; refuse interactive prompts in non-TTY.
- `build` caches nothing: always build into a clean temp dir, or you'll upload a stale wheel.
- Version guessing from git tags breaks on monorepos/multi-package repos — require an explicit `--bump` or read the current version from single-source metadata.
- `hatch`/`poetry`/`uv` each have their own publish path; shelling out to the tool the project already uses beats reimplementing upload (and avoids token-handling code).
- Post-release: create the GitHub release *after* PyPI confirmation, and attach the built artifacts.

## Definition of done

`check` catches 3 planted defects in fixture repos, `release --bump patch --yes` takes a clean repo from commit to a PyPI-visible version and a GitHub release without manual steps, and a failed upload is resumable without re-publishing.
