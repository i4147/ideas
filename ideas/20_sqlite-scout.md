# 20 — `sqlite-scout` (find and triage stray SQLite databases)

> **Difficulty 3/10** · **Effort ~3 days** · **Tier: easy→medium**
> **Prior art: ✅ real gap** — no PyPI `sqlite-scout`/`sqlitescout`; closest are `sqlite3 .dump`, `datasette`, `db-browser` (GUI), and `find -name '*.db' -exec du`. Nothing triages a folder of mystery databases.
> **Pivot required?** No. Build it, keep it read-only.

## The problem

Every project directory has them: `app.db`, `test.db`, `db.sqlite3`, `cache.db`, `foo.db-wal`, `foo.db-shm`, `foo.db-journal`, `local.db.bak`, and three copies from different branches. You don't remember which one has your data. Opening them one by one in `sqlite3` to run `.tables` and squint at row counts is exactly the kind of chore a tool should own.

Bonus horror: some of those "databases" are 0 bytes, some are corrupt, and some are other formats with `.db` extensions (SQLite has a 16-byte magic header — easy to check, rarely checked).

## What it should print

```
$ sqlite-scout ~/code --since 30d
FOUND 14 files (7 valid SQLite, 2 WAL-only, 3 empty, 2 not-SQLite)
┌──────────────────────────────┬────────┬───────┬────────────┬──────────┬───────────────┐
│ path                         │ size   │ table │ rows       │ modified │ notes         │
├──────────────────────────────┼────────┼───────┼────────────┼──────────┼───────────────┤
│ shop/local.db                │ 41.2MB │   12  │ 184,201    │ 2d ago   │ ← largest     │
│ shop/tests/fixtures/t.db     │ 12.0KB │    3  │ 41         │ 91d ago  │ dup of #7     │
│ old/app.db                   │ 0B     │    0  │ –          │ 4mo ago  │ empty         │
│ data/export.db               │ 2.1MB  │    0  │ –          │ 1mo ago  │ NOT sqlite    │
└──────────────────────────────┴────────┴───────┴────────────┴──────────┴───────────────┘
DUPLICATES: local.db ≈ backup/local.db.copy (12/12 tables, same schema+row counts)
```

Details worth capturing per database: `PRAGMA user_version`, `application_id`, page size, `journal_mode`, encoding, `freelist_count` (bloat indicator), table names + row counts (via `SELECT COUNT(*)` **only for tables < 5 M rows** or with `--fast` using `dbstat`), schema hash (normalised `sqlite_master` SQL), and first/last timestamps if a `created_at`/`updated_at` column exists.

## Safety rules (the reason a tool beats a script)

1. **Read-only open.** Use URI mode: `sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)`. Never write, never create `-wal`/`-shm`.
2. **Copy-before-open for WAL files**: a database with a live `-wal` cannot be read correctly read-only without recovery; either skip with a warning or copy all three files to a temp dir and open the copy (`--copy-wal`).
3. **Never open non-SQLite**: check the 16-byte header `SQLite format 3\0` first; report the sniffed format (Zip, ELF, gzip, text) instead of erroring.
4. **Corruption tolerance**: `PRAGMA integrity_check(1)` optionally; catch `sqlite3.DatabaseError` per table and keep going.
5. **No writes to the source dir, ever** — temp files go to `TMPDIR` and are cleaned in `finally`.

## CLI

```bash
sqlite-scout ~/code                       # tree of findings, sorted by size
sqlite-scout ~/code --json                # for scripting
sqlite-scout ~/code --csv report.csv
sqlite-scout --dupes-only ~/code
sqlite-scout --explain shop/local.db      # full schema dump + row counts + indexes
sqlite-scout --find-tables 'users,orders' # where does the real data live?
```

`--find-tables` is the everyday answer to "which of these 14 files is the one with `orders`?"

## Build

```
sqlite_scout/
  sniff.py   # magic bytes, size, wal/shm siblings
  open.py    # URI read-only connect, copy-on-wal, integrity guard
  intro.py   # schema, row counts, pragmas, timestamps
  dupes.py   # schema hash + row-count tuple + optional content hash of a sample
  report.py  # table/json/csv
```

Deps: stdlib only (`sqlite3` is in the box). Optional `rich` for tables. This is one of the best "no dependencies, obviously useful" packages in the list.

## Tests

Fixture DBs generated at test time: empty file, 0-row DB, DB with WAL and uncommitted data, deliberately corrupted page (`os.truncate` mid-file), a `.db` that's actually a zip, two DBs differing only by row count, a DB with a FTS5 virtual table, and one with a 5 M row table to check `--fast`. Assert the source file's mtime and size are unchanged after every command.

## Pitfalls

- `COUNT(*)` on a 200 M row table looks like a hang — cap with a time budget and report "≥N (sampled)".
- Virtual tables (FTS, rtree) can error on counts; skip gracefully.
- Symlinked duplicates: dedupe by `(st_dev, st_ino)` before reporting.
- Encrypted SQLite (SQLCipher) shows "file is not a database" — say so, don't call it corrupt.
- Don't be clever with "suggest deleting": report, never delete.

## Definition of done

On a 500-file project, `sqlite-scout` finishes in <3 s, correctly sniffs non-SQLite files, and its duplicate detection identifies two snapshots of the same schema at different ages. Publishing name `sqlite-scout` is free.
