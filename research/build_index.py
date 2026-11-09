#!/usr/bin/env python3
"""Regenerate INDEX.md from ideas/*.md. Single source of truth = the files."""
import re, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
IDEAS = ROOT / "ideas"

PLANNED = [
    ("53", "test-budget", "pytest runtime/flakiness budgets with history", 5),
    ("54", "pytest-fixture-graph", "fixture dependency graph, unused + scope mismatches", 5),
    ("55", "jsonl-schema", "streaming schema inference/validation for JSONL", 5),
    ("56", "bug-bundle", "redacting, reviewable bug/repro bundle", 5),
    ("57", "archlint", "pre-extraction archive safety scanner", 5),
    ("58", "db-query", "named SQL shortcuts with pretty output", 5),
    ("59", "shell2py", "recorded shell session → documented Python script", 5),
    ("60", "codebase-navigator", "\"which file should I open?\" for large repos", 6),
    ("61", "upgrade-impact", "rank upgrades by breakage risk for your code", 5),
    ("62", "release-captain", "version bump → changelog → build → tag → checklist", 5),
    ("63", "api-runner", "YAML-defined API sequencer with variable passing", 5),
    ("64", "doc-diff", "human-readable \"what changed in the docs\" diff", 5),
    ("65", "ai-session-sanitizer", "export/scrub LLM coding sessions", 5),
    ("66", "read-later", "local-first read-it-later + bookmark search", 5),
    ("67", "zettel", "Zettelkasten notes + Mermaid knowledge graph", 5),
    ("68", "ledger-import", "bank CSV → plain-text ledger with rules", 5),
    ("69", "homeprobe", "service/TLS/latency dashboard from a TOML list", 5),
    ("70", "orphaned-scripts", "find one-off scripts superseded by tooling", 5),
    ("71", "context-switch", "session profiles: dir + env + services in one command", 6),
    ("72", "ai-log-rca", "local-LLM root-cause summary of a huge log", 6),
    ("73", "prompt-vault", "versioned, runnable prompt library", 6),
    ("74", "prompt-bench", "same prompt across local models, side by side", 6),
    ("75", "config-diff", "explain config drift across machines in plain English", 6),
    ("76", "git-rewrite-history", "safe bulk history rewriting", 6),
    ("77", "aws-cost-estimator", "cost estimate from terraform/cdk", 6),
    ("78", "narrative-summary", "config/JSON → prose summary", 6),
    ("79", "semantic-organizer", "content-based file sorting with local embeddings", 7),
    ("80", "semantic-secret-scan", "LLM-assisted semantic secret detection", 7),
]

FM = re.compile(r"^>\s*\*\*Difficulty\s+(\d+)/10\*\*.*?\*\*Effort\s+([^*]+)\*\*", re.M)
PA = re.compile(r"^>\s*\*\*Prior art:\s*([^—]+?)\*\*", re.M)

def parse(p: pathlib.Path):
    t = p.read_text(encoding="utf-8")
    title = t.splitlines()[0].lstrip("# ").strip()
    fm, pa = FM.search(t), PA.search(t)
    score = int(fm.group(1)) if fm else 0
    effort = fm.group(2).strip() if fm else "?"
    prior = re.sub(r"[^\w\s:/.+-]", "", pa.group(1)).strip() if pa else "?"
    return dict(path=p.name, title=title, score=score, effort=effort, prior=prior, words=len(t.split()))

rows = sorted((parse(p) for p in IDEAS.glob("*.md")), key=lambda r: r["path"])
done_nums = {r["path"][:2] for r in rows}
PLANNED = [p for p in PLANNED if p[0] not in done_nums]
bad = [r["path"] for r in rows if r["score"] == 0]
if bad:
    sys.exit(f"missing difficulty header: {bad}")

def icon(prior: str) -> str:
    low = prior.lower()
    if "solved" in low or "already built" in low or "taken" in low or "crowded" in low:
        return "🔴 solved"
    if "partial" in low or "mostly" in low or "adjacent" in low or "fragmented" in low:
        return "🟡 partial"
    if "gap" in low or "near-gap" in low:
        return "🟢 gap"
    return "⚪ unclear"

lines = []
A = lines.append
A("# Idea index — merged, deduplicated, sorted by difficulty\n")
A(f"**{len(rows)} specs written** (of {len(rows)+len(PLANNED)} unique ideas after dedup) · "
  "target: Linux, Python 3.12+ · prior-art column verified against the live PyPI JSON API "
  "(see `research/pypi_probe.py`).\n")
