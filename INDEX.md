# Idea index — merged, deduplicated, sorted by difficulty

**58 specs written** (of 80 unique ideas after dedup) · target: Linux, Python 3.12+ · prior-art column verified against the live PyPI JSON API (see `research/pypi_probe.py`).

Legend — 🟢 **gap**: nothing comparable on PyPI, build it · 🟡 **partial**: something adjacent exists, pivot needed · 🔴 **solved**: a maintained tool already does this, read the pivot or skip.

**Difficulty** = how hard it is to build *well* (correctness risk, edge cases, integration surface), not how long it takes; **effort** is the separate calendar estimate for a working MVP. Files are numbered in difficulty order, easiest first, so `01` is a weekend and `80` is a term project.

Every file contains: problem, prior art with versions/dates, the pivot (if any), CLI surface, module layout, data model, dependencies, build order, test strategy, pitfalls, and a definition of done.

## Written

| # | File | Difficulty | Effort | Prior art | Words |
|---|---|---|---|---|---|
| 01 | [`git-trim` (bulk-safe branch cleanup)](ideas/01_git-trim.md) | 1/10 | ~1 day | 🔴 solved | 728 |
| 02 | [`cron-explain` (cron, timezones, and DST without the guesswork)](ideas/02_cron-explain.md) | 2/10 | ~2–3 days | 🟡 partial | 744 |
| 03 | [`env-stamp` (reproducible environment fingerprints)](ideas/03_env-stamp.md) | 2/10 | ~2 days | 🔴 solved | 696 |
| 04 | [`env-audit` (reconcile `.env`, `.env.example`, CI, and the code)](ideas/04_env-audit.md) | 2/10 | ~3 days | 🟡 partial | 864 |
| 05 | [`whyport` (what is on this port, and why)](ideas/05_whoport.md) | 2/10 | ~2 days | 🟡 partial | 717 |
| 06 | [`download-sort` (rule-based file organization with real undo)](ideas/06_download-sort.md) | 2/10 | ~3 days | 🔴 solved | 716 |
| 07 | [`standup` (what did I actually do, across all my repos)](ideas/07_standup.md) | 2/10 | ~1 day | 🔴 solved | 477 |
| 08 | [`urllist-check` (batch URL/endpoint status checker)](ideas/08_http-status-cli.md) | 2/10 | ~1–2 days | 🟡 partial | 524 |
| 09 | [`help2docs` (documentation from `--help`, for tools you don't own)](ideas/09_cli-docs-generator.md) | 2/10 | ~2 days | 🔴 solved | 663 |
| 10 | [`repo-budget` (size budgets per path, enforced in CI)](ideas/10_repo-budget.md) | 2/10 | ~3 days | 🟢 gap | 749 |
| 11 | [`todo-age` (how old is that TODO, and who should fix it)](ideas/11_todo-age.md) | 2/10 | ~2 days | 🔴 solved | 688 |
| 12 | [`docker-cleanup` (reclaim disk, with attribution)](ideas/12_docker-cleanup.md) | 2/10 | ~1 day (MVP) | 🔴 solved | 683 |
| 13 | [`json-to-markdown` (JSON/YAML/TOML → Markdown tables)](ideas/13_json-to-markdown.md) | 2/10 | ~half a day | 🔴 solved | 381 |
| 14 | [`file-encryptor` (password-based file encryption)](ideas/14_file-encryptor.md) | 2/10 | ~half a day | 🔴 solved | 463 |
| 15 | [`backup-validator` (verify that a backup can actually be restored)](ideas/15_backup-validator.md) | 3/10 | ~2 days (as a thin orchestrator) | 🔴 solved | 629 |
| 16 | [`pre-commit-hooks-manager` (manage hooks across many repos)](ideas/16_pre-commit-hooks-manager.md) | 3/10 | ~2 days | 🔴 solved | 521 |
| 17 | [`markdown-lint-cli` (Markdown linting)](ideas/17_markdown-lint.md) | 3/10 | ~3 days to reach parity, months to exceed | 🔴 solved | 470 |
| 18 | [`dotsync` (dotfiles: drift detection, then safe apply)](ideas/18_dotsync.md) | 3/10 | ~3 days | 🟡 partial | 668 |
| 19 | [`schema-faker` (realistic payloads from JSON Schema / OpenAPI / Pydantic)](ideas/19_schema-faker.md) | 3/10 | ~2 days | 🔴 solved | 547 |
| 20 | [`sqlite-scout` (find and triage stray SQLite databases)](ideas/20_sqlite-scout.md) | 3/10 | ~3 days | 🟢 gap | 725 |
| 21 | [`log-fold` (collapse repeated log lines into templates)](ideas/21_log-fold.md) | 3/10 | ~4 days | 🔴 solved | 640 |
| 22 | [`shell-history-redactor` (scrub secrets out of shell history)](ideas/22_shell-history-redactor.md) | 3/10 | ~3 days | 🟢 gap | 855 |
| 23 | [`csv-contract` (catch silent changes in recurring CSV exports)](ideas/23_csv-contract.md) | 3/10 | ~3 days | 🟡 partial | 746 |
| 24 | [`dockerignore-doctor` (what is actually being sent to the Docker daemon)](ideas/24_dockerignore-doctor.md) | 3/10 | ~3 days | 🟢 gap | 821 |
| 25 | [`fixture-slim` (find bloated, duplicated, and unused test fixtures)](ideas/25_fixture-slim.md) | 3/10 | ~4 days | 🟢 gap | 799 |
| 26 | [`html2md-clip` (clipboard → clean Markdown)](ideas/26_html2md-clip.md) | 3/10 | ~2 days | 🟡 partial | 682 |
| 27 | [`logslice` (cut a time window out of any log format)](ideas/27_logslice.md) | 3/10 | ~3 days | 🟡 partial | 818 |
| 28 | [`csvrepair` (fix broken CSVs, with a change report)](ideas/28_csvrepair.md) | 3/10 | ~3 days | 🟡 partial | 810 |
| 29 | [`arch-repro` (deterministic archives: same input, same hash)](ideas/29_arch-repro.md) | 3/10 | ~3 days | 🔴 solved | 685 |
| 30 | [`time-tracker` (CLI time tracking)](ideas/30_time-tracker.md) | 3/10 | ~4 days to be worth using | 🔴 solved | 800 |
| 31 | [`lan-scan` (who is on my network)](ideas/31_network-scanner.md) | 3/10 | ~2 days for a worse version | 🔴 solved | 631 |
| 32 | [`sysmon-cli` (terminal system dashboard)](ideas/32_system-monitor.md) | 3/10 | ~1 day for a worse `htop` | 🔴 solved | 708 |
| 33 | [`password-manager-cli` (local encrypted password store)](ideas/33_password-manager.md) | 3/10 | ~4 days for something worse than `pass` | 🔴 solved | 541 |
| 34 | [`mockapi` (spec-driven mock server)](ideas/34_mockapi.md) | 3/10 | ~4 days to reach parity | 🔴 solved | 609 |
| 35 | [`jira-cli` (lightweight Jira from the terminal)](ideas/35_jira-cli.md) | 3/10 | ~5 days | 🔴 solved | 659 |
| 36 | [`pip-license-check` (dependency licence compliance)](ideas/36_pip-license-check.md) | 3/10 | ~1 day | 🔴 solved | 517 |
| 37 | [`vuln-scan` (dependency vulnerability audit)](ideas/37_vuln-scan.md) | 3/10 | ~1 day | 🔴 solved | 650 |
| 38 | [`git-changelog` (release notes from commits)](ideas/38_git-changelog.md) | 3/10 | ~1 day | 🔴 solved | 557 |
| 39 | [`log-tailer` (multi-file tail with filtering and colour)](ideas/39_log-tailer.md) | 3/10 | ~1 day | 🔴 solved | 358 |
| 40 | [`codec-bench` (pick the best compression for *your* data)](ideas/40_codec-bench.md) | 3/10 | ~3 days | 🟡 partial | 783 |
| 41 | [`archdiff` (structural diff between two archives)](ideas/41_archdiff.md) | 4/10 | ~4 days | 🟡 partial | 616 |
| 42 | [`dep-why` (why is this installed, and what breaks if I remove it)](ideas/42_dep-why.md) | 4/10 | ~4 days | 🟡 partial | 693 |
| 43 | [`venv-diff` (what changed between two environments, and does it matter)](ideas/43_venv-diff.md) | 4/10 | ~4 days | 🟡 partial | 666 |
| 44 | [`pyproject-doctor` (diagnose `pyproject.toml` drift)](ideas/44_pyproject-doctor.md) | 4/10 | ~5 days | 🔴 solved | 724 |
| 45 | [`reviewq` (the review queue across many repos and orgs)](ideas/45_reviewq.md) | 4/10 | ~4 days | 🟡 partial | 583 |
| 46 | [`dep-health` (is this dependency alive?)](ideas/46_dep-health.md) | 4/10 | ~5 days | 🟡 partial | 833 |
| 47 | [`config-doc` (turn config files into human documentation)](ideas/47_config-doc.md) | 4/10 | ~4 days | 🟡 partial | 717 |
| 48 | [`api-to-csv` (stream a nested API array into CSV/Parquet)](ideas/48_api-to-csv.md) | 4/10 | ~4 days | 🟡 partial | 596 |
| 49 | [`import-graph` (the internal dependency map of a Python codebase)](ideas/49_import-graph.md) | 4/10 | ~3 days (as a gap tool) | 🔴 solved | 658 |
| 50 | [`gh-issue-triage` (issue backlog automation for a solo maintainer)](ideas/50_gh-issue-triage.md) | 4/10 | ~4 days | 🔴 solved | 687 |
| 51 | [`project-first-run` (can I actually run this repo?)](ideas/51_project-first-run.md) | 4/10 | ~5 days | 🟡 partial | 760 |
| 52 | [`readme-gap` (what's missing from the README, and what's stale)](ideas/52_readme-gap.md) | 4/10 | ~4 days | 🟡 partial | 745 |
| 53 | [`test-budget` (runtime and flakiness budgets with history)](ideas/53_test-budget.md) | 5/10 | ~5 days | 🟡 partial | 879 |
| 54 | [`pytest-fixture-graph` (the hidden structure of your fixtures)](ideas/54_pytest-fixture-graph.md) | 5/10 | ~5 days | 🟢 gap | 744 |
| 55 | [`jsonl-schema` (schema inference and drift for event streams)](ideas/55_jsonl-schema.md) | 5/10 | ~5 days | 🟡 partial | 908 |
| 56 | [`bug-bundle` (a shareable, redacted reproduction package)](ideas/56_bug-bundle.md) | 5/10 | ~5 days | 🟡 partial | 850 |
| 57 | [`archlint` (look inside an archive before you extract it)](ideas/57_archlint.md) | 5/10 | ~5 days | 🟡 partial | 858 |
| 58 | [`db-query` (named SQL shortcuts, pretty results)](ideas/58_db-query.md) | 5/10 | ~5 days | 🔴 solved | 954 |

## Still to write

These are the harder half of the deduplicated list. Numbering and scores are reserved; each will get the same treatment (including a fresh prior-art check).

| # | Name | Idea | Difficulty |
|---|---|---|---|
| 59 | `shell2py` | recorded shell session → documented Python script | 5/10 |
| 60 | `codebase-navigator` | "which file should I open?" for large repos | 6/10 |
| 61 | `upgrade-impact` | rank upgrades by breakage risk for your code | 5/10 |
| 62 | `release-captain` | version bump → changelog → build → tag → checklist | 5/10 |
| 63 | `api-runner` | YAML-defined API sequencer with variable passing | 5/10 |
| 64 | `doc-diff` | human-readable "what changed in the docs" diff | 5/10 |
| 65 | `ai-session-sanitizer` | export/scrub LLM coding sessions | 5/10 |
| 66 | `read-later` | local-first read-it-later + bookmark search | 5/10 |
| 67 | `zettel` | Zettelkasten notes + Mermaid knowledge graph | 5/10 |
| 68 | `ledger-import` | bank CSV → plain-text ledger with rules | 5/10 |
| 69 | `homeprobe` | service/TLS/latency dashboard from a TOML list | 5/10 |
| 70 | `orphaned-scripts` | find one-off scripts superseded by tooling | 5/10 |
| 71 | `context-switch` | session profiles: dir + env + services in one command | 6/10 |
| 72 | `ai-log-rca` | local-LLM root-cause summary of a huge log | 6/10 |
| 73 | `prompt-vault` | versioned, runnable prompt library | 6/10 |
| 74 | `prompt-bench` | same prompt across local models, side by side | 6/10 |
| 75 | `config-diff` | explain config drift across machines in plain English | 6/10 |
| 76 | `git-rewrite-history` | safe bulk history rewriting | 6/10 |
| 77 | `aws-cost-estimator` | cost estimate from terraform/cdk | 6/10 |
| 78 | `narrative-summary` | config/JSON → prose summary | 6/10 |
| 79 | `semantic-organizer` | content-based file sorting with local embeddings | 7/10 |
| 80 | `semantic-secret-scan` | LLM-assisted semantic secret detection | 7/10 |

## Dedup map

The source list had 115 entries; these collapsed into one idea each:

| Merged idea | Source entries |
|---|---|
| `env-audit` | env-audit, envcheck, envdiff, env-diff, envcheck, local secrets drift checker, environment variable auditor ×3, env drift detector, `.env` sanity checker |
| `dep-health` | dependency health/vitality auditor, bus factor auditor, PyPI archaeology, abandonware watchdog, holistic dependency auditor |
| `dep-why` | dep-why, depweight, `pipdeptree`-style reverse tree |
| `upgrade-impact` | dependency impact analyzer, upgrade-impact predictor, `upgradenotes` |
| `git-changelog` | git-changelog ×2, changelog-from-prs, Git-to-changelog AI, release notes tool |
| `log-fold` | log-fold, logcluster, AI log dedupe |
| `cron-explain` | cron-explain, cronwhy, cronx |
| `download-sort` | download-sort, file-organizer, rule-based sorter |
| `env-stamp` | env-stamp, contextual reproducibility bundler (env half) |
| `bug-bundle` | bug-bundle, contextual reproducibility bundler |
| `project-first-run` | project-first-run, onboarding generator, local sanity checker |
| `git-trim` | git-trim, git-prune-merged |
| `docker-cleanup` | docker-cleanup ×2 |
| `aws-cost-estimator` | aws-cost-estimator ×2 |
| `read-later` | read-it-later CLI, `mark` bookmarks |
| `zettel` | Zettelkasten CLI, digital garden indexer |
| `mockapi` | mockapi, Pydantic-to-mock-server, spec mock server |
| `schema-faker` | API payload generator, pydantic/OpenAPI fake data |
| `api-runner` | api sequence runner, api-client-cli |
| `prompt-vault` | AI prompt manager, local prompt versioning tool |
| `prompt-bench` | local LLM prompt benchmarker |
| `jsonl-schema` | jsonl-schema, schemadiff (JSON half) |
| `system-monitor` | system-monitor-cli, host dashboard |
| `shell-history-redactor` | shell-history-redactor, personal CLI telemetry cleaner |

## How prior art was verified

A script queried `https://pypi.org/pypi/<name>/json` for ~250 candidate and reference package names, recording existence, latest version, last upload date, and summary (`research/pypi_probe.py`). Where a better-known non-PyPI tool exists (`age`, `git-cliff`, `prism`, `hurl`, `infracost`), it is named even though it isn't on PyPI. Version numbers and dates quoted in the files come from that probe run.
