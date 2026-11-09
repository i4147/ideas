# 30 — `time-tracker` (CLI time tracking)

> **Difficulty 3/10** · **Effort ~4 days to be worth using** · **Tier: medium**
> **Prior art: ❌ crowded** — `watson` (TailorDev, Python, the canonical CLI timer), `timetrace` (Go), `timewarrior` (C++), `taskwarrior` + hooks, `khal`-adjacent tooling, `Toggl Track` CLI, plus `clockify-cli`.
> **Pivot required?** Yes, and it must be sharper than "sync with Toggl".

## The problem

Solo developers and students need to know where the week went, and every existing tool asks for more discipline than the user has: you must remember to *start* the timer, then remember to *stop* it, then remember to fix the 6-hour entry you forgot to stop.

## What exists (and is good)

`watson` is the closest: `watson start project +tag`, `watson stop`, `watson report`, JSON frames on disk, `watson sync` to a remote. `timewarrior` is more powerful and more rigid. `timetrace` is a single Go binary with a nice TUI. Any of these is a better choice than a new tool for personal use.

## The only pivots that aren't busywork

1. **Infer instead of asking.** Read existing signals you already produce and *propose* entries: git commit timestamps across repos, shell history timestamps (zsh `EXTENDED_HISTORY` gives epochs — see file 22), file mtimes under project dirs, and terminal window titles where available. Then `tt review` shows proposed blocks and you `tt confirm` — 30 seconds a day instead of 12 start/stop actions. No competitor does inference well, because they're all timer-first.
2. **Forget-proof by construction.** A timer that is still running after 4 hours is a bug, not a feature: auto-split at gaps (a 3 h gap in commits/fd activity closes the block), and never record an open-ended block without a `?` marker that `report` flags.
3. **Weekly budget in the terminal.** `tt budget --week 20h --project thesis` — a bar that tells you on Thursday whether you're on track. `watson` reports only after the fact.

## Design

Local-first, single SQLite file at `$XDG_DATA_HOME/tt/tt.db`:

```sql
CREATE TABLE block(
  id INTEGER PRIMARY KEY, project TEXT NOT NULL, tags TEXT, note TEXT,
  start_utc TEXT NOT NULL, end_utc TEXT,        -- NULL = running
  source TEXT NOT NULL,                          -- manual|git|shell|mtime
  confidence REAL, confirmed INTEGER DEFAULT 0,
  CHECK (end_utc IS NULL OR end_utc > start_utc));
```

Store UTC, display local. One open block per project max (enforced by a partial unique index); overlapping manual blocks require `--force` and are reported by `tt doctor`.

```bash
tt start thesis +writing -m "chapter 3"
tt stop
tt review                             # propose blocks from git/shell for today
tt confirm --all
tt report --week --format table|json|markdown|toggl-csv
tt budget --week 20h --project thesis
tt doctor                             # overlaps, open blocks > 12h, future timestamps, clock jumps
tt export --since 2026-01-01 > backup.json
```

## Inference details (the interesting engineering)

- **git**: for each repo under `--roots`, `git log --since --pretty=%aI%x00%ae` (author email filter), cluster commits with gaps > `--gap 45m` into candidate blocks. Attribute the repo to a project via a mapping file (`projects.toml`: path glob → project).
- **shell**: zsh extended history gives per-command epochs; cluster the same way, but weight by *command category* (skip `ls`, `cd`, `cat` — they don't indicate work).
- **mtimes**: `find <dir> -newermt` in 10-minute buckets; low weight, used only to extend a block that git already proposed.
- Merge candidate sources with a union-find over time intervals, cap block length at 3 h for unconfirmed blocks, and assign `confidence` = share of the block covered by evidence.
- **Privacy**: inference never leaves the machine, is off for repos/dirs not listed in the config, and `--no-infer` disables it entirely.

## Tests

Freeze time (`freezegun` or inject a clock) and drive a fake `git` repo with backdated commits. Assertions: a 45-minute gap splits into two blocks, an overnight open block is auto-closed at the last evidence + gap, `report --week` sums exactly (no off-by-one at tz boundaries), JSON export round-trips into a fresh DB, and DST transition nights don't produce a negative duration.

## Pitfalls

- Timezones and DST: store UTC, and on display group by *local* day — a block crossing midnight belongs to the day it started (document it, offer `--split-midnight`).
- Clock changes (NTP jumps, laptop sleep) create negative durations; `doctor` must catch and repair them.
- Never require a running daemon; the DB must be safe under concurrent `start` from two shells (SQLite `BEGIN IMMEDIATE`).
- Toggl CSV export format is undocumented and changes; ship it as `--format toggl` with a version note, not as the core.
- Sync to cloud services is a *separate* project (file 44) — don't bolt it on.

## Definition of done

After one week of real use, `tt review` reconstructs 80 % of the day's work from git + shell with under a minute of confirmation, and `report --week` is accurate to the minute.
