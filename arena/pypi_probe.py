#!/usr/bin/env python3
"""Prior-art probe: ask PyPI whether a name exists, and how alive it is.

This is the script that produced every version number and date quoted in
ideas/*.md.  It is deliberately dumb and dependency-free: one HTTPS GET per
name against the public JSON API, no auth, no caching between runs.

    python3 arena/pypi_probe.py                    # all names seen during the session
    python3 arena/pypi_probe.py env-stamp logfold  # specific names
    python3 arena/pypi_probe.py --extra            # the second batch (reference tools)
    python3 arena/pypi_probe.py --json out.json    # machine-readable

Exit code is always 0: "name is taken" is data, not an error.
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import json
import sys
import urllib.error
import urllib.request

# Candidate names for the 80 ideas (the words that would go in `pip install …`).
CANDIDATES = """
env-stamp envstamp env-audit envaudit envcheck envdiff env-sync cron-explain cronexplain
cronwhy cronx shell-history-redactor history-redactor download-sort downloadsort file-organizer
git-trim gittrim git-prune-merged csv-contract csvcontract log-fold logfold logcluster logslice
log-tailer logtail todo-age todoage standup repo-budget repobudget archdiff archlint reprozip
dockerignore-doctor whyport sqlite-scout sqlitescout fixture-slim dep-why depwhy depweight
venv-diff venvdiff html2md-clip html2md schemadiff jsonl-schema jsonlschema test-budget testbudget
pytest-fixture-graph pyproject-doctor pyprojectdoctor pyproject-fmt dotsync http-status-cli
urlchecker backup-validator file-encryptor csvrepair cli-docs-generator pre-commit-hooks-manager
codec-bench shell2py reviewq api-to-csv config-doc db-query mark garden-index zettel read-it-later
readlater homeprobe ledger-import time-tracker password-manager-cli system-monitor-cli
network-scanner api-client-cli jira-cli aws-cost-estimator docker-cleanup markdown-lint-cli
pip-license-check dep-health dephealth upgrade-impact upgradenotes prompt-vault prompt-bench
ai-log-rca semantic-secret-scanner doc-diff import-graph bug-bundle bugbundle project-first-run
readme-gap release-captain codebase-navigator orphaned-script-finder ai-session-sanitizer
api-sequence-runner mockapi schema-faker git-rewrite-history gh-issue-triage
""".split()

# Established tools cited as prior art — recorded so the specs can quote real versions.
EXTRA = """
age beancount buku click croniter csvkit diffoscope dulwich glances grimp hurl infracost
jsonschema jq lark-parser libcst licencecheck liccheck mdl multitail openapi-spec-validator
packaging pathspec pip-audit pip-licenses pipdeptree pip-requirements-parser platformdirs
polyfactory promptfoo psutil pydeps pymarkdown pytest-benchmark pytest-html pyinstrument radon
reprotest reprozip responses rich send2trash sqlglot strip-nondeterminism tree-sitter typer watson
yq cron-descriptor cronsim crontab cron-validator git-sweep git-branchless csvclean httpstat
khal taskwarrior wallabag readability archivebox rclone restic borgbackup duplicity detect-secrets
gitleaks shellhistory filelock tomli-w diffoscope hypothesis fakeredis vcrpy pyfakefs
pytest-timeout pytest-randomly protobuf osv cyclonedx-py scc cloc
""".split()

API = "https://pypi.org/pypi/{}/json"


def probe(name: str, timeout: float = 20.0) -> dict:
    """Return {'name', 'exists', 'last', 'version', 'summary'} for one package."""
    try:
        with urllib.request.urlopen(API.format(name), timeout=timeout) as response:
            data = json.load(response)
        files = [f for release in data["releases"].values() if release for f in release]
        last = max((f.get("upload_time", "")[:10] for f in files), default="?")
        info = data.get("info") or {}
        return {
            "name": name,
            "exists": True,
            "last": last,
            "version": info.get("version") or "",
            "summary": ((info.get("summary") or "").replace("\n", " "))[:90],
        }
    except urllib.error.HTTPError as exc:
        return {"name": name, "exists": exc.code != 404, "last": "", "version": "",
                "summary": f"HTTP {exc.code}"}
    except Exception as exc:                       # network hiccup: unknown, not "free"
        return {"name": name, "exists": None, "last": "", "version": "", "summary": type(exc).__name__}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="*", help="package names (default: all candidates)")
    parser.add_argument("--extra", action="store_true", help="also probe the reference-tool list")
    parser.add_argument("--all", action="store_true", help="candidates + extra")
    parser.add_argument("--json", metavar="PATH", help="write results as JSON")
    parser.add_argument("--threads", type=int, default=24)
    args = parser.parse_args(argv)

    names = list(dict.fromkeys(args.names))
    if not names or args.all or args.extra:
        names += [n for n in (CANDIDATES + (EXTRA if (args.all or args.extra) else [])) if n not in names]

    with futures.ThreadPoolExecutor(args.threads) as pool:
        rows = list(pool.map(probe, names))

    for row in sorted(rows, key=lambda r: (r["exists"] is not True, r["name"])):
        tag = "TAKEN " if row["exists"] else ("free  " if row["exists"] is False else "?     ")
        print(f"{tag} {row['name']:<28} {row['last']:<11} {row['version']:<12} {row['summary']}")

    taken = sum(1 for r in rows if r["exists"])
    print(f"\n{len(rows)} names · {taken} taken · {len(rows) - taken} free/unknown", file=sys.stderr)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, indent=2, sort_keys=True)
        print(f"wrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
