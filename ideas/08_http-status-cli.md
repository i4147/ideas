# 08 — `urllist-check` (batch URL/endpoint status checker)

> **Difficulty 2/10** · **Effort ~1–2 days** · **Tier: warm-up**
> **Prior art: ⚠️ partial** — `urlchecker` (0.0.35, validates URLs found in static files), `httpstat` (single-request timing), `xargs -P` + `curl -o /dev/null -w`.
> **Pivot required?** Yes — a plain status-code checker is a script. Add TLS expiry, redirect chains, and assertions.

## The problem

You have a list of 300 endpoints (a sitemap, a client's API catalogue, a monitoring config). You want to know which are 404, which redirect to a dead domain, whose certificate expires in 9 days, and which are just slow — before the client does.

## What exists and why it stops short

| Tool | Stops at |
|---|---|
| `urlchecker` | URLs scraped from docs/code, no expected-status assertions, no TLS detail |
| `httpstat` | one URL at a time, pretty timings only |
| `curl` + `xargs` | no aggregation, no exit codes, no redirect-chain analysis |
| uptime services | want your URLs in their cloud |

## Scope that makes it worth a package

```bash
urllist-check urls.txt --concurrency 20 --timeout 10 \
  --expect 'api.example.com=200' --fail-on 'status>=500,tls<14d' \
  --format table|json|csv --follow --max-redirects 5
```

Input from file, stdin (`kubectl get ing -o ... | urllist-check -`), or a literal list. Per-URL output: final status, redirect chain (`301 a → 301 b → 200 c`), total + TTFB time, TLS subject/issuer/`not_after` days, content-type, body bytes, and any assertion failure.

- **Assertions**: `--expect host=200`, `--expect '*.example.com/health=200'`, `--expect-content 'api.internal=JSON'`.
- **Concurrency**: `asyncio` + `httpx` (async, HTTP/2 optional) with a semaphore; per-host rate limit (`--per-host 2`) so you don't DoS a customer's staging box.
- **Exit codes** for CI: `0` all good, `1` assertion failures, `2` TLS warnings, `3` transport errors.
- **Retry policy**: retry only idempotent verbs, only on connect/timeout errors, max 2, with jittered backoff. Never retry a 429.
- **TLS**: `ssl.SSLSocket.getpeercert()` via a custom transport; `--insecure` still records expiry (common need: internal PKI).

## Build

```
urllist_check/
  fetch.py    # async httpx client, redirect history, timings, TLS info
  expect.py   # host-glob -> assertion matching
  report.py   # table (rich), json, csv
  cli.py
```

Deps: `httpx` (only required dep), optional `rich`. Keep it importable as a library (`check(urls, ...) -> list[Result]`) so people can embed it in tests.

## Tests

`pytest-httpserver` or `httpx.MockTransport` for: redirect loop, 3-hop chain, expired cert (fixture cert generated with `cryptography` in `conftest.py`), 429 retry suppression, per-host concurrency cap honoured, CSV header stability.

## Pitfalls

- SSRF is not your problem *if* the user supplies URLs, but do not add a "follow any link found" crawler to the MVP.
- Don't buffer bodies; `stream` and read at most 1 MB (a status check that downloads a 2 GB ISO is a bug).
- HEAD is unreliable (many servers 405/403 it); default to GET with `Range: bytes=0-1023`, fall back from HEAD only if asked.
- Report `curl`-reproducible commands for every failure — that's what makes it trustworthy.

## Definition of done

300 URLs in <10 s at concurrency 20, exit codes usable in CI, and a failure line that a human can paste into `curl` to reproduce.
