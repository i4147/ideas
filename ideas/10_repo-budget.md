# 10 — `repo-budget` (size budgets per path, enforced in CI)

> **Difficulty 2/10** · **Effort ~3 days** · **Tier: warm-up**
> **Prior art: ✅ genuine gap** — no PyPI `repo-budget`/`repobudget`; closest are GitHub's repo-size API, `git-sizer`, `du`, and wheel-size checks inside `twine`/`auditwheel`.
> **Pivot required?** No — this is a real, small, unserved need. Ship it.

## The problem

Repositories and release artifacts grow silently. A 4 MB PNG in `docs/` gets committed, a fixture is regenerated at 10× size, `dist/` gets committed once, vendored JS sneaks into `static/`, and git history passes 1 GB. Nobody notices until CI gets slow, clones take a minute, or PyPI rejects a wheel over 100 MB.

`git-sizer` measures history but has no per-path policy and no CI annotations. `du` has no history and no config. Nothing enforces *"`docs/**` must stay under 20 MB, and `dist/*.whl` under 8 MB"*.

## The design that makes it a tool and not a script

```toml
# .repo-budget.toml
[defaults]
fail = "error"                  # error | warn | off

[[budget]]
path = "docs/**"
limit = "20MB"
why  = "docs ship in the sdist"

[[budget]]
path = "tests/fixtures/**"
limit = "15MB"
[[budget]]
path = "dist/*.whl"
limit = "8MB"
why  = "PyPI practical limit / install ergonomics"

[[budget]]
path = "assets/**"
limit = "2MB"
[budget.allow]                  # explicit exceptions, with an expiry
"assets/logo-hero.png" = { limit = "6MB", until = "2027-01-01", why = "marketing asset" }

[history]
max_commit_bytes = "25MB"       # single blob accidentally committed
max_repo_bytes   = "800MB"      # whole .git
```

```bash
repo-budget check                      # working tree + git object scan
repo-budget check --base origin/main --head HEAD   # PR mode: only what this PR added
repo-budget explain dist/              # biggest files, newest first, with commit + author
repo-budget history --top 10           # largest blobs ever, still reachable
repo-budget github-annotations         # ::error file=…,line=… for GitHub Actions
```

## Implementation notes that matter

**Working-tree walk.** Do not follow symlinks; skip `.git` internals; use `os.scandir` recursively and `st_size` (sparse files: use `st_blocks * 512` for real disk usage and report both). Aggregate per budget with `fnmatch`-with-`**` semantics — reuse `pathspec` (the same library pip uses) rather than writing a glob engine.

**PR mode.** `git diff --numstat <base>...<head>` gives additions per path, but not sizes. Instead resolve the head blob of each changed path (`git cat-file -s <rev>:<path>`) and budget *only* those; that answers "did this PR add a 9 MB fixture?" without scanning the world. Report both delta and total.

**History mode.** One `git rev-list --objects --all` piped into `git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)'` gives every reachable object with size in a single pass — ~2 s for a 500 MB repo. Group by path, take max-blob per path, and report the top offenders with the commit that introduced them (`git log --diff-filter=A --format=%h -- <path>`; cache it, it's slow).

**CI annotations.** Emit `::warning file=docs/huge.pdf::docs/huge.pdf is 4.2MB (budget 2MB)`. GitHub renders these inline on the PR diff — cheap and very visible.

**Output.** Table by default; `--json` for tooling; `--format markdown` for a sticky PR comment.

## Build

```
repo_budget/
  config.py     # tomllib + validation + humanized sizes ("20MB" = 20_000_000 or 20 MiB? pick MiB, document)
  walk.py       # working tree with pathspec matching
  gitdiff.py    # PR mode
  githistory.py # rev-list + batch-check
  render.py, cli.py
```

Humanized sizes: parse both `20MB` and `20MiB` and *print* the canonical form; pick 1 MB = 1_000_000 by default (matches PyPI/Docker) and say so in `--help`. Ambiguity here generates bug reports.

## Tests

`tmp_path` repos built with `subprocess`: file just under, just at, just over budget; a 25 MB blob added in history then deleted (must still be caught by history mode); an `allow` entry that expired (must warn); a symlink loop; a sparse file; a path with `**` in the middle of the pattern.

## Pitfalls

- Git compresses; blob size ≠ repo size. Never present `gitsize == disk` — say "uncompressed content size".
- LFS pointers are 130 bytes: detect `.gitattributes` LFS lines and report "LFS-tracked, size unknown".
- Windows/macOS equivalence (case-insensitive) breaks `pathspec` matches; normalise case only when `--case-insensitive`.
- Don't walk into `node_modules`/`.venv` by default (configurable `excludes`, defaulting to the repo's `.gitignore`).
- Failing CI on *existing* debt is how tools get removed: default PR mode should fail only on regressions, with `--strict` for full compliance.

## Definition of done

`check` on a 1 GB history repo in <5 s, PR mode annotates exactly the files the PR touched, and a config with `why`/`until` fields makes the policy reviewable by humans.
