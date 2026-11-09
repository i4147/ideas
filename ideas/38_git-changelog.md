# 38 — `git-changelog` (release notes from commits)

> **Difficulty 3/10** · **Effort ~1 day** · **Tier: warm-up**
> **Prior art: ❌ fully solved, many times** — `git-changelog` (2.11.0, PyPI, Jinja2 templates, conventional-commit aware), `git-cliff` (2.14.2, Rust, extremely configurable), `gitchangelog` (3.0.4), `commitizen` (`cz changelog`), `semantic-release`, `release-please`, `github-changelog-generator`.
> **Pivot required?** Yes — but the remaining gap is editorial, not technical.

## What exists

All of these already do: parse conventional commits, group by type/scope, filter by tag range, resolve PR/issue references from GitHub/GitLab, link authors, template the output, and update `CHANGELOG.md`. `git-changelog` in particular is Python, pure-Python-entry, and Jinja-templated. `git-cliff` is faster and has better defaults.

A new "commits → Markdown" tool is a solved-problem dupe.

## The gap worth attacking: audience, not format

Generated changelogs are written for the people who wrote the commits. Users need something else. The editorial gap:

1. **Breaking-change surfacing with migration notes.** `feat!: drop Python 3.8` in a commit is a line; what users need is "Python 3.9+ required; replace `foo()` with `foo(bar=…)`". Extract `BREAKING CHANGE:` footers, then *look for* the migration note in the PR body (`gh pr view --json body`) before emitting a placeholder.
2. **Noise budgets.** 240 commits → a release note with 40 bullets where 8 matter. Rank by: breaking > security fix > feature > fix > chore; collapse dependency bumps into one line ("12 dependency updates, including 3 major"); drop `chore(deps)` individually.
3. **"How do I upgrade" section.** Diff the public API surface between the two tags using `ast` (top-level names, function signatures, removed/renamed symbols) and list removals/renames explicitly. No existing changelog tool does API diffing, and it's the single most useful thing in a release note.
4. **Empty sections and honesty**: no "Internal Changes: none" padding; if there were no user-facing changes, say exactly that.

## Concrete design

```bash
changelog --from v1.4.0 --to v1.5.0 --audience users|maintainers --format md
changelog --unreleased --check            # CI: fail if a breaking change lacks a migration note
changelog --api-diff v1.4.0..v1.5.0       # removed/renamed public symbols
```

Pipeline: `git log --format` with `%H %aI %an %s %b` → parse conventional commits with a tolerant parser (not everything is conventional; bucket the rest as "Other changes" rather than dropping them) → resolve refs (`#123`) → enrich with PR bodies via `gh` when available and offline-safe when not → API diff via `ast` on `git archive`-extracted trees → rank → render.

`--check` in CI is the hook that keeps it honest: a PR with `feat!:` must add a `MIGRATION.md` entry or a `BREAKING CHANGE:` footer with an instruction.

## Pitfalls

- Squash merges produce one commit whose subject is the PR title; the useful detail is in the PR body. Fetch it or lose half the content.
- Tags sorted by version, not by date (`git for-each-ref --sort=-v:refname`).
- Merge commits and release commits ("chore: release v1.5.0") must be excluded or they appear in their own changelog.
- Author mapping: multiple emails per human; offer `.mailmap`.
- Don't rewrite an existing `CHANGELOG.md` — insert into a marked region (`<!-- changelog:next -->`), or you'll clobber hand-written notes and never be forgiven.

## Recommendation

If a Python tool is wanted, contribute the **API diff** and **audience ranking** as a plugin/fork of `git-changelog` (it's already Jinja-templated and conventional-commit aware). That's maybe 600 lines and it becomes part of a maintained tool instead of a 41st competitor.
