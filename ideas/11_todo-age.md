# 11 — `todo-age` (how old is that TODO, and who should fix it)

> **Difficulty 2/10** · **Effort ~2 days** · **Tier: warm-up**
> **Prior art: ❌ already built** — PyPI `todoage` 0.1.0 (2026-06: "scan for TODO/FIXME/HACK/XXX/BUG and use git blame to show how old"), plus `leasot` (JS), `todocheck`.
> **Pivot required?** Yes — age alone is trivia. **PR-scoped debt budgets and author attribution** are the product.

## The problem

Every codebase has `# TODO: fix this properly` from 2019, in a file nobody owns, next to code nobody understands. Existing scanners either list TODO counts (noise) or show age (interesting once, never again). What a team can act on is: *"this PR adds 3 new TODOs and the file already had 11"*, and *"72 % of the debt in `billing/` was written by two people who left"*.

## What exists

`todoage` (PyPI) already does comment scan + `git blame` age. `leasot` is JS-ecosystem, configurable tags, no blame. `rg -n TODO` is what most people use. IDE plugins show TODOs in a panel with no history.

## The pivot: budgets, diffs, ownership

```bash
todo-age scan                        # totals per directory + age histogram
todo-age scan --pr --base origin/main   # only debt this branch adds  ← the CI mode
todo-age budget --config .todo-age.toml  # fail when a path exceeds its allowance
todo-age owners --top 10             # debt by author, using blame's commit author
todo-age list --older-than 2y --tag FIXME --format json
```

Console output should lead with the punchline:

```
TODO DEBT  142 items (38 FIXME, 6 HACK, 3 XXX)
  median age 11 months · oldest 4y 7m  src/legacy/importer.py:88  (author: @dana, 2021-03)
  hotspots: src/billing (31 items, +4 this PR)  src/legacy (44, unchanged)
  BUDGET FAILED  src/billing: 31 > 25 allowed
```

## Implementation

**Scanning.** Use `git grep -n -I -E '\b(TODO|FIXME|HACK|XXX|BUG)\b'` for speed and honour `.gitignore` for free. Then filter by comment context: run the matched line through a cheap per-language check — for Python, `tokenize` the file and keep matches that fall inside `COMMENT`/`STRING` tokens (kills matches in regexes and identifiers); for JS/Go/Rust use a small line heuristic (line starts, after `//`, `#`, `/*`, `*`). Language → comment syntax table for ~15 languages, with `--tags` override.

**Age.** `git blame --porcelain -L <line>,<line> -- <file>` per hit is O(n) subprocess calls — too slow for 1,000 hits. Instead blame once per file with `--line-porcelain` and build a `line -> (commit, author, date)` map; a 400-file repo takes ~3 s. Cache by `(file, blob-sha)` in `.todo-age-cache.json`.

**PR mode.** Diff the *tag set* between base and head: `git diff --unified=0 base...head` and count added `+` lines matching a tag. Report added/removed per file, and attribute to the commit author.

**Budget config.**

```toml
[tool.todo-age]
tags = ["TODO", "FIXME", "HACK"]
max_age = "18mo"          # warn
[tool.todo-age.budget]
"src/billing/**" = 25      # hard cap on item count
"src/**" = 200
[allow]                    # per-line allowance with a ticket reference
"src/legacy/importer.py:88" = { ticket = "PROJ-441", until = "2027-03-01" }
```

The `allow`-with-ticket mechanism is what makes a budget survivable: exceptions must cite an issue, and they expire.

## Tests

Fixture repos with commits dated via `GIT_AUTHOR_DATE`; assert age buckets, that a TODO inside a Python string literal *is* counted but one inside a regex pattern is not, that a moved line (`git log -M`) keeps its age, and that PR mode counts only `+` lines. Also a test that an expired allowance appears as a failure.

## Pitfalls

- Blame is wrong after mass reformatting (every line attributes to the formatter) — offer `--ignore-revs-file` passthrough and detect a formatter commit (>50 % of lines from one commit) to warn.
- Don't reflow long tag lists to "TODO(x):" style; match `TODO(name)`/`TODO[PROJ-1]` and capture the owner.
- Vendored/generated code will drown the report: default-exclude `*.min.js`, `*_pb2.py`, `migrations/`, and anything with a "generated" header in the first 3 lines.
- Git submodules and `--depth 1` clones break blame; degrade to mtime-free "age unknown".

## Definition of done

`scan` on a 500-file repo <4 s with blame, PR mode blocks a PR that adds debt to an over-budget directory, and every failure message names a file, a line, and a human.
