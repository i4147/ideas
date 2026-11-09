# 75 — `config-diff` (why does this machine behave differently?)

> **Difficulty 6/10** · **Effort ~7 days** · **Tier: hard**
> **Prior art: ✅ real gap** — `diff` on dotfiles, `chezmoi diff` (file 18), `dotsync`-style tools, `mackup`, `git config --list` diffing by hand, `brew bundle check` (macOS), `nix`/`home-manager` (if you already use them), `mise` (`mise doctor`), `direnv status`. No tool explains **semantic** differences in tool configuration.
> **Pivot required?** No — but the scope must be honest, because "explain the impact in plain English" needs a knowledge base.

## The problem

Two machines, same repo, different behaviour: one runs the tests green, the other has 3 failures. The cause is buried in `~/.config/git/config`, `~/.config/uv/uv.toml`, `~/.pytest.ini`, a `~/.config/ruff/ruff.toml` overriding the project one, `pip.conf`, a stray `sitecustomize.py`, or `PYTHONHASHSEED` in `.zshrc`. `diff -r ~/.config` gives 400 lines of noise; nothing says *this line changes behaviour*.

## Design

```
$ config-diff machine-a machine-b --tool git,uv,pytest,ruff
GIT  (config precedence: system → global → repo)
  DIFFERS   user.signingkey       absent → 4A2B…
            effect: commits signed on B only → CI signature check may fail
  DIFFERS   core.autocrlf         false → input
            effect: line endings normalised on B; diffs between machines will churn CRLF
UV
  DIFFERS   [tool.uv] index-url    https://pypi.org/simple → https://internal/simple
            effect: B resolves from a private index; a package absent there fails only on B
PYTEST
  DIFFERS   addopts                "-q" → "-q --strict-markers -p no:cacheprovider"
            effect: B rejects unknown markers; plugin disabled on B
RUFF
  IGNORED   ~/.config/ruff/ruff.toml exists on B but the project pyproject has [tool.ruff]
            effect: none (project config wins) — listed so you don't chase it
SHELL
  DIFFERS   PYTHONHASHSEED         unset → 0
            effect: B disables hash randomisation → set/dict ordering becomes deterministic; can mask bugs
SUMMARY  4 behavioural differences, 1 benign shadowed config
```

## How to make "effect" non-hand-wavy

This is the honest engineering problem: mapping a config key to its consequence requires curated knowledge. Do it in layers, and mark provenance:

1. **Precedence resolution** (deterministic, high value): for git, system → global → repo (`/etc/gitconfig`, `~/.gitconfig`, `~/.config/git/config`, repo `.git/config`); for ruff/mypy/pytest/uv, project config beats user config — so a user-level config that's *shadowed* is noise, and reporting it as "no effect" is itself valuable.
2. **Curated effect table** (`effects.yaml` shipped with the tool): ~120 entries for the top keys, each with `key`, `values`, `effect` (one sentence), `severity` (behavioural | cosmetic | none), and a source link. This is the product's real content — a small, reviewable knowledge base, not AI.
3. **Environment-variable effects**: `PYTHONHASHSEED`, `PYTHONPATH`, `TZ`, `LANG`/`LC_ALL`, `NO_COLOR`, `PIP_*`, `GIT_*`, `HTTP_PROXY` — a known list with precise consequences.
4. **Config-content sniffing** (deterministic, catches the "unknown key" case): flag a key present on one side only, and diff the *values* structurally; for unknown keys say "effect unknown, review" rather than inventing a sentence.
5. **Optional LLM** (`--explain`): feed only the *diffs and their doc strings* to a local model to phrase a paragraph; refuse when a key isn't in the effect table (so it can't invent). Clearly label the output as phrasing.

## Sources of config

`--tool` names with a per-tool matrix of paths and precedence: git, ssh, pip, uv, poetry, pytest, ruff, mypy, black, coverage, docker (`~/.docker/config.json`, `daemon.json`), shell (`.bashrc`, `.zshrc`, `config.fish` — but extract only `export`/`set -x` lines, not the whole file), editor (`~/.vimrc`, `nvim/init.lua` — keys only, not every line), `systemd` user units (enabled state), `/etc/environment`, `sysctl` keys that matter (inotify limits, file descriptors).

**Two modes**: (a) local — compare two snapshot bundles (`config-diff capture -o a.json`, then `config-diff compare a.json b.json`), and (b) remote — `config-diff compare --ssh user@host` (runs `config-diff capture --json` remotely, which requires the tool there; refuse otherwise, don't scrape).

Redaction: reuse file 04/22 detectors — SSH private keys, tokens in `pip.conf`/`.npmrc`/`.netrc`, proxy credentials. Values of secret-looking keys are replaced with `SET (redacted)` and compared *for presence only*.

## Tests

Fixture `$HOME` trees (two directories) with: a git config differing in precedence-shadowed keys, a team-level `.gitconfig` includeIf `gitdir:` block (must resolve), a ruff user config shadowed by a project config (must report "no effect"), a `PYTHONHASHSEED=0` in `.zshrc`, an SSH key with 0600 vs 0644 (a *permission* difference that breaks logins — compare modes too), CRLF config files, and a `/etc/environment` fixture path override. Assert the effect text and severity, and that a secret value never appears in output (grep).

## Pitfalls

- Precedence differs per tool and version — version the effect table and print it (`effects v3`).
- `includeIf`/`include.path` in git configs mean the effective config is not the file you read: resolve includes (with a depth cap) or the whole report is wrong.
- Shell rc files are programs: parse only assignments with `bashlex`, and never claim to understand conditionals — report "conditional, unknown".
- Don't send config anywhere by default; `capture` must be scrubbable and reviewable before sharing (see file 56).
- A difference that doesn't affect the failing symptom is still useful, but rank by severity and keep the report ≤30 lines.

## Definition of done

Given two captured machines, the tool names the actual cause of a "works on A, fails on B" bug in the fixture suite, marks shadowed config as inert, and leaks no secret values.
