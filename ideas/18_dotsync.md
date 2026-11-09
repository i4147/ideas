# 18 — `dotsync` (dotfiles: drift detection, then safe apply)

> **Difficulty 3/10** · **Effort ~3 days** · **Tier: warm-up**
> **Prior art: ⚠️ partial** — `chezmoi` (Go, the current best), GNU `stow`, `yadm` (shell over git), `dotbot`, `rcm`, `supervisord`-style ad-hoc git repos.
> **Pivot required?** Yes — chezmoi already won the "manage everything" space. Win the **audit** space.

## The problem

Your dotfiles repo says `nvim`, the machine says something else because you edited it at 2 a.m. three weeks ago and forgot. `chezmoi diff` solves this *if* you migrated to chezmoi (templates, encryption, a 40 MB Go binary, a new mental model). Many people keep a plain git repo of symlinked or copied files — and for those, there's no good "show me the drift, including the parts I never manage" tool.

## What exists

| Tool | Gap |
|---|---|
| `chezmoi` | full manager; requires adopting its source-state model |
| `stow` | creates symlinks; no drift report, no partial adopt |
| `yadm` | git wrapper with encryption; `yadm diff` assumes everything is tracked |
| `dotbot` | install-time only |

## The pivot: an auditor that works on *any* dotfile setup

```bash
dotsync scan                     # classify every file in ~ that is managed/unmanaged/conflicting
dotsync drift                    # managed files whose content or link target differs from the repo
dotsync adopt ~/.config/kitty --as copied   # start managing something new (adds to repo, keeps backup)
dotsync apply --only ~/.config/kitty        # write one thing, with backup, not the whole world
dotsync secrets                  # files that look like they hold tokens (config half of file 32)
```

Classification is the core insight. For each candidate path under a configurable root (`~`, but skip `~/.cache`, `~/.local/share`, browser profiles, and anything > 5 MB):

| State | Meaning |
|---|---|
| `linked` | symlink whose target is inside the repo and matches → healthy |
| `copied` + `identical` | real file, content hash equals repo copy → healthy |
| `copied` + `drifted` | real file differs → **the interesting case** |
| `templated` | repo has `.tmpl` and rendered output matches → healthy (chezmoi-style) |
| `untracked-candidate` | looks like a dotfile, isn't managed → notify only |
| `conflict` | symlink points outside the repo, or repo file present but target missing |

Drift display is a real unified diff (`difflib.unified_diff`) with `--word-diff` and secret masking (any line matching `(?i)(token|secret|key|pass)`, or a value with entropy > 4.0, prints `***`).

## Build

```
dotsync/
  map.py       # repo manifest (.dotsync.toml) -> expected states
  compare.py   # hash, symlink target, template render
  diffx.py     # unified/word diff with redaction
  apply.py     # atomic write (tmp + os.replace), backup to .dotsync/backups/<ts>/, permission preservation
  cli.py
```

Manifest example:

```toml
[dotfiles]
"bash/.bashrc"        = { target = "~/.bashrc", mode = "symlink" }
"git/.gitconfig"      = { target = "~/.gitconfig", mode = "template" }
"nvim/"               = { target = "~/.config/nvim", mode = "copy" }
```

`mode = "copy"` is deliberately supported — some tools rewrite their own configs (VS Code, some TUIs), and symlinking those causes real bugs.

## Tests

`tmp_path` HOME: symlink pointing at the repo, symlink pointing elsewhere (conflict), copy with drift, template with `{{ .hostname }}`, broken symlink, a file with mode 0600 that must stay 0600 after apply, a directory of 500 files (performance), and an interrupted apply (backup must allow recovery).

## Pitfalls

- Never write through a symlink into the repo when the user expects a copy — resolve and check.
- Backups before every write, including when `--force`.
- Preserve ownership/mode/ACL where possible (`shutil.copystat`, `os.chmod` after write); SSH keys with wrong modes break logins silently.
- Skip binary/large files in diffs; never print an SSH private key to a terminal — mask `-----BEGIN` blocks unconditionally.
- If `$HOME` is a symlink (macOS case), normalise with `Path.resolve()`.

## Definition of done

`scan` on a messy real machine classifies 200 config paths correctly, `drift` finds the three files you actually edited, and `apply --only X` writes exactly one file with a restore path.
