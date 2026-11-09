# 53 — `test-budget` (runtime and flakiness budgets with history)

> **Difficulty 5/10** · **Effort ~5 days** · **Tier: hard-ish**
> **Prior art: ⚠️ partial** — `pytest --durations`, `pytest-benchmark` (5.3.1, micro-benchmarks not suite cost), `pytest-split` (sharding), `pytest-randomly` (order shuffling, useful for flakes), `pytest-rerunfailures`, `pytest-html` (report, no history), `durationpy`/Datadog CI Visibility (commercial), Buildkite Test Analytics.
> **Pivot required?** Yes — history + budgets + "newly slow" attribution, which none of the above persist locally.

## The problem

A test suite goes from 90 s to 6 minutes over a year, and nobody knows which 8 tests did it. `--durations=20` shows today's slowest; it can't tell you that `test_import_pipeline` went from 0.4 s to 22 s three weeks ago, or that 4 tests are flaky (pass/fail without a code change), which is the *other* reason people stop trusting CI.

## Design

```bash
test-budget run --budget 120s --label main      # pytest wrapper, records to SQLite
test-budget run --budget 120s --fail-on over    # CI gate
test-budget report --slowest 20 --since 14d
test-budget flaky --history .test-budget.db --min-runs 5
test-budget diff --base origin/main             # which tests got slower in THIS branch
test-budget blame test_api.py::test_export      # when did it get slow, from history
```

Schema (SQLite, one file, committed or cached in CI):

```sql
CREATE TABLE run       (id INTEGER PRIMARY KEY, started_utc TEXT, label TEXT, commit_sha TEXT,
                        branch TEXT, total_s REAL, outcome TEXT);
CREATE TABLE test_case (id INTEGER PRIMARY KEY, nodeid TEXT UNIQUE, file TEXT, first_seen_utc TEXT);
CREATE TABLE result    (run_id INT, case_id INT, outcome TEXT, duration_s REAL, setup_s REAL,
                        call_s REAL, teardown_s REAL, PRIMARY KEY (run_id, case_id));
CREATE INDEX result_case ON result(case_id, run_id);
```

Storing `setup/call/teardown` separately matters: a slow *setup* points at fixtures (see file 54), a slow *call* points at the test body.

## Implementation: it must be a pytest plugin, not a wrapper

Wrap the `pytest` main loop via a plugin (`pytest11` entry point) so it works with any invocation (`pytest -x -k foo --cov`) instead of forcing `test-budget run`:

- `pytest_runtest_logreport(report)` → capture per-phase durations and outcome (`passed/failed/skipped/error`), keyed by `report.nodeid` (stable) — but parametrised ids can contain `[]` and Unicode; store as-is, index on the raw string.
- `pytest_sessionfinish` → write the run row and results in a single transaction (`executemany`), so a crashed suite still records what ran.
- Use `report.when` for phases; note that `setup` includes fixture instantiation, which is where 60 % of suite time usually hides.

**Flakiness detection is statistical, and must say so.** For each test: `pass_rate = passed/(passed+failed)` over the last N runs *on the same commit* or across commits with no source change to that file (`git log -1 --format=%H -- <file>` equality). Flag `0 < fail_rate < 1` with `fail_rate` in [0.05, 0.95] and `runs >= 5`. Report a confidence interval (Wilson) rather than a bare "flaky" label — with 5 runs you cannot distinguish 10 % from 40 %. Also capture `rerun` results (`pytest-rerunfailures` sets `report.outcome` after retries; use `report.wasxfail`/`_pytest` internals carefully or read the `rerun` attribute in `report.__dict__` guarded by `getattr`).

**"Newly slow" attribution** (the flagship feature): compare the current run against the median of the last K runs on the base branch **per test**, not just totals. Report tests whose duration increased >2× and by >200 ms absolute, sorted by total wall-clock impact (`delta × frequency`). Then map each test to recently changed source files via `git log --name-only` since the last green run and print "likely cause: `src/importer.py` changed in 3 commits". That's the actionable link `--durations` cannot give you.

## Storage and CI

- Default DB path `.test-budget.db`, `--db` to override; `--no-record` for local iteration.
- CI: record with `label=ci-<branch>`, and commit the DB only if you accept churn — better: cache it with `actions/cache` against a rolling key, and `test-budget report --json` into a job summary.
- Guard growth: prune runs older than `--keep 90d`, and VACUUM on prune.

## Tests

`pytester` fixtures (pytest's own testing plugin) running synthetic suites: a test that sleeps 0.2 s, one that fails intermittently based on a marker file, a slow fixture setup, a skipped test, a rerun, and a `--last-failed` run. Assert the DB rows, the flaky classification with known pass/fail sequences, and that `diff` attributes a 2× slowdown to the right test. No network, no real sleeps >0.3 s (use `time.sleep` with a monkeypatched clock where possible).

## Pitfalls

- Parallel runs (`pytest-xdist`) report per-worker durations that double-count wall clock; store both `duration_s` (sum) and `wall_s` (session), and label report rows accordingly.
- Test ids change when a test is renamed → the "newly slow" diff shows a removal + an addition; match by `file::function` prefix as a fallback.
- First run in a cold cache is 3× slower (imports, DB setup): ignore the first N runs in baselines, or normalise by a per-run "cold" flag.
- Don't gate CI on absolute suite time across heterogeneous runners; gate on *per-test regressions*.
- Never let a monitoring plugin break the suite: wrap all DB writes in try/except and warn once.

## Definition of done

After two weeks of CI runs, `report` names the 5 tests responsible for 80 % of the growth with the source files likely to blame, and `flaky` lists 4 tests with pass rates and sample counts — with zero impact on suite runtime >2 %.
