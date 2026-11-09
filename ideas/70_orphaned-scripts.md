# 70 — `script-inventory` (find the one-off scripts nobody remembers)

> **Difficulty 5/10** · **Effort ~5 days** · **Tier: hard-ish**
> **Prior art: ⚠️ partial** — `vulture` (unused code, per-file), `deptry` (unused *dependencies*), `ruff`'s `F401`/`F841` (unused imports/locals), `deadcode`, `git-sim`/`git log` archaeology, `ripgrep` for references, `code-maat`/`git-of-theseus` (churn analytics), `semgrep` (pattern rules).
> **Pivot required?** Yes — "detect old one-off scripts that duplicate modern tooling" is a *judgement* task; the product must be a ranked, evidenced inventory, not a delete list.

## The problem

In a 6-year-old monorepo, `scripts/` holds 140 files: `fix_migration.py`, `backfill_2019.py`, `send_emails_v2.py`, `db_cleanup_FINAL.py`, `gen_fixture.py`. Some are still run by cron; most are dead. Nobody deletes them because "someone might need it", so the folder grows, and a new hire eventually runs the wrong one against production.

This is not "find unused code" (that's per-module and static). It's *archaeology*: cross-reference a script against how the project works **today**.

## What the report should contain (and nothing more)

```
$ script-inventory scripts/ --repo .
INVENTORY 141 scripts (78 Python, 41 shell, 22 other)

HIGH CONFIDENCE DEAD (12)
  scripts/backfill_2019.py       last run 2019-06 (in git log msg), imports a module removed in 2021
                                 (`from app.legacy import orders`)  · no caller, not in CI, not in cron
  scripts/send_emails_v2.py      superseded: `app/notifications/emailer.py` does the same 3 SMTP calls
                                 (0.86 similarity to app/notifications/emailer.py:120-180)

LIVE BUT FRAGILE (8)
  scripts/db_cleanup_FINAL.py    still referenced by crontab @daily; imports a private API
                                 (`app.db._engine`) that no longer exists → will fail at next run ✗
  scripts/gen_fixture.py         used by tests/test_fixtures.py::test_gen (keep)

DUPLICATE PAIRS (6)
  fix_migration.py ≈ fix_migration_v2.py (0.94)  → v2 used by Makefile, v1 unreferenced

DO NOT TOUCH (0 shown) — referenced by CI, cron, docs, or Makefile
```

## How to gather evidence (each item must cite a source)

1. **Reference index**: search the repo (excluding the scripts themselves) for each script's name and path — `Makefile`, `justfile`, `*.yml` (CI), `crontab*`, `systemd/*.timer|service`, `Dockerfile`, `docs/`, `README`, `pyproject [project.scripts]`, other code (`subprocess.run(["python", "scripts/x.py"])`).
2. **Runtime evidence**: shell history import (file 59's capture) + `~/.bash_history` grep + any `*.log` in the repo — matches mean it was *used*, which is different from *referenced*.
3. **Git archaeology per file**: creation date, last modified, last commit message, author churn, whether it was ever touched after its first commit (`git log --follow --format`).
4. **Death signals** (deterministic, citable): imports a module that no longer exists (`ast` + import graph); references an env var absent from `.env.example`; calls a CLI binary not in any Dockerfile/CI; hard-coded date literals older than 2 years; `sys.exit`/`TODO`/`FIXME` in the first 10 lines (a self-declared one-off).
5. **Supersession**: similarity between a script's body and modern module code (AST-normalised token shingles, 0.8+ threshold) plus matching library calls (both send email, both `pg_dump`). Report the *specific* modern file:line as the replacement — that single line converts "delete?" into a decision.
6. **Risk of deletion**: if any signal places it in cron/CI/docs, it's "do not touch"; if the script's imports are broken, it's already broken — flag it as *failing silently*, which is often more important than deleting it.

## CLI

```bash
script-inventory scripts/ [--repo .] [--json]
script-inventory --dead-only
script-inventory --explain scripts/fix_migration.py     # every signal, with evidence lines
script-inventory --export-candidates > cleanup.md        # markdown with `git rm` commands, never executed
```

Never delete. Emit a markdown checklist the team can review in a PR — deletion of a script is a social act, not a tool action.

## Tests

Fixture repo with 12 scripts and a Makefile/CI/crontab referencing 4 of them; scripts importing removed modules; a duplicate pair; a script referenced only in a doc; a script referenced only from shell history (simulated history file). Assert classification for each, that `--explain` cites the exact evidence line, and that no `git rm` is ever executed (monkeypatch `subprocess` to assert no destructive call). Performance: 500 scripts under 5 s.

## Pitfalls

- False "dead" on a script run manually from a laptop is the main risk: default the confident bucket to scripts with *both* no references *and* a broken/dead dependency signal, and label everything else "review".
- Similarity between two unrelated 20-line scripts is high (boilerplate) — require ≥30 significant tokens before a duplicate claim.
- Monorepos have multiple roots and `scripts/` dirs; support several `--root`s and dedupe.
- Non-Python scripts can't be AST-analysed: use shebang + a light token scan and mark them "lower confidence".
- The tool must never suggest removing something with a `#!/usr/bin/env` + `argparse` + reasonable docs — that's a tool, not a one-off; use "looks like a maintained tool" as a guard.

## Definition of done

On a real monorepo, the top 5 "dead" scripts are ones the team confirms as dead, every claim cites a file:line or a git fact, and the "live but fragile" bucket catches at least one cron job that would fail next run.
