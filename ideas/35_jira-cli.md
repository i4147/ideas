# 35 — `jira-cli` (lightweight Jira from the terminal)

> **Difficulty 3/10** · **Effort ~5 days** · **Tier: medium**
> **Prior art: ❌ solved multiple times** — `jira` (PyPI, official-ish Python lib + CLI), `jira-cli` (0.3.0, PyPI), `ankitpokhrel/jira-cli` (Go, actively maintained, feature-rich), `go-jira`, `jiratui` (Textual TUI), `atlassian-python-api`.
> **Pivot required?** Yes — and it's narrow: **offline-first caching for a slow/JSON-heavy workflow**.

## The problem

Jira's web UI is slow, and the Python `jira` package is a heavy dependency (`requests`, `requests-oauthlib`, `pillow`, `packaging`, `typing_extensions`, plus a `jira` shell) that many people install just to run `jira issue list`. The official REST API is fine; the ergonomics aren't.

## Why the obvious version fails

`ankitpokhrel/jira-cli` (Go) already offers: `jira issue list --jql …`, interactive TUI, sprint/epic views, create/edit/transition/assign, comments, worklogs, and shell completion. It's a single binary and it's fast. A Python reimplementation with `click` + `requests` will be slower to start (~300 ms of imports) and will have fewer features. `jiratui` covers the TUI case with Textual.

## The one credible pivot: local cache + offline queue

Jira's API is *slow* (300–900 ms typical, worse with many custom fields). A CLI that keeps a local SQLite mirror and answers instantly is a different product:

```bash
jira sync --jql 'assignee = currentUser() AND resolution = Unresolved'   # one bulk pull
jira ls                                 # instant, from the local mirror
jira show PROJ-412                     # cached; --refresh to bypass
jira comment PROJ-412 "deployed to staging"   # queued offline, flushed by `jira sync --push`
jira board --sprint current            # renders from cache, not 40 API calls
jira worklog PROJ-412 1h30m --when yesterday
```

Details that make it trustworthy:

- **Incremental sync** with `updated >= <last_sync - 5m>` JQL and a watermark table; store the raw JSON blob plus extracted columns so a schema change doesn't lose data.
- **Offline queue** with idempotency keys (`X-Atlassian-Token` not needed; use your own `client_request_id` in a comment if the API has no idempotency) and conflict detection on `updated` timestamp before pushing an edit — someone else may have changed the issue.
- **Search**: JQL passthrough *and* local FTS5 over summary/description/comments (`jira grep 'flaky test'`) — the mirror makes full-text search possible, which Jira's own UI does poorly.
- **Auth**: API token in the OS keyring (`keyring`), never in the config file; a `jira login` flow that validates against `/rest/api/3/myself`.

## Build

```
jira_cli/
  api.py     # httpx client, ADF (Atlassian Document Format) <-> plain text/markdown
  sync.py    # watermark query, pagination, upsert into SQLite
  store.py   # schema + FTS5 virtual table
  queue.py   # offline mutations, replay with conflict checks
  render.py  # rich table, --json, --format md
  cli.py
```

ADF is the trap: Jira Cloud stores descriptions and comments as a JSON document format, not Markdown. You need a converter both ways (there's `marklassian`/`adf-builder` on PyPI; wrap one rather than writing it).

## Tests

`respx` (httpx mock transport) with captured Jira Cloud fixtures: pagination via `nextPageToken`, ADF→text for a comment with mentions and a table, incremental sync watermark behaviour with a clock fixture, conflict detection when `updated` changed remotely, and queue replay idempotency (replaying twice creates one comment). Rate-limit handling: 429 with `Retry-After` must back off and resume, not drop.

## Pitfalls

- Jira Server/DC uses API v2 and different auth (basic/PAT); Cloud uses v3 + ADF. Detect and branch, and say which you detected.
- Custom fields are per-instance IDs (`customfield_10042`); resolve names dynamically and cache the mapping.
- Don't hammer: respect `Retry-After`, cap concurrency at 2, and cache aggressively.
- Timezone: Jira timestamps have offsets but report timezones per user; worklogs are even worse. Store UTC, display with `--tz`.
- Sprints and boards live in the Agile API (`/rest/agile/1.0`), a different base path and different permissions.

## Definition of done

`jira ls` returns in <80 ms from cache for 2,000 issues, `sync` of a 2,000-issue JQL set takes <30 s, and offline comments flush correctly after a network hiccup. If you can't beat `ankitpokhrel/jira-cli` on this axis, don't ship it.
