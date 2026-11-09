# 07 — `standup` (what did I actually do, across all my repos)

> **Difficulty 2/10** · **Effort ~1 day** · **Tier: warm-up**
> **Prior art: ❌ already built** — PyPI `standup` 0.1.2 (2014), `git-standup` (shell), `git log --author`, GitHub's activity feed.
> **Pivot required?** Yes — the 2014 package scraped one repo; the modern gap is *many repos, offline, with blockers*.

## The problem

Daily standup takes 10 minutes of archaeology: `git log` in six repos, remembering what was blocked, and re-reading yesterday's Slack message. The information is entirely local and already structured — nobody assembles it.

## What exists

`standup` (PyPI, 2014) does a single-repo commit dump. `git-standup` is a shell script that walks subdirectories and prints commits (good, but no PR/blocker context, no markdown, no dedup across worktrees). Both stop at "here are commit subjects".

## The pivot worth building

1. **Multi-repo discovery** by walking a root and de-duplicating worktrees of the same repo (`.git` file vs directory, same `git rev-parse --git-common-dir`).
2. **Session framing**: `--since 9am`, `--since yesterday 18:00`, `--window 24h`. "Yesterday" must respect the user's tz and *working hours*, not a naive 24 h subtraction.
3. **Blocker extraction** from commit trailers (`Blocked-by:`), merge-request labels (`blocked`, `waiting-for-review` via `gh` when available), and WIP commits.
4. **Output that is pasted, not edited**: markdown with three sections — *Done / In progress / Blocked* — each item a commit subject with a repo prefix, and PR numbers linked when the remote is parseable.

```
$ standup --since yesterday --root ~/code
## Done
- shop-api: feat(cart): persist line items (#412)
## In progress
- shop-api: wip: tax calculation  [3 commits, uncommitted changes]
## Blocked
- infra: chore: bump terraform  [Blocked-by: #88 waiting on VPC quota]
```

## Build notes

```
standup/
  discover.py   # find repos, skip node_modules/.venv/build, depth limit, .standupignore
  gitlog.py     # `git log --pretty=%H%x00%an%x00%ae%x00%aI%x00%s --author=<me>` per repo
  me.py         # identity from user.email + user.name, plus --author override
  blocked.py    # trailers + gh pr list --label blocked (optional, skipped if no gh)
  render.py     # markdown | text | json
```

Use `--author` matching on email, not name (same person, three spellings). Exclude merge commits. Skip commits already reported since the last run with a tiny state file (`.standup-state.json`) so a 9:05 and 9:30 run don't duplicate.

## Tests

Fixture repos created in `tmp_path` with backdated commits (`GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE`), including: a worktree duplicate, a repo with a non-UTF8 commit subject, commits at the exact window boundary, an author with two emails.

## Pitfalls

- Timezones: `%aI` is ISO with offset — compare in UTC but *display* in local tz.
- Don't include other people's commits; don't leak private repo names into a public paste without `--redact-paths`.
- Empty output is a valid answer; don't print fake "no commits today — great job!" filler.

## Definition of done

Under 1 s over 20 repos, output pasted into Slack unedited.
