#!/usr/bin/env python3
"""Regenerate INDEX.md from ideas/*.md.  Single source of truth = the spec files.

    python3 arena/build_index.py            # rewrite INDEX.md
    python3 arena/build_index.py --check    # exit 1 if INDEX.md is stale (CI)

The renderer is importable (`from arena.build_index import render_index`) so
tests/test_specs.py can assert the committed index matches the specs.
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
IDEAS = REPO_ROOT / "ideas"
INDEX = REPO_ROOT / "INDEX.md"
TOTAL_IDEAS = 80

DIFFICULTY = re.compile(r"^>\s*\*\*Difficulty\s+(\d+)/10\*\*.*?\*\*Effort\s+([^*]+)\*\*", re.M)
PRIOR_ART = re.compile(r"^>\s*\*\*Prior art:\s*([^—]+?)\*\*", re.M)

# Why each genuine gap is still open, keyed by file number. Curated by hand:
# these are the claims the index makes beyond what the specs already say.
GAP_WHY = {
    "10": "size budgets per path with PR-scoped regression mode; nobody ships this",
    "20": "read-only triage of stray SQLite files; stdlib-only, obviously useful",
    "22": "no tool redacts shell history, and it's the most secret-dense file on a laptop",
    "24": "build-context size and secret leakage are invisible before `docker build`",
    "25": "fixture cost/duplication audit; pytest exposes the graph, nobody reports it",
    "54": "fixture graph is invisible in pytest; authoritative data is one hook away",
    "64": "instruction-level doc diff; deterministic, no competitor",
    "75": "semantic config diff across machines, with a curated effect table",
}

DEDUP = [
    ("env-audit", "env-audit, envcheck, envdiff, env-diff, envcheck, local secrets drift checker, "
                  "environment variable auditor ×3, env drift detector, `.env` sanity checker"),
    ("dep-health", "dependency health/vitality auditor, bus factor auditor, PyPI archaeology, "
                   "abandonware watchdog, holistic dependency auditor"),
    ("dep-why", "dep-why, depweight, `pipdeptree`-style reverse tree"),
    ("upgrade-impact", "dependency impact analyzer, upgrade-impact predictor, `upgradenotes`"),
    ("git-changelog", "git-changelog ×2, changelog-from-prs, Git-to-changelog AI, release notes tool"),
    ("log-fold", "log-fold, logcluster, AI log dedupe"),
    ("cron-explain", "cron-explain, cronwhy, cronx"),
    ("download-sort", "download-sort, file-organizer, rule-based sorter"),
    ("env-stamp", "env-stamp, contextual reproducibility bundler (env half)"),
    ("bug-bundle", "bug-bundle, contextual reproducibility bundler"),
    ("project-first-run", "project-first-run, onboarding generator, local sanity checker"),
    ("git-trim", "git-trim, git-prune-merged"),
    ("docker-cleanup", "docker-cleanup ×2"),
    ("aws-cost-estimator", "aws-cost-estimator ×2"),
    ("read-later", "read-it-later CLI, `mark` bookmarks"),
    ("zettel", "Zettelkasten CLI, digital garden indexer"),
    ("mockapi", "mockapi, Pydantic-to-mock-server, spec mock server"),
    ("schema-faker", "API payload generator, pydantic/OpenAPI fake data"),
    ("api-runner", "api sequence runner, api-client-cli"),
    ("prompt-vault", "AI prompt manager, local prompt versioning tool"),
    ("prompt-bench", "local LLM prompt benchmarker"),
    ("jsonl-schema", "jsonl-schema, schemadiff (JSON half)"),
    ("system-monitor", "system-monitor-cli, host dashboard"),
    ("shell-history-redactor", "shell-history-redactor, personal CLI telemetry cleaner"),
]


def parse_spec(path: pathlib.Path) -> dict:
    """Pull the header fields out of one spec file."""
    text = path.read_text(encoding="utf-8")
    title = text.splitlines()[0].lstrip("# ").strip()
    meta, art = DIFFICULTY.search(text), PRIOR_ART.search(text)
    prior = re.sub(r"[^\w\s:/.+-]", "", art.group(1)).strip() if art else "?"
    return {
        "path": path.name,
        "title": title,
        "score": int(meta.group(1)) if meta else 0,
        "effort": meta.group(2).strip() if meta else "?",
        "prior": prior,
        "words": len(text.split()),
    }


def verdict(prior: str) -> str:
    """Map the prior-art header to a traffic light."""
    low = prior.lower()
    if "solved" in low or "already built" in low or "taken" in low or "crowded" in low:
        return "🔴 solved"
    if "partial" in low or "mostly" in low or "adjacent" in low or "fragmented" in low or "thin" in low:
        return "🟡 partial"
    if "gap" in low or "near-gap" in low:
        return "🟢 gap"
    return "⚪ unclear"


def _label(row: dict) -> str:
    """Link text for a spec: the tool name, not the whole title."""
    after_dash = row["title"].split("—")[-1].strip()
    return after_dash.split("(")[0].strip().strip("`") or after_dash[:40]


def render_index() -> str:
    """Return INDEX.md as a string (no I/O). Deterministic."""
    rows = sorted((parse_spec(p) for p in IDEAS.glob("*.md")), key=lambda r: r["path"])
    missing = [r["path"] for r in rows if r["score"] == 0]
    if missing:
        raise ValueError(f"spec file(s) without a Difficulty header: {missing}")

    gaps = [r for r in rows if verdict(r["prior"]).startswith("🟢")]
    out: list[str] = []
    add = out.append

    add("# Idea index — merged, deduplicated, sorted by difficulty\n")
    add(f"**{len(rows)} specs written** (of {TOTAL_IDEAS} unique ideas after dedup) · "
        "target: Linux, Python 3.12+ · prior-art column verified against the live PyPI JSON API "
        "(see `arena/pypi_probe.py`).\n")
    add("Legend — 🟢 **gap**: nothing comparable on PyPI, build it · 🟡 **partial**: something adjacent exists, "
        "pivot needed · 🔴 **solved**: a maintained tool already does this, read the pivot or skip.\n")
    add("**Difficulty** = how hard it is to build *well* (correctness risk, edge cases, integration surface), "
        "not how long it takes; **effort** is the separate calendar estimate for a working MVP. Files are numbered "
        "in difficulty order, easiest first, so `01` is a weekend and `80` is a term project.\n")
    add("Every file contains: problem, prior art with versions/dates, the pivot (if any), CLI surface, "
        "module layout, data model, dependencies, build order, test strategy, pitfalls, and a definition of done.\n")

    add("## Written\n")
    add("| # | File | Difficulty | Effort | Prior art | Words |")
    add("|---|---|---|---|---|---|")
    for r in rows:
        title = r["title"].split("—", 1)[-1].strip() if "—" in r["title"] else r["title"]
        add(f"| {r['path'][:2]} | [{title}](ideas/{r['path']}) | {r['score']}/10 | {r['effort']} "
            f"| {verdict(r['prior'])} | {r['words']} |")
    add("")

    add("## The real gaps — where nothing comparable exists\n")
    add("If you only build a few things, these are the ones with no maintained equivalent on PyPI "
        "(easiest first):\n")
    add("| # | Idea | Difficulty | Why it's open |")
    add("|---|---|---|---|")
    for r in gaps:
        add(f"| {r['path'][:2]} | [`{_label(r)}`](ideas/{r['path']}) | {r['score']}/10 "
            f"| {GAP_WHY.get(r['path'][:2], 'no maintained equivalent')} |")
    add("")

    add("## Dedup map\n")
    add("The source list had 115 entries; these collapsed into one idea each:\n")
    add("| Merged idea | Source entries |")
    add("|---|---|")
    for name, sources in DEDUP:
        add(f"| `{name}` | {sources} |")
    add("")

    add("## How prior art was verified\n")
    add("A script queried `https://pypi.org/pypi/<name>/json` for ~250 candidate and reference package names, "
        "recording existence, latest version, last upload date, and summary (`arena/pypi_probe.py`). "
        "Where a better-known non-PyPI tool exists (`age`, `git-cliff`, `prism`, `hurl`, `infracost`), it is named "
        "even though it isn't on PyPI. Version numbers and dates quoted in the files come from that probe run.\n")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    rendered = render_index()
    if "--check" in argv:
        current = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
        if current != rendered:
            print("INDEX.md is stale — run: python3 arena/build_index.py", file=sys.stderr)
            return 1
        print("INDEX.md is up to date")
        return 0
    INDEX.write_text(rendered, encoding="utf-8")
    rows = sorted(IDEAS.glob("*.md"))
    print(f"wrote INDEX.md: {len(rows)} specs, {sum(len(p.read_text().split()) for p in rows):,} words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
