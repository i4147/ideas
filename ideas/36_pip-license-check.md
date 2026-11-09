# 36 — `pip-license-check` (dependency licence compliance)

> **Difficulty 3/10** · **Effort ~1 day** · **Tier: warm-up**
> **Prior art: ❌ fully solved** — `pip-licenses` (5.5.5, actively maintained, JSON/CSV/Markdown output, `--fail-on`), `licensecheck` (2026.0.8, licence compatibility against a policy), `liccheck` (0.9.2, `requirements.txt` + policy file), `cyclonedx-bom` (SBOM), `pip-audit`'s licence sibling in dev, `fossa`/`scanCode` (multi-language).
> **Verdict: don't build the lister.** There's exactly one gap and it's small.

## What already exists

```bash
pip-licenses --format=markdown --with-urls --order=license
pip-licenses --fail-on "GPL;AGPL" --packages requests,flask
licensecheck --format=json          # compatibility rules, SPDX expression parsing
liccheck -s setup.cfg               # policy: unauthorized = GPL-3.0
```

`pip-licenses` reads installed distributions' metadata, handles classifiers and `License-Expression`, dedupes, and exits non-zero on a deny list. `licensecheck` goes further: it parses SPDX expressions and evaluates them against your project's licence with an allow/deny policy — the actual legal question, not just a list.

## The remaining gap (small, but real)

Metadata is frequently *wrong or missing*: packages with `License: UNKNOWN`, classifiers that contradict `License-Expression`, or a licence file that is the only evidence (`LICENSE`, `COPYING`, `NOTICE` in `dist-info`). A tool that classifies from evidence — SPDX identifier detection by text matching (the SPDX licence list + `licensee`-style fingerprints), plus the `License-File` core-metadata field — and reports *confidence* is marginally useful.

Second small gap: **licence drift across a lockfile change** — "these 3 new transitive dependencies are AGPL" at review time, rather than a full re-audit. That is a 100-line addition to `licensecheck`, not a package.

## Recommendation

Contribute the two gaps upstream rather than publishing `pip-license-check`:

1. Evidence-based classification with confidence into `licensecheck` (it already has the policy engine).
2. A `--diff-lockfile old.lock new.lock` mode into `pip-licenses` or `licensecheck`, with a GitHub annotation per new package.

If the group insists on a standalone tool, scope it as `licence-diff`:

```bash
licence-diff --from uv.lock@main --to uv.lock --policy licences.toml
ADDED     httpx 0.28  BSD-3-Clause   ok
ADDED     some-agpl-lib 2.1  AGPL-3.0-or-later   DENIED (policy: denial for distribution)
CHANGED   charset-normalizer 3.3 → 3.4  MIT → MIT  ok
```

## If built, the details that matter

- Read `importlib.metadata` for installed envs and parse lockfiles directly (`uv.lock` TOML, `poetry.lock` TOML, `requirements.txt` with hashes) — do **not** require installation.
- Normalise everything to SPDX identifiers; `MIT`, `mit`, `MIT License`, `License :: OSI Approved :: MIT License` must collapse. Handle `MIT AND Apache-2.0`, `GPL-2.0-or-later`, and `UNKNOWN`.
- Policy is per-use-case, not absolute: GPL is fine for an internal tool, a problem for a distributed wheel. Make the policy file say `distribution = "saas" | "wheel" | "internal"` and change the rules accordingly — that nuance is what legal reviews actually need.
- Always emit the full text location (`dist-info/licenses/LICENSE`) so a human can check.

## Tests

Fixture `dist-info` directories (hand-built, not installed) covering: `License-Expression` only, classifiers only, `UNKNOWN` with an SPDX-recognisable LICENSE file, dual licence, and a non-SPDX custom licence. Assert normalisation and policy outcomes, including that an unknown licence is *not* silently allowed.

## Definition of done

If standalone: a lockfile diff annotates exactly the new packages with normalised licences and policy verdicts in under a second. Otherwise: two merged PRs upstream, which is worth more than the package.
