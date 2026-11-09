# 27 — `logslice` (cut a time window out of any log format)

> **Difficulty 3/10** · **Effort ~3 days** · **Tier: medium**
> **Prior art: ⚠️ partial** — `lnav` (interactive, has time filters), `angle-grinder`, `awk`/`sed` one-liners, `jq` for JSON logs, `journalctl --since` (systemd only).
> **Pivot required?** Yes — non-interactive, format-agnostic, and *fast on huge files*.

## The problem

An incident happened at 14:32. You have seven log files from four services, three formats (`2026-11-09T14:32:01Z level=…`, `Nov  9 14:32:01 host app[123]: …`, `{"ts":"…","msg":…}`), one 8 GB rotated file, and you need ±10 minutes of context. `awk` requires you to know each format; `lnav` is interactive (great, but not scriptable for evidence gathering); `journalctl` only works for journald.

```bash
logslice app.log api.log --since 14:32 --until 14:45 --date 2026-11-09 --context 20 > incident.log
logslice huge.log --since '2026-11-09 14:32:00' --until +10m --format json
logslice *.log --explain-formats
```

## The real work: format detection with confidence

Timestamp formats to support at minimum (~15 patterns), each with a parser and a *confidence*:

| Pattern | Example |
|---|---|
| ISO-8601 with T and offset | `2026-11-09T14:32:01.123Z`, `+01:00` |
| ISO-8601 space, no offset (assume `--tz`) | `2026-11-09 14:32:01,123` |
| Common log format | `09/Nov/2026:14:32:01 +0000` |
| syslog / RFC 3164 | `Nov  9 14:32:01` (no year! → `--assume-year`) |
| RFC 5424 | `<34>1 2026-11-09T14:32:01Z host app - - msg` |
| JSON with `ts`/`time`/`timestamp`/`@timestamp`/`t`/`datetime` | nested, epoch seconds, epoch millis, epoch nanos |
| Go/Rust default | `2026-11-09T14:32:01.123456789+00:00` |
| Python logging | `2026-11-09 14:32:01,123 - name - INFO - msg` |
| Bare epoch | `1731155521` / `1731155521123` |
| Windows/IIS | `2026-11-09 14:32:01.123 +00:00` |

Detection: read the first 200 lines, try every pattern, pick the one with the highest *consistent* match rate (≥90 % of lines) and the most specific result; store the pattern index for the scan. **Never guess silently** — print `detected: ISO-8601 Z (12/12 sample lines)` to stderr, and `--explain-formats` makes it auditable when the output looks wrong.

Epoch disambiguation (seconds vs millis vs micros vs nanos) by magnitude; `--assume-year` for syslog; `--tz` for naive timestamps (default UTC with a warning when ambiguous — showing local by default has burned everyone).

## Performance, which is the differentiator

- **Stream** with a fixed 4 MB read buffer and `bytes` scanning; decode lazily (only lines that pass the cheap regex prefilter).
- **Fast path for sorted files**: binary search for the first offset ≥ `--since` using `file.seek` + a chunk scan, then read forward and stop at `--until`. On an 8 GB sorted log this is ~50 ms instead of 3 minutes. Detect sortedness on the sample (timestamps non-decreasing); if unsorted, full scan.
- **Parallel files**: `concurrent.futures.ThreadPoolExecutor` per file, output ordered deterministically by timestamp (or `--no-sort` for raw concatenation).
- **Context lines**: buffer the last N lines before a match (ring buffer) and continue N lines after the last match.

## Multi-line records

Exceptions span lines with no timestamp. Rules: a line *without* a timestamp is a continuation of the previous record if the previous line matched the format. Keep whole records (`--records`), so the output isn't truncated mid-traceback. This is the difference between a usable slice and a useless one.

## CLI details

```
--since / --until    absolute (parsed with the detected format or ISO) or relative (+10m, -1h, +90s)
--context N          lines/records of context around matches
--tz                 timezone for naive timestamps
--format text|json   passthrough or re-emit as JSON with "file","line","ts"
--grep PATTERN       optional second filter, applied after slicing
--stats              count per minute histogram (incident shape at a glance)
```

`--stats` is a cheap, very useful addition: a per-minute count histogram in ASCII shows the spike instantly.

## Tests

Fixtures for each format, including a file with mixed formats (must pick the dominant one and report stragglers), a sorted 100 MB generated file (assert the seek fast path is used via a monkeypatched read counter), an unsorted file, a file with a 2026→2025 date regression mid-file, and a traceback spanning the window boundary. Assert `--since 14:32 --until +10m` is inclusive on both ends and `--tz` handling matches `zoneinfo`.

## Pitfalls

- syslog without a year around New Year: `Dec 31` → `Jan 1` must not produce a negative window.
- Rotated files are usually *reverse*-sorted per file, in-order across files: sort the file list by mtime, and warn if a slice crosses files with overlapping time.
- Sub-second precision: don't truncate to seconds when comparing, or the last line of the window disappears.
- A line with a *second* timestamp inside (an embedded stack frame) must not be treated as a record start.
- Don't rewrite the log; this tool is strictly read-only (and should work on files you can only read).

## Definition of done

A 10-minute window ±40 context lines out of 8 GB in <1 s, correct across all supported formats, with the detected format printed so the result is auditable.
