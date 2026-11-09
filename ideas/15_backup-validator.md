# 15 — `backup-validator` (verify that a backup can actually be restored)

> **Difficulty 3/10** · **Effort ~2 days (as a thin orchestrator)** · **Tier: warm-up**
> **Prior art: ❌ solved inside every serious backup tool** — `restic check --read-data`, `borg check --verify-data`, `duplicity verify`, `rsync --checksum --dry-run`, `zfs scrub`, `zbackup`.
> **Pivot required?** Yes — and it's a good one: **restore-drill orchestration with a pass/fail report**, not checksumming.

## The problem

"Backups are useless if they can't be restored" is correct, and every backup tool already verifies its own repository: restic `check --read-data` recomputes every pack file's hash, borg `check --verify-data` does the same. So a from-scratch checksum comparison would be strictly worse than what users already have.

The unsolved half is the **drill**: proving a *specific file* comes back intact, automatically, on a schedule, with evidence. People run `restic check` (which proves the repo isn't corrupt) and never run `restic restore` (which proves the recovery works and takes an hour).

## The pivot: `backup-validator` = restore drills as code

```toml
# backup-validator.toml
[[source]]
name    = "laptop-home"
kind    = "restic"
repo    = "s3:https://…/laptop"
password_file = "~/.config/restic/laptop.pass"

[[drill]]
name  = "docs-restore"
from  = "laptop-home"
paths = ["/home/ana/Documents"]
sample = { files = 25, strategy = "largest+random" }   # don't restore 200 GB
to    = "/tmp/drill-{date}"
verify = ["exists", "sha256", "mtime", "path"]
max_minutes = 30
```

```bash
backup-validator drill --config backup-validator.toml      # run all drills
backup-validator drill docs-restore --json                 # machine-readable result
backup-validator inventory --from laptop-home             # what's in there (file count/bytes)
backup-validator schedule --cron "0 3 * * 0" --notify slack://…
```

A drill report is evidence you can attach to a compliance doc: source snapshot ID, files restored, bytes, per-file sha256 match, wall time, and a link to the log. Output as JSON + a signed (ed25519, `--sign`) manifest so a third party can check it later.

**Supported engines (adapters, thin):** restic (`restic restore --include`, `--verify-data` available as `--deep`), borg (`borg extract`), rsync/`rclone` (compare by hash), plain directory copies, `tar` archives, and a generic `command` adapter (`backup-validator run` = a user-supplied restore command + a verify hook). The adapter interface is ~40 lines each, which is the right size for this tool.

## Build

```
backup_validator/
  adapters/{restic,borg,rclone,tar,dir,command}.py   # inventory(), restore(paths, dest)
  sample.py     # choose files: largest 10 + random 15 + all files <1MB up to a cap
  verify.py     # sha256, exists, mtime tolerance, path normalisation
  report.py     # json + markdown + signed manifest
  cli.py
```

Sampling matters: restoring 25 well-chosen files (10 largest, 10 random, 5 newest) catches ~all real corruption in minutes instead of hours. Verify by comparing to the *live* source when available (`--compare-live`), else to a stored inventory hash (`.backup-validator/inventory/<source>.json`).

## Tests

Fake adapters that copy from a `tmp_path` tree; drills for: file missing in restore, size mismatch, mtime drift beyond tolerance, permission-denied, restore timeout (kill the subprocess group), and a repository password failure. Also a test that verifies `--sign` output against a known public key.

## Pitfalls

- Never store repository passwords in the config — reference `password_file`/`password_command` (restic convention) and check the file's permissions are `0600`.
- Restores are I/O heavy: enforce `max_minutes`, `nice`/`ionice` by default, and never run two drills against the same repo concurrently.
- mtime is not preserved by some engines/formats (tar without `-p`, rclone remotes) — make it a per-drill toggle, not a default failure.
- Clean up `/tmp/drill-*` even on failure (`try/finally`), or the drill becomes the disk problem.
- Don't claim "backup verified" when only a sample was restored — say "25 of 1,204,118 files verified (largest + random sample)".

## Definition of done

A weekly cron drill restores a sample from a real restic repo, produces a signed JSON report in <15 min, and fails loudly (exit 1 + notification) if any sampled file mismatches.
