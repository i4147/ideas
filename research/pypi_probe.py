import json, urllib.request, concurrent.futures as cf

NAMES = """env-stamp envstamp env-audit envaudit envcheck envdiff env-sync cron-explain cronexplain
cronwhy cronx croniter shell-history-redactor history-redactor download-sort downloadsort file-organizer
git-trim gittrim git-prune-merged csv-contract csvcontract log-fold logfold logcluster logslice log-tailer
logtail todo-age todoage standup repo-budget repobudget archdiff archlint reprozip dockerignore-doctor whyport
sqlite-scout sqlitescout fixture-slim dep-why depwhy depweight venv-diff venvdiff html2md-clip html2md schemadiff
jsonl-schema jsonlschema test-budget testbudget pytest-fixture-graph pyproject-doctor pyprojectdoctor pyproject-fmt
dotsync http-status-cli urlchecker backup-validator file-encryptor csvrepair csvkit cli-docs-generator
pre-commit-hooks-manager codec-bench shell2py reviewq api-to-csv config-doc db-query mark garden-index zettel
read-it-later readlater homeprobe ledger-import time-tracker password-manager-cli system-monitor-cli network-scanner
api-client-cli jira-cli aws-cost-estimator docker-cleanup markdown-lint-cli pip-license-check pip-audit osv-scanner
git-changelog dep-health dephealth upgrade-impact upgradenotes prompt-vault prompt-bench promptfoo ai-log-rca
semantic-secret-scanner doc-diff import-graph pydeps grimp bug-bundle bugbundle project-first-run readme-gap
release-captain codebase-navigator orphaned-script-finder ai-session-sanitizer api-sequence-runner mockapi
schema-faker polyfactory git-rewrite-history gh-issue-triage multitail buku watson glances beancount pass age
hurl git-cliff gitchangelog pip-licenses licensecheck liccheck mdl pymarkdown infracost docker-gc strip-nondeterminism
lzbench python-dotenv typer click rich psutil dulwich lark-parser babel packaging cyclonedx-py sqlglot""".split()

def probe(n):
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{n}/json", timeout=20) as r:
            d = json.load(r)
        info = d["info"]
        rels = [v for v in d["releases"].values() if v]
        last = max((f["upload_time"][:10] for v in rels for f in v), default="?")
        return n, True, last, (info.get("summary") or "")[:90].replace("\n", " "), info.get("version")
    except urllib.error.HTTPError as e:
        return n, False, "", f"HTTP {e.code}", ""
    except Exception as e:
        return n, None, "", type(e).__name__, ""

with cf.ThreadPoolExecutor(24) as ex:
    rows = list(ex.map(probe, NAMES))
rows.sort(key=lambda r: (not r[1], r[0]))
for n, exists, last, summ, ver in rows:
    print(("TAKEN " if exists else "free  ") + f"{n:26} {last:10} {ver:10} {summ}")
