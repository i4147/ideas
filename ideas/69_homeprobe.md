# 69 — `homeprobe` (one dashboard for the services you actually run)

> **Difficulty 5/10** · **Effort ~5 days** · **Tier: hard-ish**
> **Prior art: ⚠️ partial** — `gatus` (declarative YAML health checks, web UI, Go), `uptime-kuma` (self-hosted UI, Node), `prometheus` `blackbox_exporter` (the standard for probes), `healthchecks.io` (cron dead-man's-switch), `monitoringplugin`, `goss` (validate local services), `smokeping` (latency), `netdata` (host metrics). All of them are **servers**.
> **Pivot required?** Yes — the gap is a *stateless, TOML-configured, one-shot CLI* for a homelab or a single VPS. No daemon, no database, no web UI.

## The problem

You run 12 things on a small box (or three): a Postgres, two web apps, a reverse proxy, a cron backup, a WireGuard endpoint, a Home Assistant, a MinIO, and some are behind TLS certs that expire. Checking them means 12 tabs. Prometheus + blackbox + Grafana is the correct answer for a company and absurd overhead for a homelab; `gatus` is close but wants a daemon and a UI.

What a solo operator wants at 8 a.m.:

```
$ homeprobe
SERVICE          KIND      STATUS  LATENCY  DETAIL
postgres         tcp        ✓ ok    12 ms   5432 accepting, 3 connections
web-api          http       ✓ ok    84 ms   200 · cert 71d · 1.2 KB
blog             http       ✗ FAIL  2.1 s   502 after 3 retries
minio-admin      http       ! warn  310 ms  200 but cert expires in 11 days ⚠
backup@nightly   cron       ! STALE  —      last success 39h ago (expected 24h) ★
nas               ping       ✓ ok     3 ms   192.168.1.20, 0% loss
wireguard         udp        ? unknown  —    UDP cannot be probed; checking handshake file instead
SUMMARY 6/8 ok · 1 fail · 2 warn · exit 2
```

## Config

```toml
[[check]]
name = "postgres"; kind = "tcp"; host = "127.0.0.1"; port = 5432; timeout = "2s"

[[check]]
name = "web-api"; kind = "http"; url = "http://127.0.0.1:8000/healthz"
expect = { status = 200, body_contains = "\"ok\"", max_ms = 500 }
tls = { warn_days = 21 }          # only meaningful for https URLs

[[check]]
name = "minio-admin"; kind = "http"; url = "https://minio.example.com/"
tls = { warn_days = 30 }

[[check]]
name = "backup@nightly"; kind = "cron"
success_file = "/var/lib/app/last_backup.ok"   # or: command + max_age
max_age = "26h"

[[check]]
name = "nas"; kind = "ping"; host = "192.168.1.20"; count = 3

[[check]]
name = "db-replication"; kind = "command"
command = "psql -tAc 'select count(*) from pg_stat_replication'"
expect = { stdout_matches = "^[1-9]", max_ms = 3000 }
```

Concurrency: all checks in parallel (`asyncio`), total wall clock = slowest check, hard global timeout. Exit codes: `0` all ok, `1` warn, `2` fail — usable directly in a cron + `curl`-to-webhook or `systemd` + `OnFailure`.

## Implementation notes that matter

- **TLS expiry**: connect with `ssl.SSLContext`, `getpeercert()["notAfter"]`, parse with `ssl.cert_time_to_seconds`, warn at `warn_days`. Check the *chain* too (a valid leaf with an expired intermediate is a real-world failure mode). Verify by hostname, not by IP.
- **HTTP checks**: `httpx` with `follow_redirects`, connect/read timeouts, 3 retries with backoff for *transport* failures only; record TTFB separately (a 200 that takes 4 s is a warning). Never send credentials unless configured, and support `--insecure` explicitly for internal PKI (with a warning in output).
- **Cron/dead-man's-switch**: two idioms — a heartbeat file (`max_age`) or an HTTP healthchecks.io-style ping URL (`command` mode). Missing heartbeat is the single most valuable check and the one everyone forgets.
- **Ping**: `subprocess` to `ping -c 3 -W 2` rather than raw ICMP sockets (no root needed, portable inside containers). Report loss % and jitter, not just "up".
- **UDP/ICMP limits**: be honest — WireGuard/Tailscale "up" must be probed via an interface/handshake file or a TCP fallback; label `? unknown` rather than pretending.
- **Output**: plain aligned text (no `rich` requirement), `--json`, and `--format prometheus` (textfile collector format) so the same config feeds a real monitoring stack later. That escape hatch is what makes the tool credible.

## Tests

Local fixtures: an `http.server` in a thread with endpoints `/ok`, `/slow` (sleep 1 s), `/502`, `/redirect`; a `socket` listener for tcp; a temp file for the heartbeat (`os.utime` to control age); a self-signed cert generated in `conftest.py` with `cryptography` for TLS expiry (assert warn/fail at thresholds). Assert: concurrency (total time ≈ slowest, not sum), exit codes, `--json` schema, and that a DNS failure is reported as `fail` with the resolver error, not a traceback. Use a fake clock for age thresholds.

## Pitfalls

- Never fail the whole run on one misconfigured check — report `CONFIG ERROR` per check.
- Certificate checks behind a proxy verify the *proxy's* cert; document `--resolve`/`--sni` options.
- Don't hammer: per-target minimum interval, and if run from cron every minute, cap total runtime at 30 s with a clear timeout message.
- Secrets (a health endpoint with a token) come from env var references, never the TOML.
- Homelab hardware misbehaves: timeouts must be *per check*, and a global `--deadline` should still print partial results.

## Definition of done

A 15-check config on a homelab runs in <3 s, correctly flags a 502, an expiring cert, and a stale backup, and the same config can emit Prometheus metrics.
