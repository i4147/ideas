# 51 — `project-first-run` (can I actually run this repo?)

> **Difficulty 4/10** · **Effort ~5 days** · **Tier: medium**
> **Prior art: ⚠️ partial** — `dependabot`-style bots (deps only), `pre-commit` (hooks only), `devcontainer`/`devcontainer-cli` (declarative, if the project has one), `nix flake`/`devbox` (if the project has one), `mise`/`asdf` (tool versions), `make setup` (if it exists), `repo-copier`, `onboard` (opinionated), `semantic-grep`.
> **Merged from:** "project onboarding generator", "unfamiliar Python repo setup checklist", "local environment sanity checker" (3 entries).
> **Pivot required?** Yes — read-only *diagnosis* with a fix list, not execution.

## The problem

You clone a repo you don't know. `README` says `pip install -r requirements.txt`; the repo has `uv.lock`, a `Makefile` with 14 targets, a `docker-compose.yml` for Postgres, `.python-version` 3.12, a `justfile`, and a `tests/` folder that needs `TEST_DATABASE_URL`. You spend 40 minutes discovering this. An experienced dev builds a mental checklist; a tool can build it too.

The critical constraint: **do not execute anything.** Running `make setup` from an unknown repo is how you get `curl | bash`'d. Diagnosis only, and if a step is suggested, show the exact command with where it came from.

## What it must output

```
$ project-first-run .
REPO  shop-api (Python 3.12) · uv · pytest · docker compose · pre-commit

FACTS
  interpreter   .python-version = 3.12 ; pyproject requires-python >= 3.11
  package mgr   uv.lock present (uv 0.5+ assumed; not installed ⚠)
  venv          .venv present, created 41d ago, 212 packages
  env           .env missing (needed: DATABASE_URL, REDIS_URL, SECRET_KEY)
  services      docker-compose.yml: postgres:16 (5432), redis:7 (6379)  — none running
  migrations    alembic.ini + alembic/versions (12) → `alembic upgrade head`
  tests         pytest; markers: slow, integration; needs TEST_DATABASE_URL
  lint          ruff (format+check), mypy (strict)
  hooks         .pre-commit-config.yaml: 6 hooks, not installed ⚠

LIKELY SETUP (from evidence, not invented)
  1. uv sync                          [uv.lock]
  2. cp .env.example .env             [.env.example; 3 keys have no default]
  3. docker compose up -d postgres redis
  4. uv run alembic upgrade head      [alembic.ini]
  5. uv run pytest -q -m "not slow"   [pyproject markers]

BLOCKERS
  ✗ uv not installed (pyproject has no requirements.txt fallback)
  ✗ SECRET_KEY has no example value and no generator script
  ✓ all 212 packages importable by the current interpreter
```

## Signal extraction (be concrete)

| Fact | Evidence |
|---|---|
| interpreter | `.python-version`, `.tool-versions`, `pyproject requires-python`, CI matrix |
| package manager | `uv.lock`, `poetry.lock`, `Pipfile.lock`, `pdm.lock`, `requirements*.txt`, `environment.yml` |
| install command | lockfile type + `Makefile` targets (`grep -E '^(install|setup|dev):'`), `justfile`, README code blocks |
| env vars | `.env.example` keys ∪ AST scan of `os.environ` (reuse file 04) |
| services | `docker-compose.y*ml` service names/ports/images, `.devcontainer/*.json` |
| migrations | `alembic.ini`, `migrations/`, `manage.py migrate`, `prisma/schema.prisma` |
| tests | `pytest.ini`/`[tool.pytest]`, `tox.ini`, `no tests` (honest) |
| lint/format | config sections present in `pyproject.toml`, `.pre-commit-config.yaml` |
| tool versions | `.tool-versions`, `.nvmrc`, `rust-toolchain.toml` |

**Verification without execution**: check `importlib.util.find_spec` for each declared dependency in the *current* interpreter (cheap, safe), check `shutil.which` for required binaries, `socket.connect_ex` to `127.0.0.1:5432` for compose services, and file permissions for scripts. That yields the "blockers" section, which is the part that saves the 40 minutes.

## CLI

```bash
project-first-run .                    # the report
project-first-run . --json             # for a bot that comments on new clones/issues
project-first-run . --script > setup.sh   # emits the commands, marked "review before running"
project-first-run doctor               # compare this machine against the repo's requirements
```

`--script` prints commands with a `# from: <file>` provenance comment for each line and a header stating it was generated, not verified. Never run it.

## Tests

Fixture repos (tiny dirs) for each package manager, a repo with `requirements.txt` + `pyproject` conflict, a repo with no tests, a `docker-compose.yml` with `depends_on` chains, a `.env.example` with `# comment` lines and duplicate keys, a monorepo with two pyprojects, and one that must produce "insufficient evidence" rather than a guess. Assert no subprocess is spawned for anything except `--script` generation (monkeypatch `subprocess.run` to fail the test if called).

## Pitfalls

- Never `pip install` or `make` anything, even to "check" — that's the whole safety contract.
- README instructions are often wrong; rank evidence (lockfiles/config) above prose, and label prose-derived steps as "README says".
- Don't assume `python3` is the right interpreter: read `.python-version` and report a mismatch with `sys.version_info`.
- Compose services are often not started deliberately (CI-heavy repos) — report, don't judge.
- Long reports don't get read: cap at ~25 lines, put blockers first if any exist.

## Definition of done

On 10 unfamiliar real repos, the checklist's first three steps are correct in ≥8, every command cites its source file, and the tool provably runs zero repo code.
