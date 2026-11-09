# 52 — `readme-gap` (what's missing from the README, and what's stale)

> **Difficulty 4/10** · **Effort ~4 days** · **Tier: medium**
> **Prior art: ⚠️ partial** — `readme-ai` (generates a README from repo structure, LLM-assisted), `readme-md-generator`, `standard-readme` (spec + linter), `markdown-link-check`, `doc-detective`/`pytest-codeblocks` (executable doc snippets), `vale` (prose linting), `repo-ratings`.
> **Pivot required?** Yes — do not *generate* a README (LLM generators own that). *Audit* the existing one against the repo.

## The problem

A README is the most-read file in a repo and the least maintained. Typical gaps:

- documents flags that no longer exist, or misses half of `--help`;
- install steps that no longer work (wrong package name after a rename);
- a "Supported Python versions" claim that contradicts `requires-python`;
- badges pointing at a moved CI workflow;
- no licence section, or a licence that contradicts `LICENSE`;
- copy-pasted example code that raises `ImportError` today.

All of these are *checkable*. That's the tool: a verdict per claim, with evidence.

```
$ readme-gap .
CONTRADICTIONS
  ✗ "Requires Python 3.8+"  → pyproject requires-python = ">=3.11"
  ✗ badge: workflow "ci.yml" not found (workflows: test.yml, release.yml)
  ✗ install line `pip install shopapi` → package name is `shop-api`; PyPI has neither
  ✗ example uses `Client(timeout=...)`; signature is `Client(*, request_timeout)`
MISSING
  - no usage example for the CLI (24 subcommands exist)
  - no licence section (LICENSE file: MIT)
  - no "Development" section (repo has 14 make targets, a pre-commit config, docker compose)
STALE
  - 3 relative links broken (docs/install.md, docs/api.md#v2, CONTRIBUTING.md)
OK
  - 41 internal links resolve · description matches pyproject summary · code fence languages valid
```

## How to check each class

| Claim | Verification |
|---|---|
| CLI flags/subcommands | parse the README's `bash` blocks for invocations of the project's own entry point, then compare against live `--help` output (reuse file 09's parser) — or import the Typer/Click app and introspect (`--inspect-app pkg.cli:app`) |
| Python version | `requires-python` vs README text (`re.search(r'Python\s*(\d\.\d+)\+')`) |
| Package name / install command | `pyproject [project].name` and PyPI JSON existence |
| Badges | parse `img.shields.io/github/workflow/status/{org}/{repo}/{workflow}` and `github.com/{o}/{r}/actions/workflows/{file}` URLs; `git ls-files .github/workflows` |
| Links | collect `[x](y)` and `![x](y)`; relative → resolve against repo (and heading anchors, see file 17); absolute → optional HEAD check with `--online` |
| Code examples | parse `python` fenced blocks, `ast.parse` them (syntax), then `--exec-examples` (opt-in, sandboxed) to catch import/signature errors |
| Licence | `LICENSE` file SPDX detection vs the README's licence section |
| Commands in prose (`make test`) | verify the target exists in `Makefile`/`justfile`/`pyproject scripts` |

`--inspect-app` is the strong feature: importing a Typer/argparse app object and comparing its commands to the documented ones catches real drift, and needs no execution of the CLI.

## Safety

Executing README code is the only dangerous part. It must be: opt-in (`--exec-examples`), in a subprocess with a timeout, `cwd` = a temp copy of the repo, network disabled via a warning (not enforceable in plain Python — say so), and never for snippets that contain `rm`, `sudo`, `curl | sh`, or `os.system`. Default mode is static only.

## Implementation

```
readme_gap/
  parse_md.py    # markdown-it-py -> blocks with positions (for file:line output)
  claims.py      # extract structured claims from prose/code/badges
  probes.py      # each claim type -> verifier (repo, pyproject, PyPI, app introspection)
  report.py      # categories, exit codes (0 clean, 1 contradictions)
  cli.py
```

Vale/`readme-ai` are adjacent and complementary — say so in the README; overlap is in "generate", not "audit".

## Tests

Fixture repos + READMEs, one per finding class, including: a README with a valid claim that must NOT be flagged (false-positive control is the main risk), a renamed package, a badge for a deleted workflow, a broken anchor, and a python block with valid syntax but a wrong signature. Assert `--exec-examples` never runs when `--dry-run`.

## Pitfalls

- READMEs legitimately describe *other* tools' CLIs (`docker run …`) — never flag those; only the project's own entry points.
- Version claims are often deliberately vague ("Python 3.9+ or newer"); only flag contradictions, not sloppiness.
- `CHANGELOG.md`/`docs/` often hold the real docs — scan those for the "missing section" check, or you'll demand duplicated content.
- Do not rewrite the README. Output a patch suggestion (`--patch`) at most.
- Emoji/shortcode and HTML in Markdown break naive regex parsing — use a real parser.

## Definition of done

On 10 real repos, ≥1 true contradiction found in 7 of them, near-zero false positives on the control fixtures, and CI-friendly exit codes.
