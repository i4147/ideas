# 29 — `arch-repro` (deterministic archives: same input, same hash)

> **Difficulty 3/10** · **Effort ~3 days** · **Tier: medium**
> **Prior art: ❌ solved by existing tools** — `strip-nondeterminism` (Debian, Perl), `reprozip` (1.3.2, PyPI), `SOURCE_DATE_EPOCH` (the standard), `reprotest` (0.7.33), `diffoscope` (verification side), plus every packaging tool's own normalization (`wheel`, `hatchling`, `flit` already honour `SOURCE_DATE_EPOCH`).
> **Pivot required?** Yes — **Python-native rewriting for CI is the only open sliver, and it's narrow.**

## The problem

The same source directory tarred twice gives two different SHA-256s, because tar records mtime, uid/gid, owner names, and directory order — and `gzip` records a timestamp and the original filename. This breaks reproducible builds, cache keys, and "did anything actually change?" checks.

The fix is a well-understood transform: sorted entry order, fixed mtimes (`SOURCE_DATE_EPOCH`), zeroed uid/gid/uname/gname, normalized modes, stripped gzip header (mtime=0, no filename, OS=255), and for zip: fixed DOS timestamps, no extra fields, sorted central directory.

## What exists

- `strip-nondeterminism` — does exactly this for zip/tar/gzip/jar/pdf; it's **Perl** with a Debian package, awkward in a Python CI container.
- `reprozip` — a *packer* for experiment provenance (traces syscalls), not an archive normalizer; different tool entirely, name is misleading.
- `SOURCE_DATE_EPOCH` — the *convention*; honoured by setuptools/wheel/hatch, ignored by `tar`, `zip`, `rpm`, and most scripts.

So the honest gap: a pip-installable, pure-Python normalizer that CI can call as `arch-repro normalize dist/*.tar.gz dist/*.whl` without a Perl/apt dependency.

## Scope that stays honest

```bash
arch-repro normalize dist/*.tar.gz dist/*.whl --epoch 1700000000 -o out/
arch-repro check dist/x.tar.gz            # is this archive already deterministic? list offences
arch-repro verify --build ./build.sh      # run the build twice, compare hashes (needs reprotest-ish care)
```

`check` is often more valuable than `normalize`: it tells you *which* of the five sources of nondeterminism you actually have (mtimes, ordering, uid, mode, gzip header, comment field) so you can fix the build rather than post-process.

**Formats:** tar (ustar + pax), gzip, zip/wheel. Explicitly refuse (with a clear message) xz-in-tar racing data, rpm/deb, and anything requiring a rebuild.

## Implementation notes (where the bugs live)

- **tar**: rewrite via `tarfile.open(mode="w", format=tarfile.PAX_FORMAT)`; sort members by `name` (normalized, `/`-separated, no `./` prefix); `mtime=epoch`; `uid=gid=0`; `uname=gname=""`; mode `0o755` for dirs, `0o644` for files, `0o755` for files with the exec bit (preserve only the exec bit); strip pax headers except `path`/`linkpath` when needed; do not follow symlinks.
- **gzip**: `gzip.GzipFile(fileobj=out, mode="wb", mtime=0, filename="")` — Python's `gzip` writes the filename by default when given one, which is the classic leak of the source path.
- **zip/wheel**: `zipfile.ZipInfo` with `date_time=(1980,1,1,0,0,0)` (the ZIP epoch — anything earlier is invalid), `external_attr` set from the mode, `create_system=3` (Unix), `compress_type=ZIP_DEFLATED` with a fixed level (level affects bytes!), and sort by filename. `extra=b""`.
- **Wheels specifically**: `RECORD` must be regenerated after rewriting (hashes change) — `wheel`'s `WheelFile` handles this; use it for `.whl` instead of raw `zipfile`, and update `.dist-info/RECORD` last.
- **Verify your own output**: `normalize(normalize(x)) == normalize(x)` byte-for-byte. That idempotency test catches nearly every mistake.

## Tests

Build a tree with: files whose mtimes differ by seconds, uid/gid 1000, umask-dependent modes, a file with a `\n` in its name, a symlink, a hardlink pair, a 100-byte file, an empty dir, and non-ASCII names (NFC/NFD normalization matters on macOS). Normalize twice in separate processes (fresh `umask`), assert identical sha256. Fixtures must include a real wheel built by `build` to test `RECORD` regeneration.

## Pitfalls

- `SOURCE_DATE_EPOCH` must be read from the environment and surfaced in `--help`; hardcoding 1980 breaks anything that checks the date.
- Changing compression level changes hashes — pick one and document it as part of your format.
- Never normalize an archive you don't own the licensing of and republish it as "reproducible" without noting the transformation.
- `xz`/`zstd` wrappers are separate (`XZ Utils` supports `--threads=1` for determinism); don't claim them.
- If `strip-nondeterminism` is already installed, offer `--delegate` so CI users with Debian have a path.

## Definition of done

`normalize` on a wheel and an sdist produces byte-identical output across two machines and two runs, `check` names the offending header for a non-deterministic archive, and the package installs with `pip install arch-repro` and no system dependencies.
