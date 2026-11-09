# 57 — `archlint` (look inside an archive before you extract it)

> **Difficulty 5/10** · **Effort ~5 days** · **Tier: hard-ish**
> **Prior art: ⚠️ fragmented** — `zipfile`/`tarfile` safety notes, `zipbomb`/`zip-bomb` PoCs, `unzip -l`, `bsdtar -tf`, `oletools` (Office macros), `yara`, `clamav`, `snyk`'s archive scanning (containers), `libarchive`'s `--safe-writes`, Python's `tarfile` `filter="data"` (3.12+).
> **Pivot required?** No, but the value is in **severity-based scoring with an explanation**, not in a checklist.

## The problem

You're about to extract `vendor-release.zip` from an unknown source, or a CI job extracts a user-supplied artifact. Known attack classes, all checkable *without* extracting:

| Class | What to look for |
|---|---|
| zip bomb | compression ratio > ~1000×, nested archives, quine structures |
| path traversal | entry name containing `..`, absolute path, drive letter, backslashes, NUL |
| symlink escape | entry is a symlink whose target leaves the extraction root, or a link → link chain |
| absolute/root paths | `/etc/passwd`, `C:\…` |
| duplicate entries | same name twice (last-wins in many extractors → TOCTOU/overwrite tricks) |
| setuid/setgid bits | mode 0o4755 in tar |
| device/fifo entries | character devices in a tar |
| huge single file | declared size > budget, or size mismatch with actual data (tar allows lying) |
| encryption/obfuscation | encrypted zip (can't scan → suspicious), garbage headers |
| special names | `.git/hooks/*`, `.bashrc`, `cron.d/*`, `*.pth` (Python site-packages persistence!) |

The `.pth` case is Python-specific and almost never checked: a wheel/tar with a `sitecustomize.py` or `anything.pth` can execute code on interpreter start. If you ship a Python tool, that's your differentiator.

## Design

```bash
archlint scan artifact.zip                    # risk report, exit 1 on high
archlint scan artifact.tar.gz --json          # CI
archlint scan *.whl --max-ratio 100 --budget 500MB
archlint scan artifact.zip --extract-to ./out --yes    # safe extraction with enforcement
```

Report format:

```
artifact.zip  (zip, 4,102 entries, 812 MB declared, 41 MB compressed)
HIGH     ratio 1,980× on "data/huge.bin" (41 KB → 81 MB)        zip bomb
HIGH     path traversal "…/../../etc/cron.d/x"                  rejects
HIGH     symlink "bin/tool" → /usr/local/bin/sh                  escapes extraction root
MEDIUM   duplicate entry "pkg/__init__.py" (2 occurrences, different sizes)
MEDIUM   persistence file "sitecustomize.py" at archive root      executes on import
LOW      setuid bit on "bin/sudo-helper" (mode 04755)
INFO     encrypted entries: 0 · nested archives: 1 (inner.zip, +200 MB declared)
VERDICT  DO NOT EXTRACT (3 high findings)
```

## Implementation details that matter

- **Never trust declared sizes.** For zip, use `ZipInfo.file_size` for the ratio check but stop reading after `--max-bytes` while decompressing a sample to verify the real expansion (a "lie" bomb declares 1 KB and expands to 4 GB). For tar, stream headers (`tarfile.open(mode="r|")`) — never `getmembers()` on an untrusted tar (it can allocate huge member lists) — and **stop after `--max-entries`** (e.g. 100k) because a tar can claim billions of entries.
- **Symlink chains**: build a link map, resolve up to 10 hops, and compare the resolved target against the extraction root; a link pointing at another link that escapes is the trick that defeats naive checks.
- **Nested archives**: scan up to `--depth 2` by streaming the member into a `BytesIO` with a size cap; report and stop (quine bombs are infinite in theory).
- **Python-specific rules**: `.pth` files containing `import` statements/absolute paths, `sitecustomize.py`, `usercustomize.py`, `.pth` in a wheel's `data/` directory, and `*.pth` content that is not a plain path.
- **Ratio thresholds** should be size-aware: a 2 KB text file "compressing" 900× is normal-ish; a 50 MB blob at 1,000× is not. Use `ratio > 200 AND uncompressed > 10 MB` as HIGH, `ratio > 1000` as HIGH regardless.
- **Safe extractor** (`--extract-to`): enforce target-inside-root after `os.path.realpath`, never create symlinks/devices, `O_NOFOLLOW` on writes, and `filter="data"` when using `tarfile` on 3.12+ (it exists precisely for this, and you should say you rely on it).

## CLI/exit codes

`0` clean, `1` medium (warn), `2` high (refuse), `3` unreadable format. `--fail-on low|medium|high` for different CI policies, `--json` with a stable schema (`findings[]` with `code`, `severity`, `entry`, `detail`).

## Tests

Generate hostile archives at test time (never commit real bombs): a 10 MB-of-zeros zip, a `../` entry (build with `zipfile` and a crafted name), a symlink entry (zip external attributes; tar `type=SYMTYPE`), duplicate names, setuid tar member, a FIFO member, a nested trap depth 3, a `.pth` payload, a lying-size tar header (patch bytes), and a malformed/truncated archive. Assert the verdict and that `--extract-to` creates **nothing** outside the root (compare the temp dir tree before/after).

## Pitfalls

- Python's `zipfile` normalises some names; check both raw `ZipInfo.orig_filename` and `filename`.
- 7z/rar need external tools — detect and either refuse with a clear message or delegate to `libarchive` via `bsdtar`; don't silently skip.
- Don't report "safe" for encrypted archives — unreadable means unknown means warn.
- Memory safety: a 4 GB zip entry must not be fully decompressed for a ratio check; read incrementally and abort.
- Windows path semantics (`C:\`, `\\?\`) must be flagged even on Linux, because the archive may travel.

## Definition of done

All ten hostile fixtures correctly classified, `--extract-to` provably cannot write outside the root, and a real 800 MB vendor artifact scans in <3 s without full decompression.
