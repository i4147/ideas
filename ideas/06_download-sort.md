# 06 — `download-sort` (rule-based file organization with real undo)

> **Difficulty 2/10** · **Effort ~3 days** · **Tier: warm-up**
> **Prior art: ❌ crowded** — PyPI `download-sort` (0.1.0 placeholder), `file-organizer` (0.2.3, suffix-based), `organize` (Go), `czkawka`, `ranger`/`nnn` (interactive), macOS Hazel (GUI).
> **Merged from:** `download-sort`, `file-organizer`, "semantic file organizer" (rule half only — the embedding version is file 79).
> **Pivot required?** Yes — sorting by extension is a solved one-liner. Undo + dry-run + content sniffing is not.

## The problem

`~/Downloads` with 3,000 files: `invoice (3).pdf`, `Screenshot 2026-11-04 at 10.41.22.png`, five copies of the same 40 MB installer, `statement.csv`. Extension-based organizers exist and are useless for the actual piles:

- `.pdf` covers invoices, papers, tickets, and scanned passports — different homes;
- date should come from **content/filename**, not mtime (downloads preserve nothing);
- duplicates should be collapsed before sorting, not after;
- the one thing every existing tool gets wrong: **you can't undo it**, so nobody dares run it.

## The pivot: plan → apply → undo, with content-aware signals

```
$ download-sort plan ~/Downloads --config sort.toml
WOULD MOVE (1,284 files, 41.2 GB)
  Finance/Invoices/2026/INV-2026-0412-Acme.pdf      ← invoice no. in text layer
  Media/Screenshots/2026-11/Screenshot 2026-11-04…png
  Software/Linux/firefox-132.0.tar.bz2              ← ELF/tar sniffed, not extension
DUPLICATES (37 groups, 8.4 GB reclaimable)
  ~/Downloads/installer(2).exe == ~/Downloads/installer.exe    keep oldest
UNSORTED (52) → leave in place, listed at the end
Run `download-sort apply --plan .download-sort/plan-20261109.json` to execute.
```

Signals, in priority order: **(1)** explicit glob/extension rules → **(2)** filename regex with capture groups (`INV-(?P<year>\d{4})`) → **(3)** MIME sniffing on the first 4 KB (`libmagic` via `python-magic`, optional) → **(4)** embedded metadata (PDF `/CreationDate` + text layer first page, EXIF `DateTimeOriginal`, ID3, OOXML core properties) → **(5)** mtime as a fallback only, clearly labelled.

Extraction stays cheap and optional: `pypdf` for the first page's text and metadata, `Pillow` for EXIF, `zipfile` for OOXML. Everything wrapped in a per-file time budget (`--max-inspect-ms 200`) and a hard try/except so one corrupt PDF cannot abort a 3,000-file run.

## CLI surface

```bash
download-sort plan  ~/Downloads --config sort.toml [--json]
download-sort apply --plan .download-sort/plan-20261109.json [--yes]
download-sort undo  [--last | --plan-id X]
download-sort dedupe --by content [--keep oldest|newest|shallowest]
download-sort explain "Screenshot 2026-11-04 at 10.41.22.png"   # which rule fired, why
```

`apply` writes a journal (JSONL) *before* each move, in this shape — that journal is the undo log and the audit trail:

```json
{"ts":"2026-11-09T14:31:02Z","op":"move","src":"/home/a/Downloads/x.pdf",
 "dst":"/home/a/Documents/Finance/Invoices/2026/x.pdf","sha256":"…","size":40213,"rule":"invoice-regex"}
```

Use `os.rename` when same filesystem; `shutil.move` across devices. Never overwrite: on collision, append ` (1)` or route to `_conflicts/` — configurable — and record it.

## Config

```toml
[general]
root = "~/Downloads"
on_conflict = "rename"          # rename | skip | conflicts_dir
min_age_days = 1                # don't touch what you just downloaded

[[rule]]
name = "invoices"
match = { filename = "(?i)invoice|receipt|INV-\\d+" }
dest  = "~/Documents/Finance/Invoices/{year}"

[[rule]]
name = "screenshots"
match = { filename = "(?i)^(screenshot|screen shot|cleanshot)" }
dest  = "~/Pictures/Screenshots/{year}-{month}"

[[rule]]
name = "installers"
match = { mime = ["application/x-executable","application/x-tar","application/zip"],
          min_size = "20MB" }
dest = "~/Software/{ext}"
```

Rule evaluation is first-match-wins and deterministic; `explain` prints the matched rule plus the captured groups so users can debug their own regexes.

## Tests

`tmp_path` trees with 30 handcrafted files (fake PDFs with real minimal headers, PNGs with EXIF, a 0-byte file, a symlink, a name with newline and emoji, a file that would collide). Assertions: dry-run changes nothing, apply matches the plan byte-for-byte, undo restores every path *and* mtime, interrupted apply (simulate by raising after N ops) is recoverable with `undo`, cross-device path is mocked.

## Pitfalls

- **Symlinks**: default to skipping, `--follow-symlinks` opt-in; never move a link's target.
- Filenames with `\n`, leading `-`, or 255-byte limits — never pass through a shell.
- Case-insensitive collision on macOS/exFAT (`.PDF` vs `.pdf`) even though target is Linux.
- Don't scan `~/Downloads` recursively by default (nested project folders get shredded); `--recursive` opt-in.
- `undo` must be idempotent and must refuse if the destination was modified since the move (compare sha256) — partial undo with a clear report beats a corrupt tree.
- Being a "file mover" means being blamed for data loss: default `plan`, require `--yes` for `apply`, and fsync the journal.

## Definition of done

A 3,000-file Downloads folder is planned in <5 s, deduped, applied with a complete undo journal, and `undo` restores an identical tree. Publish name `download-sort` is taken — use `sortplan` or `dl-sort`.
