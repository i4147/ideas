# 76 — `git-rewrite-history` (safe bulk history rewriting)

> **Difficulty 6/10** · **Effort ~6 days · most of it spent telling the user not to** · **Tier: hard**
> **Prior art: ❌ name taken and solved** — PyPI `git-rewrite-history` 0.1.3 (bulk-rewrite messages/authors/emails/dates), `git-filter-repo` (the canonical tool, Python, recommended by the git project itself), `git rebase -i`, `git filter-branch` (deprecated for good reasons), `BFG Repo-Cleaner` (Java), `git-sed`, `newren`'s guidance, GitHub's own "sensitive data removal" docs.
> **Verdict: do not build.** `git-filter-repo` is a single Python file, fast, maintained, and safer than anything a weekend produces.

## Why this is dangerous, specifically

History rewriting is *destructive, irreversible without a backup, and contagious*: every clone, every open PR, every CI cache, and every fork keeps the old hashes. Rewriting `main` invalidates:
- all open PRs (they rebase onto a history that no longer exists → duplicated commits, phantom diffs),
- CI caches keyed by SHA,
- signed commits (signatures break when the parent changes — non-negotiable for many projects),
- release tags pointing at old commits (they must be re-pointed, and published artifacts can't be re-signed retroactively),
- `blame` attribution and any `git notes`.

`git-filter-repo` documents all of this in a 400-line `--help` and still gets misfired. A less-tested reimplementation is a data-loss incident waiting for a first-time user.

## What `git-filter-repo` already covers

| Need | Invocation |
|---|---|
| remove a file/dir from all history | `--path src/secret.py --invert-paths` |
| strip a large blob | `--strip-blobs-bigger-than 10M` |
| replace text everywhere | `--replace-text expressions.txt` (with regex support) |
| rename/move paths | `--path-rename old/:new/` |
| rewrite author/email | `--mailmap` (proper `.mailmap` semantics, not sed) |
| extract a subdirectory into its own repo | `--subdirectory-filter` |
| only recent history | `--refs main~50..main` |
| prune empty commits | `--prune-empty always` |

Plus `--dry-run`, `--analyze`, and a callback API (`--commit-callback`, `--blob-callback`) for anything exotic. It also refuses to run on a non-fresh clone unless forced, which is exactly the guardrail a hand-rolled tool omits.

## The only defensible artifact: a *planner*, not a rewriter

If the group wants to work in this space, build the safety layer around the existing tool — that's genuinely missing:

```bash
rewrite-plan --remove path:secrets/ --bigger-than 5M     # print the exact planned changes
rewrite-plan --analyze                                    # what will break: PRs, tags, signatures, caches
```

`--analyze` output:

```
PLAN  rewrite main (2,412 commits) to drop 3 paths and 41 large blobs
CONSEQUENCES
  14 open PRs will need rebasing (list, with authors to notify)
  6 tags point into rewritten history (must be re-created; checksums on PyPI will not match)
  182 commits are GPG-signed → signatures will be invalid
  CI caches keyed by SHA: 41 entries invalidated (GitHub Actions cache API)
  contributors' clones: 23 distinct authors in rewritten range (mailmap needed)
  forks: 4 forks reference these hashes (they will diverge silently)
SAFE PROCEDURE (generated, reviewed, then executed by you)
  1. git clone --mirror … rewritten.git        # never rewrite in place
  2. git filter-repo --path secrets/ --invert-paths --force
  3. verify: git log --oneline | wc -l ; git cat-file --batch-check
  4. rotate every secret that was in the blobs (a rewrite does not un-leak)
  5. force-push with --force-with-lease, notify the 23 authors, re-create 6 tags
ROLLBACK  original mirror preserved at ./backup-20261109.git
```

The "rotate every secret" line is the one people miss: removing a token from history does **not** un-leak it. A tool that says so loudly is more valuable than a faster rewriter.

## If it is built anyway (non-negotiables)

1. **Never operate in place.** Always clone into a new working directory; refuse if `--in-place` and the tree is not a fresh `--mirror` clone.
2. **Refuse signed commits and published tags** unless `--i-know` is given twice, listing what breaks.
3. **`--dry-run` first, always**, printing before/after commit counts, object counts, and the exact command it will run.
4. **Delegate the rewriting** to `git-filter-repo` via `subprocess` (fail with an install hint) rather than reimplementing tree surgery with `pygit2`/`dulwich`. Writing a correct fast-export/import stream filter is a multi-week project on its own.
5. **Auto-backup**: create a mirror clone before any operation, print the restore command, and keep it for `--keep-backup 30d`.
6. **Post-checks**: `git fsck --full`, expected commit count, tag map, and a summary of authors preserved.

## Tests

Fixture repos: a repo with 3 tags, 2 signed commits (fixtures with a test GPG key), an open PR simulation (a branch with a merge base), a `secrets/` dir, and a 5 MB blob. Assert `--analyze` reports the right consequences, `--dry-run` changes nothing (hash the object store before/after), the backup exists, and a refused operation returns exit 3 with the reason. Never test against a real remote.

## Recommendation

Do not spend a project slot on this. If someone is interested, the *analyzer* (what will break when I rewrite) is a genuinely useful two-week tool with no destructive code in it — and it composes with `git-filter-repo` instead of competing.
