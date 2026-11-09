# 17 — `markdown-lint-cli` (Markdown linting)

> **Difficulty 3/10** · **Effort ~3 days to reach parity, months to exceed** · **Tier: warm-up**
> **Prior art: ❌ heavily solved** — `markdownlint-cli2` (Node, canonical), `pymarkdown` (PyPI), `mdl` (Ruby), `rumdl` (Rust, fast), `remark-lint`, plus CI actions for each.
> **Verdict: don't build a general linter.** If the team wants Python, contribute to `pymarkdown` instead.

## The problem

Markdown in a repo rots: broken relative links, skipped heading levels, inconsistent list markers, trailing spaces, unlabelled code fences. Real problem, already solved by mature linters with 60+ rules and auto-fix.

## What exists

| Tool | Notes |
|---|---|
| `markdownlint-cli2` | the de-facto standard; rule set documented, `--fix` works; requires Node |
| `pymarkdown` | Python, active, plugin-based, `--fix`, pre-commit hook exists |
| `rumdl` | Rust, very fast, LSP mode — best current Python-repo compromise (single binary) |
| `mdl` | Ruby, older rule set, slow |

A new Python linter starts 60 rules behind and will be judged on false positives in someone's README table. That is a losing project.

## The one defensible niche

Not "lint Markdown" but **"lint Markdown *as it relates to the repo*"** — rules that require context the existing linters do not have:

1. **Cross-file link graph**: relative links that resolve to a heading anchor that no longer exists (`docs/guide.md#deploy` → the `## Deploy` heading was renamed). `markdownlint` checks link *syntax* and `mdl` checks resolution; none checks anchors across files.
2. **Code-block ↔ source drift**: fenced blocks tagged `python path=src/foo.py` must still match the actual file (or at least parse). Catches docs that rotted two refactors ago.
3. **CLI help blocks**: `bash title="$ mycli --help"` blocks compared against live output — this composes beautifully with file 09.
4. **Orphan docs**: pages that nothing links to and that don't appear in `mkdocs.yml`/`SUMMARY.md` nav.
5. **Invariant checks**: "every page has a front-matter `title`", "no page under `reference/` exceeds 400 lines without a TOC".

That tool is `doclink` or `md-graph`, not `markdown-lint-cli`, and it *complements* `markdownlint-cli2` rather than competing (run both in pre-commit).

## If you do build the anchor checker

Parsing must use the exact slug algorithm of the target renderer — GitHub slugs (`lowercase`, strip punctuation, spaces→`-`, dedupe with `-1`), MkDocs (`toc` slugify, `python-markdown`-style), and GitBook differ. Implement GitHub and MkDocs, detect which by repo config (`mkdocs.yml` present → MkDocs), and let `--slug-fn` be pluggable. Build the anchor set per file with `markdown-it-py` tokens (heading levels and inline text), then resolve every `[…](path#anchor)`.

## Tests

Fixtures: duplicate headings (GitHub's `-1` suffixing), heading with inline code/emphasis, anchor with URL-encoding (`#caf%C3%A9`), case differences, links to `README.md` from a subdirectory, absolute `/docs/x.md` links, and a docs site with `use_directory_urls: false`.

## Recommendation

Two-person-week project only if scoped to the anchor/link-graph niche. Do not attempt a general linter; the market is closed.
