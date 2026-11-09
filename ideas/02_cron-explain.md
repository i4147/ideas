# 02 — `cron-explain` (cron, timezones, and DST without the guesswork)

> **Difficulty 2/10** · **Effort ~2–3 days** · **Tier: warm-up**
> **Prior art: ⚠️ partial** — libraries exist (`croniter`, `cronsim`, `cron-descriptor`, `crontab`), and there are web explainers, but no Linux CLI that answers *"why didn't it run?"*.
> **Pivot required?** Yes — explaining fields is a solved one-liner. The value is DST + overlap + missed-run diagnosis.

## The problem

Cron is everywhere and silently wrong. Three failure modes that cost real hours:

1. **DST.** `0 2 * * *` in `Europe/London` does not run at 02:00 on the spring-forward day (that hour doesn't exist), and runs twice on the autumn day (02:00 occurs twice). `croniter` will happily print predictions that no daemon would follow.
2. **Overlap.** Two jobs that both take 40 minutes scheduled `*/30 * * * *` build up a queue nobody notices.
3. **Silent non-execution.** Job didn't run because: no trailing newline in crontab, `%` unescaped, wrong user, `/etc/cron.d` file with wrong permissions (must be 0644, root-owned, no dot in name), systemd timer shadowing, or the daemon being anacron-less on a laptop that was asleep.

## What already exists

| Tool | Gap |
|---|---|
| `croniter` / `cronsim` (libraries) | give you `get_next()`; you still have to reason about DST and write the CLI |
| `cron-descriptor` | converts `*/5 * * * *` → "Every 5 minutes" (English only, no schedule math) |
| crontab.guru (web) | no next-runs list, no tz, no file analysis, no exit codes |
| `systemd-analyze calendar` | excellent for systemd timers, but not crontabs and not multi-file |

A single CLI that reads `/etc/crontab`, `/etc/cron.d/*`, `crontab -l`, and `.github/workflows/*.yml` cron blocks, then explains each entry with real timezone math, does not exist as a pip-installable tool.

## CLI surface

```bash
cron-explain "*/5 9-17 * * MON-FRI" --tz America/Toronto --next 5
cron-explain --file /etc/cron.d/backup --dst-warnings --json
cron-explain --file crontab --overlaps --min-duration 40m
cron-explain --explain-missed "0 2 * * *" --tz Europe/London --window 2026-03-25:2026-04-05
```

## How to build it

```
cron_explain/
  parser.py     # 5-field (and @daily/@reboot) -> CronSpec(fields, user, command, source_file)
  explain.py    # per-field English ("every 15 minutes, between 09:00 and 17:00, Mon–Fri")
  schedule.py   # next_run(spec, tz, after, n) using zoneinfo, NOT naive datetime
  dst.py        # classify each computed run: normal | skipped (gap) | duplicated (fold)
  overlaps.py   # pairwise interval overlap over a horizon using declared/observed durations
  sources.py    # discover crontab files; ignore-invalid-permissions report
  render.py     # table + json
```

**DST is the whole trick.** Compute candidate wall-clock times in the target zone, then resolve with `datetime.astimezone(ZoneInfo(tz))`:

- For each date, build naive `02:00`, attach tz with `fold=0` and `fold=1`; if both map to the same instant → normal. If the naive time lands in a gap (spring forward), Python raises nothing — you detect it by round-trip: `naive → aware → astimezone(UTC) → astimezone(tz)` and compare; mismatch means **skipped**.
- Vixie cron runs *skipped* DST jobs once when the clock jumps (i.e. it catches up), while `systemd` timers with `OnCalendar` do not. Emit the daemon-specific note — that difference is the top source of confusion, and no existing tool states it.
- For duplicated times, report "runs twice" and warn about non-idempotent jobs (anything containing `>>`, `rm`, `mail`, or POST-like commands — a cheap heuristic, flag it as heuristic).

## Data model

```json
{"source": "/etc/cron.d/backup", "line": 4, "user": "root", "schedule": "0 2 * * *",
 "runs": [{"at": "2026-11-10T02:00:00-05:00", "kind": "normal"},
          {"at": "2027-03-14T03:00:00-04:00", "kind": "shifted", "note": "DST gap; Vixie runs once"}],
 "warnings": ["runs twice on 2026-11-01"]}
```

## Tests

Fixtures of tz + expression + expected instants, asserted against known DST dates for `Europe/London` (2026-03-29, 2026-10-25), `America/New_York` (2026-03-08, 2026-11-01), and `Australia/Lord_Howe` (30-minute DST offset — the case everyone forgets). Property test: every generated run, converted to UTC and back, must be a valid instant; count per day ≤ 2.

## Pitfalls

- Use `zoneinfo` (stdlib, 3.12), not `pytz`. Never do naive arithmetic on aware datetimes.
- Cron's day-of-month OR day-of-week semantics: `0 0 13 * 5` means "13th OR Friday". Almost every explainer gets this wrong; handle it explicitly and test it.
- `@reboot`, `%` escaping, `CRON_TZ` (Vixie), and `MAILTO` need parsing but can be reported as unsupported rather than mis-explained.
- Report `--next` relative to the tz, not the host tz.

## Definition of done

Output for a DST-crossing window explains exactly what the daemon does, in one screen, with `--json` for scripting and exit code 3 when warnings exist.
