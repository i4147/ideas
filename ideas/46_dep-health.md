# 46 — `dep-health` (is this dependency alive?)

> **Difficulty 4/10** · **Effort ~5 days** · **Tier: medium**
> **Prior art: ⚠️ partial** — `deps.dev` API (Google: Scorecard, dependents, advisories), OpenSSF Scorecard, Snyk Advisor (web), `libraries.io` (API), `pypistats`, `pip-audit` (security only), `npm audit` equivalents, `ecosyste.ms`.
> **Merged from:** "dependency health/vitality auditor", "bus factor auditor", "PyPI package archaeology", "abandonware watchdog" (4 entries).
> **Pivot required?** Yes — the *dossier* and the *recommendation*, not the metrics.

## The problem

`pip-audit` says "no known vulnerabilities" — and the package was abandoned in 2021, has one maintainer, 340 open issues, and no release in 4 years. You're building on sand and no signal told you.

## What exists

`deps.dev` already exposes OpenSSF Scorecard, dependency counts, advisories, and "project health" per package; `ecosyste.ms` has release cadence and maintainer data. So *fetching* the metrics is a solved, free API call. The unsolved part is turning 12 metrics into a decision, per package, in a form a human reads once:

```
$ dep-health check
14 direct dependencies analysed (source: deps.dev + PyPI + GitHub)

RISK  pkg "oldorm" 2.1.0
  last release   2019-04-02  (6.6y ago)        ✗
  maintainers    1 (bus factor 1)              ✗
  commits 12mo   0                             ✗
  open issues    142 (closed in 90d: 3)        ✗
  dependents     ~1,200                        ·  (not abandoned by usage)
  fork activity  2 active forks with releases  ·
  verdict        ABANDONED — 2 active forks: fork-a (last release 3mo ago), fork-b
  action         pin and vendor, or migrate to fork-a

WATCH "requests" 2.32.3
  last release 8mo ago, 4 maintainers, 88 issues (responded 71% within 30d)  ✓
```

## The decision model, made explicit

Score each package on four axes, each with the evidence shown (never a single opaque number):

1. **Currency**: days since last release, and whether the *latest* release is a patch/minor/major vs your pin. (>2 y without a release in an actively-changing ecosystem = high risk.)
2. **Bus factor**: distinct commit authors in 12 months (GitHub API), maintainer count from PyPI metadata, whether the most active maintainer also owns 50+ packages (a maintainer-overload risk signal that `deps.dev` exposes indirectly).
3. **Responsiveness**: median time-to-first-response on new issues (sample the last 50 issues via GitHub API — this is a real measurement, not a guess), open/closed ratio, and whether security advisories were fixed promptly (from `deps.dev`'s advisory history).
4. **Escape route**: are there maintained forks or drop-in successors? Determine by: forks with releases in the last 12 months (GitHub `/forks?sort=newest` + releases), and `deps.dev`'s "similar packages". **This is the axis everyone omits and the only one that changes the decision** — "abandoned with no fork" is a very different verdict from "abandoned, but `fork-a` is a drop-in".

Output is a per-package dossier + a portfolio summary ("3 of 14 at risk; 1 with no escape route"). `--json` for a dashboard, `--sarif`/annotations for CI. Default CI behaviour: fail only on `high` risk *and* no escape route — otherwise you get alert fatigue and the tool gets removed.

## Implementation

```
dep_health/
  sources/pypi.py     # JSON API: releases, yanked, maintainers, requires_python
  sources/depsdev.py  # Scorecard, dependents, advisories (batch endpoint /v3alpha/systems/pypi/packages/{n})
  sources/github.py   # commits, issues, releases (needs a token; degrade gracefully)
  score.py            # axes -> evidence -> verdict + confidence
  render.py, cli.py
```

- **Batching**: `deps.dev` supports batch requests (up to 1,000 package versions per POST) — use it, one round-trip for a whole lockfile.
- **Rate limits**: GitHub unauthenticated is 60/h — refuse to run the GitHub axis without a token, and label those axes "unknown", not "healthy".
- **Cache** per package for 7 days (`~/.cache/dep-health/`), with `--refresh`; a weekly CI run shouldn't re-fetch the world.
- **Never invent maintainer activity** from PyPI alone (PyPI has no commit data); each axis states its source and `--offline` mode uses only cached data with a clear "stale" marker.

## Tests

Fixture JSON from each source (captured, no network) for: a healthy package, an abandoned one with an active fork, an abandoned one with no fork, a package with a single-release history (too young to judge → "insufficient evidence"), a yanked release, and a package whose GitHub repo moved (404 → mark unknown). Assert verdict mapping and that unknown axes lower confidence rather than the score.

## Pitfalls

- "No release in 2 years" is *fine* for a stable, finished library (e.g. a small pure-Python utility). Your verdict must say "stable" vs "abandoned" using issue-response and commit signals, not release cadence alone.
- Maintainer count from PyPI's `maintainer`/`author` fields is unreliable (organisations, bots).
- Big projects look responsive in aggregate but can be hostile in the issue tracker — cap the recommendation at "review" rather than pretending to measure culture.
- Don't scrape GitHub HTML; use the REST/GraphQL API with conditional requests (ETag) to save rate limit.
- Time-based metrics age badly in a repo: store the fetch date in every dossier.

## Definition of done

A lockfile of 40 packages analysed in one batch in <15 s with cache, and the report changes at least one decision (a package you'd have kept you now pin/vendor, with the fork named).
