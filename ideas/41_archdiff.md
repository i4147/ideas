# 41 — `archdiff` (structural diff between two archives)

> **Difficulty 4/10** · **Effort ~4 days** · **Tier: medium**
> **Prior art: ⚠️ partial** — `diffoscope` (338, in-depth, 50+ formats, slow by design), `zipdiff`, `tar --diff`, `bsdtar -d`, `debsums`, `pkgdiff`, `diff -r` after extraction.
> **Pivot required?** Yes — speed and CI ergonomics, not depth. Do not compete with `diffoscope` on depth.

## The problem

You have `myproject-1.5.0.tar.gz` and `myproject-1.5.0-py3-none-any.whl` built from the same commit, and you want to know: are the file lists identical? Do the bundled files match? Did the wheel ship a stale `LICENSE`? Which entries differ in mode or timestamp?

`diffoscope` answers *everything* and takes 40 seconds and 200 MB of RAM for two 5 MB archives, printing a recursive tree you must read carefully. In CI, you want:

```
$ archdiff a.tar.gz b.whl
FORMAT   tar.gz (gzip, 41 entries)  vs  zip (wheel, 44 entries)
IDENTICAL   38 files (byte-for-byte)
CHANGED      1  myproject/__init__.py     (289 B → 291 B, sha256 …→…)
ONLY IN A    2  myproject/_build/cache.bin, myproject/tests/…
ONLY IN B    3  myproject-1.5.0.dist-info/{RECORD,WHEEL,METADATA}
MODE        1  myproject/cli.py  0755 → 0644
TIME        all  2026-11-09 12:00:00 (A) vs 1980-01-01 (B, normalized)
exit 1
```

Exit codes and `--format json` are the product; humans read the top-10 list, CI reads the JSON.

## Design that avoids diffoscope's trap

- **Never extract to disk.** Stream entries: `tarfile.open(fileobj=…)` and `zipfile.ZipFile` both support reading members incrementally. Compare by `(name, size, sha256 of streamed bytes, mode, mtime)`.
- **Normalize names** per format: wheel paths are relative to the project dir; tarballs have a top-level `project-version/` prefix. Strip a common prefix when `--normalize-prefix` (default on, reported when applied) — otherwise everything shows as "only in A".
- **Hash cost is the limit**: 500 MB of entries hashed twice is ~1.5 s with `blake2b` and a 1 MB buffer, plus decompression. That's acceptable; offer `--size-only` (5× faster) and `--no-hash` for a manifest-only diff.
- **Formats**: tar (all compressions via `tarfile` `r:*`), zip (incl. wheels/jars), and a plain directory (`archdiff dist/ dist2/`). Refuse others by name with a suggestion (`--external diffoscope` delegation via `subprocess` when depth is genuinely needed — a nice escape hatch that makes the tool honest).
- **Metadata comparison is opt-in** (`--modes --times --owners`): timestamps make every comparison noisy, and for wheels they're *normalized* (1980) by design, so default off and explain why.

## CLI

```bash
archdiff A B [--json] [--size-only|--no-hash] [--modes] [--times]
             [--only '**/*.py'] [--ignore '*.dist-info/RECORD'] [--exit-zero]
```

`--ignore` patterns are essential in practice: `RECORD`, `*.pyc`, `.DS_Store`, and `__pycache__` produce false alarms on every run.

## Tests

Build pairs at test time: a tar and a wheel from the same tiny project (`build` in-process), then mutate copies (append a byte to one file, chmod one file, add a file, truncate an entry, change mtime). Assert the classification and the exit codes. Include: an archive with a duplicate entry name (tar allows it!), a symlink entry, a PAX long path (>100 chars), a ZIP64 archive, an encrypted zip (must fail cleanly), and a 0-byte file.

## Pitfalls

- Duplicate names in tar: compare by the *last* occurrence (tar semantics) and report the duplicate explicitly.
- Wheels' `RECORD` contains hashes of the files — it will always differ if anything differs, so it's derived noise; ignore by default.
- Symlinks vs regular files with the same name: compare `type` before content.
- Never write to the archive's directory (no temp extraction next to it).
- Timestamps inside zip are 2-second resolution — don't report 1-second differences as meaningful.

## Definition of done

Two 50 MB archives compared in under 4 s, exit code trustworthy in CI, and a `--only`/`--ignore` set that makes a real-world wheel-vs-sdist comparison produce exactly the 3 differences a human cares about.
