# 56 — `bug-bundle` (a shareable, redacted reproduction package)

> **Difficulty 5/10** · **Effort ~5 days** · **Tier: hard-ish**
> **Prior art: ⚠️ partial** — `python -m traceback`/`faulthandler`, `pytest --tb`, `pip freeze`, `envstamp` (file 03), `sentry`/`bugsnag` (SaaS), `pytest --basetemp` archives, `.zip` of logs by hand, `minibug`/`pysnooper` (debugging, not packaging).
> **Merged from:** `bug-bundle`, "contextual reproducibility bundler", "AI session sanitizer" (partially — see file 65).
> **Pivot required?** Yes — the **review step** and *redaction quality* are the entire product; zipping files is trivial.

## The problem

A user reports "it crashed". You need: the exact command, the traceback, versions, OS, config (redacted), a copy of the input that triggered it, and enough environment to reproduce. Asking for all that takes four round trips, and users paste screenshots.

## Design: capture → preview → redact → export

```bash
bug-bundle create --from-last-failed            # pytest integration: captures the failure
bug-bundle create --cmd "mycli import data.csv" --attach data.csv:first-200-rows
bug-bundle preview ./bug-bundle-2026-11-09.zip  # what's inside, with secrets masked
bug-bundle inspect ./bug-bundle.zip --verify    # is it safe to send?
```

The bundle is a **zip with a manifest**, deliberately boring:

```
bug-bundle-20261109-1432/
  manifest.json        # schema, tool version, created_at, host (hashed), steps, redaction log
  command.txt          # argv, exit code, duration, stdout/stderr tails
  traceback.txt        # last exception chain, with local paths rewritten
  environment.json     # python, os, packages (envstamp schema, see file 03), env var NAMES only
  config/              # discovered config files, redacted
  inputs/              # attached files, size-capped, redacted
  logs/                # tail of relevant logs (last N lines, size-capped)
  redaction-report.md  # every redaction applied + a "review before sharing" checklist
```

`manifest.json` must be self-describing so a maintainer can write a test from it:

```json
{"schema": 1, "tool": "bug-bundle/0.1.0", "created_at": "…",
 "repro": {"steps": [{"cmd": "mycli import data.csv", "cwd": "<repo>", "exit": 1}],
           "expected": "imports 200 rows", "observed": "KeyError: 'date'"},
 "host": {"os": "linux 6.8", "python": "3.12.7", "arch": "x86_64", "hostname_sha256": "…"},
 "redactions": [{"file": "config/app.yaml", "rule": "env-secret", "count": 2},
                {"file": "environment.json", "rule": "env-values-dropped", "count": 41}]}
```

## Redaction: the part that has to be good

Layered, and every layer logs what it did:

1. **Path normalisation**: replace `$HOME` → `~`, repo root → `<repo>`, temp dirs → `<tmp>`, and usernames.
2. **Env vars**: names only, plus values for an allowlist (`TZ`, `LANG`, `PYTHONHASHSEED`, `PYTHONPATH` truncated).
3. **Known secret patterns** (reuse file 22's detector): cloud keys, `Bearer` tokens, PEM blocks, URLs with credentials, `*_SECRET`/`*_TOKEN` keys in YAML/TOML/JSON/`.env`.
4. **High-entropy strings** in text files: length ≥ 32, charset mixed, entropy > 4.2 → mask with `[REDACTED:high-entropy:<n chars>]`.
5. **User data**: emails (mask local part), IPs (mask last octet unless `--keep-ips`), absolute paths outside the repo, phone-number-like sequences.
6. **Binary attachments**: never include by default; if included, hash + size only, with `--attach-binary --yes`.

**`preview` is mandatory before `export`** in interactive use: it prints the file list, sizes, and a redaction summary, and requires confirmation. `--yes` skips it (CI), but `manifest.json` records `previewed: false` so a maintainer knows to be careful.

## Zip hygiene

- Store **uncompressed** small text files (better for grepping later) but compress large logs; cap total at `--max-size 5MB` (default) with a clear list of what was dropped.
- Zip with explicit, sanitised member names — never `os.path.join(root, file)` from a walked tree (path traversal and symlink escapes: reject `..`, absolute paths, and symlinks; see file 57's rules).
- Deterministic zip metadata (fixed timestamps) so two bundles of the same state compare equal — useful for dedupe.
- Set no archive password (encryption here is a footgun, not protection) and say so explicitly: **a bundle is not a secure container; review it**.

## pytest and CLI integration

- `pytest --bug-bundle` plugin: on failure, capture the failing test's nodeid, its `--basetemp` contents (capped), the captured stdout/stderr, the traceback with locals **only if `--show-locals`** (locals are a privacy hazard: default off, and warn).
- `bug-bundle create --cmd "…"`: run it (with confirmation), capture everything, and add `--attach`.
- Exit codes: `0` created, `2` too large / redaction failed (refuse to export rather than leak).

## Tests

Golden bundles: a fixture project that raises a `KeyError` with a config containing fake secrets and an env var named `DATABASE_URL`. Assert: no secret value appears anywhere in the zip (grep the whole archive), paths are normalised, `manifest.json` validates, `preview` output matches, deterministic bytes across two runs, and a symlink/`..` attachment is rejected. Fuzz the redactor with 100 random high-entropy strings (assert all masked).

## Pitfalls

- Never upload. No telemetry, no "attach to issue" without explicit user action.
- Tracebacks contain source **lines** (fine) and sometimes local variable values (not fine) — strip the latter by default.
- `manifest.json` itself can leak: run the redactor over it too.
- Exception messages frequently embed secrets (`Invalid token sk_live_…`): apply the secret patterns to `traceback.txt`, not only to config files.
- Bundles age: include a `created_at` and the tool version, and keep the schema versioned so old bundles stay inspectable.

## Definition of done

A user runs one command, gets a <2 MB zip, `preview` shows zero unmasked secrets on a hostile fixture repo, and a maintainer can reproduce the bug from `manifest.json` + `inputs/` without a follow-up question.
