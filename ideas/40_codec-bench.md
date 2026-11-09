# 40 — `codec-bench` (pick the best compression for *your* data)

> **Difficulty 3/10** · **Effort ~3 days** · **Tier: medium**
> **Prior art: ⚠️ partial** — `lzbench` (C++, the reference benchmark), `squash`/`compression-benchmarks`, `zstd --train` advice, `benchmark-compression` scripts, `python-zstandard` docs, `crabz`, `precomp`. Nothing in Python that benchmarks *your file* and gives a recommendation.
> **Pivot required?** Small — the framing is already good, the work is measurement discipline.

## The problem

"Should this 400 MB log archive be `.gz`, `.xz`, or `.zst`?" The answer depends on your data's entropy, your CPU budget, whether you decompress once or 1,000 times, and whether you need random access. Benchmarks online use corpora (Silesia, enwik8) that look nothing like your data.

A local tool that measures gzip/bz2/xz/zstd/brotli/lz4 (plus `zstd --long`, `xz -9e`, `gzip -9`, `brotli -q 11`) at several levels and returns **"use zstd-9: 92 % of xz's ratio at 8× the speed"** is genuinely useful and small.

## Design

```
$ codec-bench data/*.log --goal ratio|speed|balanced --sample 64MB --json
Sampled 64.0 MB from 12 files (4 distinct formats detected; sampling preserves file order)

codec        level  ratio   comp MB/s  decomp MB/s  peak RSS   time
gzip           6    4.12×      42        210          32 MB     1.5s
zstd           9    5.31×     118        640          64 MB     0.5s   ★ balanced
zstd          19    6.02×      14        610         512 MB     4.3s
xz             6    6.44×       6        180          96 MB    10.2s   ★ ratio
brotli        11    6.38×       2        390         256 MB    28.0s
lz4            1    2.14×     620       2100           4 MB     0.1s   ★ speed
bz2            9    4.90×       9        120          32 MB      6.6s

RECOMMENDATION (balanced, weight = 0.5·ratio + 0.5·log(speed)):
  zstd -9  →  5.31× at 118 MB/s   (vs gzip -6: +29% ratio, +181% comp speed)
  verify: decompressed output identical to input ✓ (all codecs)
```

## Measurement discipline (this is the whole tool)

1. **Sampling that doesn't lie.** Take N-byte chunks evenly spaced through *each* input file, not the first 64 MB (first 64 MB of a log is the boring part). Or `--full` for smaller inputs. Report the sampling plan in the output.
2. **Correct benchmarking**: warm up, run ≥3 iterations, report the median (not mean), use `time.perf_counter_ns`, measure compressed size after `flush()`, and **verify round-trip equality on every measurement** — a codec that returns garbage fast is worse than useless.
3. **Peak memory**: measure with `resource.getrusage(RUSAGE_SELF).ru_maxrss` per child process (each codec run in a fresh subprocess, else peak RSS is the max of everything and meaningless).
4. **Subprocess for CLI-backed codecs** (`zstd`, `xz`, `brotli`, `lz4` binaries when the Python lib is absent), with a timeout and a hard cap on input size to prevent an accidental 4-hour `xz -9e` run.
5. **Fair comparison**: same input, same block/chunk handling, and note when a codec is multithreaded (`zstd -T0`, `xz -T0`) — either pin to 1 thread or report threads used. Thread count changes the numbers by 4×, and every online benchmark gets this wrong.
6. **Scoring** must be explained, not a magic number: `score = ratio_weight * normalized_ratio + speed_weight * normalized_log_speed`; expose `--weights ratio=0.5,speed=0.5` and print the table so users can re-rank themselves.

## Python bindings to use

`zstandard`, `brotli`, `lz4` (all pip-installable, wheels everywhere), stdlib `gzip`/`bz2`/`lzma`. Fall back to subprocess binaries when a wheel is missing. Do not shell out to `7z`/`pigz` oscillating between "installed" and "not".

## CLI

```bash
codec-bench FILE... [--goal ratio|speed|balanced] [--sample 64MB] [--full]
            [--levels 1,3,9] [--codecs zstd,xz,gzip] [--json] [--csv out.csv]
codec-bench --explain zstd-9     # why it won, in plain language
codec-bench --verify-only file.zst   # is this archive intact + what codec is it?
```

`--verify-only` (magic-byte sniffing + decompress-and-check) is a nice freebie: people lose track of what codec a file uses.

## Tests

Deterministic synthetic data: random bytes (incompressible), repeated text, JSONL, a 1 MB text with entropy ~4.5, an empty file, and a 1 GB sparse file (must respect `--sample`). Assert the recommender picks lz4 for `--goal speed` on compressible data, xz/zstd-19 for `--goal ratio`, and that `--verify` catches a deliberately corrupted stream. Benchmarks themselves must be marked slow.

## Pitfalls

- Do not benchmark in-memory with one huge buffer for a codec that streams in 128 KB blocks — reported speed will be off by 2×.
- OS page cache: run each measurement twice and use the second (or `posix_fadvise`).
- Filesystem compression (btrfs/zfs) silently distorts output sizes; detect via `statfs` and warn.
- Report compressed size in bytes, and ratio as `uncompressed/compressed` (state the convention; half of all benchmark tables disagree).
- `xz -9e` on 500 MB can take 20 minutes: enforce `--max-seconds` and skip with a note.

## Definition of done

Given a real log directory, the tool produces a defensible recommendation in under a minute, every row round-trip-verified, and a `--json` report that can be committed next to the build for reproducibility.
