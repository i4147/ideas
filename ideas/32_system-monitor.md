# 32 — `sysmon-cli` (terminal system dashboard)

> **Difficulty 3/10** · **Effort ~1 day for a worse `htop`** · **Tier: medium**
> **Prior art: ❌ fully solved** — `glances` (4.5.9, Python, does everything incl. Prometheus export), `btop`/`bpytop` (Python originally, now C++), `htop`, `bottom` (`btm`), `vtop`, `nvtop`, `nethogs`, `iotop`.
> **Pivot required?** Yes — but "make a nicer htop" is a losing battle. Only the *export/alert* angle has room.

## The problem

"Lightweight real-time dashboard for CPU/mem/disk/net" is the single most-built tool in the Unix world. `glances` alone covers: CPU per core, memory, swap, disk I/O by process, network throughput per interface, sensors, containers, GPU, plus a web UI, an API, Prometheus/InfluxDB export, and alerting. In Python. Actively maintained.

## Why the original idea is a dead end

- `htop`/`btop` own the interactive niche and are faster (C++), with mouse support and themes.
- `glances` owns the "everything plus export" niche, in Python, the exact language you'd use.
- `psutil` (which you'd depend on) is the same dependency `glances` uses, so you have no performance advantage.
- A TUI needs terminal-resize handling, colour degradation, key handling, and a refresh loop that doesn't tear. That's the majority of the work, and it's already done better four times.

## The sliver that isn't solved

**"Is this machine healthy over time?"** rather than "what is it doing now":

```bash
sysmon-cli sample --interval 10s --out ~/.local/share/sysmon/metrics.jsonl  # cheap, no daemon
sysmon-cli report --since 24h        # p95 vs p50, top consumers, disk fill rate, OOM events
sysmon-cli watch --threshold cpu=90%:5m --exec 'notify-send …'  # sustain-based, not instantaneous
sysmon-cli capacity --disk /var      # "full in 11 days at current rate"
```

Three concrete gaps:

1. **Sustained-threshold alerts.** Everyone alerts on instantaneous CPU, which fires constantly. Alerting on "CPU > 90 % for 5 minutes" or "load average above core count for 10 min" with hysteresis is what actually matters, and `glances`' alert model is per-plugin, per-sample.
2. **Trend/capacity, not snapshot.** Disk fill rate (`df` history → days-to-full), memory leak detection (RSS of a named process growing monotonically over 6 h), swap-in rate.
3. **JSONL instead of a time-series DB.** A 10-second sample for a month is ~260k lines = ~30 MB; `pandas`/DuckDB read it instantly. No InfluxDB required, which is what everyone wants for a laptop.

`report` should be genuinely insightful, e.g.:

```
24h: cpu p50 4% p95 61% (peak 97% 09:14–09:22, process "pytest" 3 runs)
mem: 14.2/16 GB, swap-in 1.4 GB  ← memory pressure, top: chrome 6.1 GB
/var: 82% used, +1.1 GB/day → full in ~4 days  ⚠
oom_kills: 1 (09:22, python)
```

OOM events come from the kernel log (`journalctl -k -g "Out of memory"` or `/dev/kmsg`) — a detail most dashboards omit and the most useful line in the report.

## Build

```
sysmon_cli/
  sample.py   # psutil.cpu_percent(interval=None), virtual_memory, disk_usage, net counters, per-process top-5
  store.py    # append-only JSONL with rotation (compress >7d with gzip)
  report.py   # percentile math, per-process attribution via sampled top-N
  alert.py    # sustained thresholds + hysteresis + cooldown
  cli.py
```

Deps: `psutil` (unavoidable). No TUI in v1 — printing a report is more useful and 10× less code. If a TUI is wanted later, add `--tui` using `textual`, but that's v2.

## Tests

Inject a fake psutil module (monkeypatched) to test percentile math and threshold hysteresis: 4 samples above 90 % then 1 below must not clear the alert. Capacity forecast: linear regression on daily `df` with a noisy fixture; assert "days to full" within ±20 %. Test rotation keeps 7 days of uncompressed and gzips the rest.

## Pitfalls

- Sampling must be cheap: `cpu_percent(interval=None)` (non-blocking) and skip per-process scans unless `--processes`.
- Don't sample the whole process table every 10 s on a 4-core box (that's 0.5 % CPU forever); sample top-5 by a cheap first pass.
- Container memory accounting (`cgroup v2 memory.current`) differs from `psutil.virtual_memory` — report both.
- File growth: enforce a budget and rotate; a monitoring tool that fills the disk is a classic self-own.
- Clock jumps (NTP/suspend) must not produce negative deltas; store monotonic alongside wall clock.

## Definition of done

A week of 10-second samples stays under 20 MB, `report --since 24h` correctly identifies a memory-leaking process and a disk filling at 1 GB/day, and no TUI code is written.