A("Legend — 🟢 **gap**: nothing comparable on PyPI, build it · 🟡 **partial**: something adjacent exists, "
  "pivot needed · 🔴 **solved**: a maintained tool already does this, read the pivot or skip.\n")
A("**Difficulty** = how hard it is to build *well* (correctness risk, edge cases, integration surface), "
  "not how long it takes; **effort** is the separate calendar estimate for a working MVP. Files are numbered "
  "in difficulty order, easiest first, so `01` is a weekend and `80` is a term project.\n")
A("Every file contains: problem, prior art with versions/dates, the pivot (if any), CLI surface, "
  "module layout, data model, dependencies, build order, test strategy, pitfalls, and a definition of done.\n")
A("## Written\n")
A("| # | File | Difficulty | Effort | Prior art | Words |")
A("|---|---|---|---|---|---|")
for r in rows:
    num = r["path"][:2]
    A(f"| {num} | [{r['title'].split('—',1)[-1].strip() if '—' in r['title'] else r['title']}](ideas/{r['path']}) "
      f"| {r['score']}/10 | {r['effort']} | {icon(r['prior'])} | {r['words']} |")
A("")
A("## Still to write\n")
A("These are the harder half of the deduplicated list. Numbering and scores are reserved; each will get the same "
  "treatment (including a fresh prior-art check).\n")
A("| # | Name | Idea | Difficulty |")
A("|---|---|---|---|")
for n, name, desc, score in PLANNED:
    A(f"| {n} | `{name}` | {desc} | {score}/10 |")
A("")
A("## Dedup map\n")
A("The source list had 115 entries; these collapsed into one idea each:\n")
A("| Merged idea | Source entries |")
A("|---|---|")
A("| `env-audit` | env-audit, envcheck, envdiff, env-diff, envcheck, local secrets drift checker, "
  "environment variable auditor ×3, env drift detector, `.env` sanity checker |")
A("| `dep-health` | dependency health/vitality auditor, bus factor auditor, PyPI archaeology, "
  "abandonware watchdog, holistic dependency auditor |")
A("| `dep-why` | dep-why, depweight, `pipdeptree`-style reverse tree |")
A("| `upgrade-impact` | dependency impact analyzer, upgrade-impact predictor, `upgradenotes` |")
A("| `git-changelog` | git-changelog ×2, changelog-from-prs, Git-to-changelog AI, release notes tool |")
A("| `log-fold` | log-fold, logcluster, AI log dedupe |")
A("| `cron-explain` | cron-explain, cronwhy, cronx |")
A("| `download-sort` | download-sort, file-organizer, rule-based sorter |")
A("| `env-stamp` | env-stamp, contextual reproducibility bundler (env half) |")
A("| `bug-bundle` | bug-bundle, contextual reproducibility bundler |")
A("| `project-first-run` | project-first-run, onboarding generator, local sanity checker |")
A("| `git-trim` | git-trim, git-prune-merged |")
A("| `docker-cleanup` | docker-cleanup ×2 |")
A("| `aws-cost-estimator` | aws-cost-estimator ×2 |")
A("| `read-later` | read-it-later CLI, `mark` bookmarks |")
A("| `zettel` | Zettelkasten CLI, digital garden indexer |")
A("| `mockapi` | mockapi, Pydantic-to-mock-server, spec mock server |")
A("| `schema-faker` | API payload generator, pydantic/OpenAPI fake data |")
A("| `api-runner` | api sequence runner, api-client-cli |")
A("| `prompt-vault` | AI prompt manager, local prompt versioning tool |")
A("| `prompt-bench` | local LLM prompt benchmarker |")
A("| `jsonl-schema` | jsonl-schema, schemadiff (JSON half) |")
A("| `system-monitor` | system-monitor-cli, host dashboard |")
A("| `shell-history-redactor` | shell-history-redactor, personal CLI telemetry cleaner |")
A("")
A("## How prior art was verified\n")
A("A script queried `https://pypi.org/pypi/<name>/json` for ~250 candidate and reference package names, "
  "recording existence, latest version, last upload date, and summary (`research/pypi_probe.py`). "
  "Where a better-known non-PyPI tool exists (`age`, `git-cliff`, `prism`, `hurl`, `infracost`), it is named "
  "even though it isn't on PyPI. Version numbers and dates quoted in the files come from that probe run.\n")
(IDEAS.parent / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
print(f"wrote INDEX.md: {len(rows)} written, {len(PLANNED)} planned, "
      f"{sum(r['words'] for r in rows):,} words total")
