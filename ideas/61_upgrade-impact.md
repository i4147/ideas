# 61 — `upgrade-impact` (which dependency upgrade will break *your* code)

> **Difficulty 5/10** · **Effort ~6 days** · **Tier: hard**
> **Prior art: ❌ name already taken** — PyPI `upgrade-impact` 0.2.0 (*"Find dependency upgrade breakages in your Python code"*), plus `upgradenotes`, `dependabot`/`renovate` (version bumps + CI as the oracle), `ruff`'s `UP` rules (stdlib deprecations), `libcst`/`griffe` (API introspection), `grep.app`/`github code search` (who else uses this symbol), `pyupgrade`, `django-upgrade` (framework-specific codemods).
> **Pivot required?** Yes — the existing tool exists but is 0.2.0 with no API diffing; that gap is the product.

## The problem

Renovate opens 12 PRs: `requests 2.31 → 2.32`, `pydantic 1.10 → 2.9`, `sqlalchemy 1.4 → 2.0`, 9 others. CI runs 25 minutes per PR, so merging is a day of waiting. What you want before the PR queue: *"pydantic 2 will break 41 call sites in 12 files; the rest are safe"*.

## The pivot: diff the installed API, then match against your call sites

Do not parse changelogs with an LLM and guess. Do this, which is deterministic:

1. **Fetch both versions** of the distribution into a temp dir *without touching your environment*: `pip download --no-deps --only-binary=:all: pkg==old` and `==new`, then unpack the wheel (`zipfile`) — you get the shipped `.py`/`.pyi` files.
2. **Extract the public API** from each with `ast`/`griffe`: top-level names, classes, functions, their parameter lists (names, defaults, kind), attributes on classes, and `__all__` where present. For C extensions without stubs, fall back to `pydoc`-style import in a subprocess with a *synthetic* environment (riskier; behind `--allow-import`).
3. **Diff the API** into change records:
   ```python
   {"kind": "param_removed", "symbol": "Client.__init__", "param": "timeout",
    "severity": "breaking", "replacement": "request_timeout"}
   {"kind": "default_changed", "symbol": "Client.timeout", "old": 5, "new": 30, "severity": "behavioural"}
   {"kind": "symbol_removed", "symbol": "pkg.utils.dumps", "severity": "breaking"}
   ```
   Classify: removed/renamed symbol → breaking; parameter removed/renamed or becoming keyword-only/required → breaking; new required parameter → breaking; default changed, new exception type, return-type change → behavioural (worth a warning); pure additions → compatible.
4. **Match against your code**: import graph + call sites (`ast`), resolving `from pkg import Client` → `Client(` usages, and `pkg.Client(` attribute calls. Report `file:line` per affected call, with the specific argument when it's an argument-level change (`src/api.py:41 passes timeout=`).
5. **Rank** by (breaking + reachable + call count), so the report answers "merge these 9 now, do these 3 manually".

The output that makes it worth installing:

```
$ upgrade-impact --from requirements.lock@main --entry src/
pydantic 1.10.13 → 2.9.2   BREAKING (41 sites, 12 files)
  ✗ BaseModel.dict() removed → model_dump()        src/api/serializers.py:88, 102, 141 …
  ✗ validator decorator → field_validator          src/models/user.py:22
  ✓ 38 other call sites unaffected
requests 2.31.0 → 2.32.3   compatible
sqlalchemy 1.4.52 → 2.0.36 BREAKING (18 sites)
  ✗ engine.execute() removed → conn.execute(text())  src/db.py:31,44
VERDICT  3 PRs safe to auto-merge · 2 need work (est. 4 files)
```

## Build

```
upgrade_impact/
  fetch.py     # pip download into tmp, wheel unpack, cache by (name, version)
  apidiff.py   # ast/griffe API model + diff -> Change[]
  callsites.py # import graph + call resolution -> Site[]
  impact.py    # join(Change, Site) -> Impact, ranking
  render.py    # table/json/github annotations
```

Optional `--changelog` fetches the project's changelog URL (PyPI metadata) and links the relevant section per change — as a *link*, never as the source of truth.

## Tests

Build two tiny local wheels (`build` in-process) `demo-1.0` and `demo-2.0` with known API changes (removed function, renamed param, changed default, added required param, new class), install none of them, and assert the generated change records. Call-site fixtures: `from demo import f; f(x=1)`, `import demo; demo.f(1)`, an aliased import, a call inside a lambda, a call in a test file (report but rank lower), and a dynamic `getattr(demo, name)` (must be reported as "unverifiable").

## Pitfalls

- Private APIs (`_internal`) change without notice — default to ignoring underscore names, with `--include-private`.
- Some breaking changes are *behavioural only* (a regex tweak, a default encoding change): you cannot detect those statically. Say so in the report, and recommend running the test suite for `behavioural` changes.
- Dynamic dispatch makes call-site matching incomplete: cap the claim at "no static call sites found", never "safe".
- Wheels for the *current* platform only: `pip download --python-version 3.12 --only-binary=:all:` matters when a project ships per-version wheels.
- Cache downloaded wheels (`~/.cache/upgrade-impact/<name>-<version>.whl`) — CI will run this repeatedly.
- Don't import the old and new package in one process (module-level state, C extensions): subprocess per version.

## Definition of done

On a real repo, the tool correctly predicts that 3 of 12 pending upgrades need manual work, naming the files and call sites, before CI runs — and is wrong only about behavioural changes, which it labels as such.
