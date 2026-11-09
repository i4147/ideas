# 22 — `shell-history-redactor` (scrub secrets out of shell history)

> **Difficulty 3/10** · **Effort ~3 days** · **Tier: medium**
> **Prior art: ✅ real gap** — PyPI `shellhistory` only *visualises* history; `detect-secrets`/`gitleaks`/`trufflehog` scan files and git diffs, not `~/.bash_history`; `HISTIGNORE` prevents future leaks, not past ones.
> **Pivot required?** No — this is a genuine, high-value, self-contained tool. Best pick in the easy tier.

## The problem

Everyone has done it:

```bash
export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
mysql -u root -pTr0ub4dor3x9 production
curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.…" https://api…
psql "postgres://admin:hunter2@prod-db:5432/app"
```

Then they sync dotfiles to a public repo, paste `history | tail -50` into a ticket, or upload the whole home directory to a backup. The history file is one of the most secret-dense files on a developer machine and almost nobody treats it that way.

## What it must find

| Class | Examples | Confidence |
|---|---|---|
| Known prefixes | `AKIA…`, `ghp_…`, `ghs_…`, `sk_live_…`, `xoxb-…`, `glpat-…`, `npm_…` | very high |
| CLI flags that take secrets | `-p<pw>`, `--password=…`, `--token …`, `--api-key=…`, `mysql -p…`, `psql "postgres://u:p@…"` | very high |
| Inline assignments | `export …KEY=…`, `FOO_SECRET=…`, `DATABASE_URL=scheme://u:p@h` | high |
| Auth headers | `-H "Authorization: Bearer …"`, `--header 'X-Api-Key: …'` | high |
| URLs with credentials | `://user:pass@host` | high |
| PEM blocks | `-----BEGIN … PRIVATE KEY-----` (usually pasted via heredoc — left as-is in history) | high |
| High-entropy tokens | 32+ chars, mixed classes, no dictionary words, entropy > 4.2/char | medium (needs confirmation) |
| Long base64/hex blobs | `openssl enc -aes…-a …` | low |

Two outputs, and this distinction is the whole design: **`scan` lists findings with context; `redact` rewrites the file.** Never silently rewrite on scan.

## The formats you must parse exactly

Rewriting history naively destroys it. Each shell has a format:

- **bash**: plain lines; if `HISTTIMEFORMAT` was set, each command is preceded by `#<epoch>` on its own line. Multi-line commands are split across lines (no continuation marker) — you cannot reliably rejoin; treat each line independently and say so.
- **zsh**: with `EXTENDED_HISTORY`, lines are `: <epoch>:<elapsed>;<command>`; multi-line commands are stored with literal newlines *inside* the entry until the next `: ` record. Parsing must be record-oriented, not line-oriented.
- **fish**: `~/.local/share/fish/fish_history` is YAML-ish: `- cmd: docker login -p x\n  when: 1699…\n  paths:\n    - …`. Nanosecond `when:` values matter.
- **sh/ksh** (rare), **PowerShell** (out of scope; say so).

A parser per shell that yields `Record(start_line, end_line, command_text, raw_span)`, redaction replaces the secret substring in place, and the writer rebuilds the file preserving every other byte (epoch prefixed lines, elapsed values, ordering).

## Redaction mechanics (the part that must be conservative)

```bash
shell-history-redactor scan                        # default: dry run, no writes
shell-history-redactor scan --since 90d --json
shell-history-redactor redact --in-place --backup  # writes ~/.zsh_history.bak-<ts>
shell-history-redactor redact --in-place --yes     # required in non-TTY
shell-history-redactor install-hook                # prints a PROMPT_COMMAND / precmd snippet using HISTIGNORE
```

- Replacement is a stable marker: `hunter2` → `[REDACTED:aws-secret]`, so the *shape* of the command survives (people still need `export AWS_SECRET_ACCESS_KEY=[REDACTED]` to remember what they did).
- **Atomic write**: write to a temp file in the same directory, `os.fsync`, then `os.replace`, preserving mode (0600) and ownership. A half-written history file is data loss.
- **Backup before the first write**, and refuse if the target is a symlink into a git repo without `--force`.
- Fixed-point check: re-scan the rewritten file and assert zero remaining high-confidence findings (log any that persist, e.g. in a different shell's file).
- `--entropy-only-over 40` and `--min-confidence high|medium` to tune; medium findings default to *reported, not redacted*.

## Why not just delete the history?

Because deleting it destroys real value (that scary `iptables` command you'll need again) and people will turn the tool off. Surgical redaction keeps the audit trail of *that you ran something*, minus the secret.

## Tests

Fixture history files with all four formats, including: a zsh multi-line record containing a token on the second line, a bash `#epoch` preamble, a fish entry with `paths:`, CRLF endings, non-UTF-8 (latin-1) bytes, an already-redacted entry (idempotency), and a line that *looks* like a secret but is documentation (`curl -H "Authorization: Bearer <YOUR_TOKEN>"` — the `<…>` placeholder must not be flagged). Golden-file assertions on byte-exact output for the untouched parts.

## Pitfalls

- Do not redact the *command* if it's `history | grep` — that's meta, but over-redaction of harmless lines is the #1 complaint.
- Fish's YAML-ish file uses escaped quotes inside `cmd:` — handle `\n`/`\\` without corrupting.
- Rotated files (`.bash_history.1`), `~/.local/state/…`, and `zsh` `HISTFILE` in a non-default location: discover via `echo $HISTFILE`, then the known fallbacks.
- Root's history and other users' history need sudo; detect and tell the user precisely which files were unreadable.
- Never phone home, never log values to stderr — including in error messages (redact the repr).

## Definition of done

`scan` finds every planted secret across bash/zsh/fish fixtures with zero false positives on placeholders, `redact --in-place` produces a file whose non-secret bytes are identical to the original, and the tool ships a `pre-commit` hook so a dotfiles repo can never publish them again.
