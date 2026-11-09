# 39 — `log-tailer` (multi-file tail with filtering and colour)

> **Difficulty 3/10** · **Effort ~1 day** · **Tier: warm-up**
> **Prior art: ❌ fully solved** — `lnav` (log-file navigator: merging, filters, SQL over logs, time zones), `multitail` (colour, filters, split windows), `tail -F f1 f2` + `grc`/`ccze` (colourisers), `journalctl -f -u a -u b`, `stern`/`kubectl logs -f -l` (Kubernetes), `dozzle` (web), `grc`.
> **Verdict: skip.** `lnav` does more than you would build in a semester, and `stern` covers containers.

## What people actually do today

```bash
tail -F logs/api.log logs/worker.log | grep --line-buffered -E 'ERROR|WARN' | grcat conf.log
lnav logs/*.log        # merge, filter, SQL, histogram — interactive
stern 'api|worker' -n prod --since 10m
multitail -cS apache logs/access.log
```

All four cover: following multiple files, colourising levels, filtering by regex, and surviving log rotation (`tail -F` = `--follow=name --retry`, which is the one detail naive implementations get wrong).

## Why a new one loses

- **Rotation and truncation**: `logrotate` renames the file; a `stat`-polling tailer must detect inode change *and* truncation, re-open, and read from offset 0. `tail -F` has done this correctly for 30 years.
- **Colour + TTY**: `NO_COLOR`, 256-colour fallbacks, not colourising when piped.
- **Performance**: a Python loop over `readline()` on 4 files at 10k lines/s costs real CPU; `lnav` is C++.
- **Backpressure**: if the consumer (your terminal) is slow, buffering policy matters, and getting it wrong loses lines during an incident — the exact moment the tool is used.

## The only version that could be worth it

A **filter-first** tailer for *structured* logs, which is what `tail`+`grep` handles badly:

```bash
logtail --follow api.log worker.log \
  --where 'level=ERROR and duration_ms>500' \
  --dedupe 'message' --rate 20/s \
  --since 10m --json
```

i.e. a streaming `jq`/`logfmt` predicate with rate limiting and dedupe. But note: `angle-grinder`, `jq`, `lnav`'s `:filter-in`, and `stern`'s `--since`/`--tail` already cover 80 % of that, so the incremental value is thin — and file 21 (`log-fold`) covers the dedupe/summarise angle much better.

## Recommendation

Do not build. If someone wants an easy, high-value shell-adjacent tool, build **file 22 (shell-history-redactor)** or **file 27 (logslice)**: both solve a problem the existing tools genuinely don't.
