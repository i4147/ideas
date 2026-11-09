# 16 — `pre-commit-hooks-manager` (manage hooks across many repos)

> **Difficulty 3/10** · **Effort ~2 days** · **Tier: warm-up**
> **Prior art: ⚠️ mostly solved** — `pre-commit autoupdate` (built in), `pre-commit.ci` autoupdate PRs, `pre-commit-mirror-maker`, `renovate` with a `pre-commit` manager.
> **Pivot required?** Yes, and narrow: **the multi-repo local fleet**, not one repo's hooks.

## The problem

`pre-commit autoupdate` solves "bump the revs in this repo". What it doesn't solve: you maintain 12 repos (or a lab full of student projects), and you want *the same* hook set, at the *same* versions, everywhere — with drift reporting and a one-command sync. `pre-commit.ci` does this only for repos on GitHub with the app installed, and only for updates, not for unifying configs.

## The narrow pivot

```bash
hookfleet scan ~/code                 # which repos have pre-commit, which hooks, which revs
hookfleet drift                       # repos whose .pre-commit-config.yaml differs from the shared baseline
hookfleet sync --all --yes            # write the baseline into every repo, `pre-commit autoupdate` each
hookfleet pin --hook ruff --rev v0.7.4   # pin one hook everywhere (security/incident response)
hookfleet report --format markdown    # a table for the team wiki
```

Behaviour that makes it more than a `for` loop:

- **Baseline resolution**: `.pre-commit-config.yaml` in the current repo, or a shared file (`--baseline https://…/hooks.yaml`), or `hookfleet.toml` with per-hook policy (`required`, `forbidden`, `allowed-revs`).
- **Merge-aware sync**: hooks present locally but absent from the baseline are *reported*, not deleted, unless `--prune`. Repo-specific hooks (a local `id: my-script`) are always preserved by matching `repo: local`.
- **Ordering/canonicalisation**: hook order affects diagnostics; sort by `(repo, id)` and write YAML with `ruamel.yaml` round-trip to keep comments.
- **Dry-run by default**, and `sync` must run `pre-commit autoupdate` *after* writing, then `pre-commit install-hooks` to warm the environment — otherwise the next commit fails and everyone blames you.
- **Vendored repos**: skip if `.pre-commit-config.yaml` is a symlink into a monorepo, unless `--follow`.

## Build

```
hookfleet/
  discover.py   # find .pre-commit-config.yaml under a root (skip node_modules/.venv, depth limit)
  parse.py      # yaml load + normalise (repo, rev, hooks[ids], args)
  policy.py     # baseline diff -> Findings (missing, extra, drifted, forbidden, stale rev)
  sync.py       # ruamel.yaml round-trip write + subprocess `pre-commit autoupdate`
  cli.py
```

Deps: `ruamel.yaml` (round-trip is the point), optional `rich`.

## Tests

Fixture repos with: comments that must survive a sync, a `repo: local` hook, a hook with `additional_dependencies`, a YAML anchor, a repo with a hook list in a different order (must not count as drift), and a missing `pre-commit` binary (must degrade to "config updated, autoupdate skipped").

## Pitfalls

- Editing YAML with `pyyaml` destroys comments and ordering — users will reject that. Use round-trip mode.
- `autoupdate` needs network; make it opt-out and report exactly which repos failed.
- Rev pinning to tags that don't exist yet silently breaks commits; verify with `git ls-remote` before writing.
- In CI, `pre-commit` caches at `~/.cache/pre-commit` — don't wipe it.
- The name is long and hyphenated; `hookfleet` (free on PyPI) is the better distribution name.

## Definition of done

`drift` across 12 real repos in <5 s, one `sync` unifies them without touching local hooks or comments, and each repo still commits cleanly afterwards.
