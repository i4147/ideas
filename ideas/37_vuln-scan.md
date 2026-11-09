# 37 — `vuln-scan` (dependency vulnerability audit)

> **Difficulty 3/10** · **Effort ~1 day** · **Tier: warm-up**
> **Prior art: ❌ fully solved** — `pip-audit` (2.10.1, PyPA, OSV + PyPI advisory DB, `--fix`, lockfile support, GitHub Action), `safety` (commercial), `osv-scanner` (Google, all ecosystems), Dependabot, `trivy`, `grype`, `cyclonedx-bom` + SBOM scanning.
> **Pivot required?** Yes — and it's the only interesting problem left in this space: **reachability**.

## The problem

Every team already gets vulnerability alerts, and they ignore them, because the list is 40 items long and 35 of them are in code paths they never call. `pip-audit` is correct, fast, free, and integrated (it can even fix). Rebuilding it is a waste of a semester.

## The unsolved problem: reachability triage

`urllib3` CVE in a code path that only talks to `http://localhost`? `pyyaml` `load()` RCE where your code only calls `safe_load`? `numpy` overflow in a Fortran routine you never touch? These are the 35 ignored items. What developers need is:

```
$ vulnreach scan
14 advisories reported → 3 actionable

HIGH   jinja2 3.1.2  CVE-2024-22195 (XSS via |attr filter)
       reachable: src/render/emails.py:88 calls Template(...).render() with user data ✗
HIGH   pyyaml 5.4.1  CVE-2020-1747 (arbitrary code execution via full_load)
       reachable: src/config.py:41 uses yaml.load(...) (not safe_load) ✗
MEDIUM requests 2.25  CVE-2023-32681 (Proxy-Authorization leak on redirect)
       reachable: only through httpx via requests-toolbelt (transitive, unused code path) ?
SUPPRESSED 12 advisories not reachable from any entry point (analysed statically)
```

The heuristic stack, in order of confidence:

1. **Package-level**: is the vulnerable package imported at all? (`grimp`/`ast` import graph). Not imported → suppress with evidence.
2. **Symbol-level**: does the advisory name a function (`yaml.load`, `jinja2.filters.do_attr`, `PIL.ImageMath.eval`)? Parse the advisory's details/aliases; check whether your code calls that symbol (AST call-site scan with a simple resolution rule: `from yaml import load` → `load(`).
3. **Config-level**: some advisories are only triggerable with a setting (`yaml.load` with a `Loader`, `requests` with redirects + proxy, Django `DEBUG=True`). Extract a few known predicates per advisory family and check the repo.
4. **Everything else → "unknown, review"**, never silently suppressed.

Ship the suppression list as a file (`.vulnreach.toml`) with a *reason* and an expiry, so it's auditable:

```toml
[[suppress]]
id = "CVE-2023-32681"; package = "requests"
reason = "proxy auth only; we do not use proxies"
until = "2027-01-01"
```

## Build

```
vulnreach/
  audit.py     # shell out to `pip-audit --format json` OR call OSV API directly (no reimplementation of advisory data)
  imports.py   # ast/grimp import graph + call-site extraction
  advisers.py  # advisory -> affected symbols/predicates (small curated map + heuristics from description text)
  report.py    # actionable / unknown / suppressed sections, --json, exit codes
```

**Do not rebuild the advisory database.** Call `pip-audit --format json -r requirements.txt` (or the OSV API `POST /v1/querybatch`) and treat it as the source of truth. Your contribution is the reachability layer — which is a genuine research-y product with a clear value story ("14 advisories → 3 that matter").

## Tests

Fixture projects with: `yaml.load` vs `yaml.safe_load`, an import of a vulnerable package in a `try/except ImportError` block, a dynamic import (`importlib.import_module("PIL.ImageMath")`), a call inside a `if TYPE_CHECKING` block (not reachable at runtime), and a transitive-only package. Advisories are fixture JSON, so tests never touch the network.

## Pitfalls

- Never claim "not vulnerable" — say "not statically reachable from analysed entry points", with the analysis limits stated. This tool will be read by security people who will tear it apart otherwise.
- Dynamic dispatch (`getattr(module, name)`, plugin loading) breaks symbol analysis: mark the project as "partially analysed" and keep those advisories visible.
- Keep evaluation time bounded; a 500-package environment × 30 advisories must stay under 20 s.
- Suppression expiry must produce a warning, not silence — expired suppressions are how real risk hides.

## Definition of done

On a real project with 14 advisories, the report has ≤5 actionable items each with a file:line, and the "unknown" bucket is honestly labelled. Otherwise use `pip-audit`.
