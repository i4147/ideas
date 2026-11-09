# 01 — `git-trim` (bulk-safe branch cleanup)

> **Difficulty 1/10** · **Effort ~1 day** · **Tier: warm-up**
> **Prior art: ❌ already built** — PyPI `git-prune-merged` (0.4.6, last release 2022), `git-sweep` (0.1.1, 2012), and `git branch --merged`.
> **Pivot required?** Yes — the naive version is a 40-line shell script. Only the squashed-merge case is still open.

## The problem

`git branch --merged main` misses everything merged via GitHub's **squash** or **rebase** buttons, which is now the default in most orgs. So developers accumulate 80 dead branches, stop trusting the tool, and start deleting by hand. Nobody wants to delete a branch that holds unmerged work.

## What already exists

| Tool | What it does | Why it isn't enough |
|---|---|---|
| `git branch --merged` | lists branches whose tip is an ancestor | blind to squash/rebase merges |
| `git-prune-merged` (PyPI) | prunes merged local+remote branches | last release 2022, no squash detection, no JSON, deletes by default |
| `git-sweep` (PyPI) | lists branches merged into master on origin | Python 2 era, broken on modern git |
| `git-branchless` | advanced branch workflow | whole new mental model, not a cleanup tool |

## The pivot that makes it worth shipping

Three things none of the Python tools do:

1. **Squash-merge detection via patch-id.** A squashed branch's commits never appear as ancestors, but their *diffs* do. Compute `git patch-id --stable` for each branch commit and compare the set against the patch-ids of commits on the mainline since the merge-base. If every branch commit's patch-id is present, the work landed. (Same mechanism as `git cherry`, but `git cherry` compares commit-by-commit and gets confused by multi-commit squashes — compare *sets* and also try the concatenated diff.)
2. **Refuse unsafe deletions.** Never delete a branch that (a) has no upstream and no merged patch-id, (b) is checked out in any worktree (`git worktree list --porcelain`), (c) is the current branch, (d) is in `--keep`, (e) has commits newer than `--stale` days *and* is unmerged.
3. **Machine-readable output + undo.** `--json` for CI, and write every deleted branch's SHA to `.git/trim-log.jsonl` so `git-trim undo` can recreate them with `git branch <name> <sha>`.

## CLI surface

```bash
git-trim scan                     # table: name, last commit, merged?, method, safe?
git-trim scan --json
git-trim delete --dry-run         # default is dry-run; requires --yes to act
git-trim delete --yes --pattern 'feat/*' --keep main,develop,release/*
git-trim prune-remote --yes
git-trim undo                     # recreate from .git/trim-log.jsonl
```

Exit codes: `0` nothing to do, `10` candidates found (for CI/hooks), `1` error.

## How to build it

```
git_trim/
  cli.py          # argparse (stdlib is enough; no click dependency for a 1-day tool)
  gitio.py        # thin subprocess wrapper: run(["git", ...]) -> str; raises GitError
  refs.py         # parse `for-each-ref --format='%(refname:short)%00%(objectname)%00%(upstream)%00%(committerdate:iso-strict)'`
  merges.py       # is_merged_ancestor(), is_merged_patchid(), classify()
  safety.py       # worktree/current/protected checks
  render.py       # rich-free table writer + json
```

Key mechanics:

- `git merge-base main <branch>`; if it equals the branch tip → plain merge.
- Patch-id set: `git log --no-merges -p <mergebase>..main | git patch-id --stable` gives `patchid commit` lines; build a set. Then for the branch: `git log --no-merges -p <mergebase>..<branch> | git patch-id --stable`. Branch is squashed-merged if the branch's set ⊆ mainline's set. Guard: skip branches with <1 commit or merge commits only.
- Cache patch-ids per invocation (a 200-branch repo re-walks history otherwise).
- Never shell-interpolate branch names; pass argv lists.

## Tests

Build throwaway repos in `tmp_path` with `subprocess` (`git init -b main`, `git commit --allow-empty`):

1. plain merge → classified merged
2. squash merge (`git merge --squash` + commit) → classified merged
3. one extra unmerged commit → classified unmerged
4. branch checked out in `git worktree add` → skipped with reason
5. `--dry-run` deletes nothing; `--yes` deletes and `undo` restores the exact SHA

## Pitfalls

- **Shallow clones**: patch-ids unavailable for missing commits → downgrade to "unknown", never "safe to delete".
- **Case-insensitive filesystems**: `Main` vs `main` in `--keep`.
- **Submodules/worktrees** hold refs you can't see from `git branch`.
- Don't trust the remote without `git fetch --prune` first; make it explicit via `prune-remote`.
- Deleting the upstream of another local branch orphans it — warn.

## Definition of done

`scan` on a real 100-branch repo finishes <2 s, correctly identifies a squash-merged branch, refuses every unsafe case, and `undo` round-trips. Publish as `git-trim`, entry point `git-trim` (git subcommand naming works automatically for `git trim`).
