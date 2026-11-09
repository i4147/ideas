# 80 — `semantic-secret-scan` (find secrets that don't look like secrets)

> **Difficulty 7/10** · **Effort ~9 days** · **Tier: hard**
> **Prior art: ⚠️ mature in the regex/entropy direction, empty in the semantic one** — `gitleaks`, `trufflehog` (also *verifies* credentials against providers), `detect-secrets` 1.5.0 (entropy + plugins + baselines), `ggshield` (GitGuardian), `secretlint`, `semgrep` custom rules, `noseyparker` (Rust, high-performance), `git-secrets`.
> **Pivot required?** Yes — and it must beat a very good baseline on **precision**, or it is worse than useless.

## The problem

Regex scanners find `AKIA…`, `ghp_…`, JWTs, and high-entropy strings. They miss:

```python
# not a known prefix, medium entropy, but it IS a production credential
GATEWAY = "gw_live_7f3a91c2"          # internal service token, 16 chars, entropy 3.1
headers["X-Sig"] = sign(payload, b"9c1f...")   # HMAC key inline in code
DB = {"host": "db.internal", "user": "svc", "pass": "correct-horse-battery"}
```

And they over-report: test fixtures, documentation examples (`sk_test_…`), hash constants, base64 images.

A local model that uses **context** — variable names, surrounding code, whether the value is passed to an auth header, whether the file is a test — could in principle get both better. That's the pitch. The engineering problem is proving it.

## Design: a hybrid where the model is a *ranker*, not the detector

Never let the LLM be the only line of defence (a false negative leaks a credential). Architecture:

1. **Candidate generation (recall-first, cheap, deterministic)**: run your existing detectors as generators — `detect-secrets` plugins, `gitleaks` rules, entropy windows, plus custom *context* rules: assignment of a string literal to a name matching `(?i)(key|secret|token|pass|cred|sig|hmac|auth)` where the value length ≥ 12 and is not a placeholder (`xxx`, `<...>`, `${...}`, `changeme`, `example`), plus "value flows into an auth header/signature call" (AST dataflow, one hop).
2. **Feature extraction per candidate**: entropy, length, charset classes, identifier name tokens, the AST context (call/argument/assignment/dict value), file type/role (test, docs, fixture, vendored, generated), presence of a neighbouring comment, whether it's checked into git and in a commit (vs untracked), and provider hints (address pattern `db.`, URL with userinfo).
3. **Ranking**: deterministic score first (logistic weights you can inspect), then **optional** local LLM as a second opinion for the ambiguous band (score 0.3–0.7) — it sees a *redacted 20-line window*, never the whole file.
4. **Verification** (`--verify`, opt-in): for providers with safe read-only endpoints (GitHub `/user`, GitLab `/user`, Stripe `/v1/balance`), confirm whether a candidate is live. `trufflehog` does this well — do not reimplement a dozen verifiers; support 3–4 and delegate to `trufflehog` when installed.
5. **Never** auto-rotate or auto-delete. Output a report and a rotation checklist (the value has to be assumed compromised the moment it hit git).

## Measuring it honestly (the whole project)

The only way this earns trust is a **labelled corpus and published precision/recall** against `detect-secrets` and `gitleaks`:

- Build a corpus of ~400 files: 100 real-ish planted secrets (generated with provider-shaped formats + realistic context), 200 lookalikes (test fixtures, docs placeholders, hashes, encrypted blobs, base64 assets), 100 clean files of real code.
- Report a confusion matrix **per detector** and for the hybrid, plus the ambiguity band's contribution.
- The honest expected result: the semantic layer adds maybe 10–15 points of recall on custom secrets and *loses* precision unless the false-positive controller is good. Publish that.

```
$ secret-scan . --report
CANDIDATES 128 → CONFIRMED 7 · LIKELY 4 · LIKELY-NOT 117
HIGH   src/gateway/client.py:14   gateway token (custom prefix) conf 0.91
       "gw_live_7f3a91c2" · 16 chars · entropy 3.1 · flows to X-API-Key header · live? yes (verified)
HIGH   deploy/hmac.py:31          inline HMAC key (32 bytes hex) · used in sign() · rot needed
MEDIUM tests/fixtures/auth.py:8   looks like a token but file is a test fixture + placeholder pattern
SUPPRESSED 12 entropy hits in base64 assets, 3 in vendored/, 1 known hash constant
BASELINE vs detect-secrets: +15% recall, -2% precision (see report.md)
```

## CLI

```bash
secret-scan . [--staged | --since HEAD~20 | --all-history]
secret-scan --report --json --fail-on high
secret-scan baseline update           # accept known FPs, stored with reasons + expiry (see file 04)
secret-scan explain src/x.py:14       # full feature breakdown, deterministically
```

## Implementation

```
secret_scan/
  generate.py  # candidates from detectors + context rules (AST one-hop dataflow)
  features.py  # entropy, identifiers, AST context, file role, git state
  rank.py      # transparent logistic scorer (weights in a readable YAML) 
  llm.py       # optional local model for the ambiguous band; redacted window; strict JSON out
  verify.py    # 3-4 provider checks, opt-in, cached
  report.py    # table/json/sarif, baseline handling
```

Model use must be *cached* by window hash and *bounded* (a 5,000-file repo cannot make 5,000 LLM calls): only the ambiguous band, capped at `--max-llm 200`, with a clear "N candidates not model-reviewed" line.

## Tests

The labelled fixture corpus is the test suite (checked in as generated files with a manifest, not real secrets). Assert: recall on planted custom secrets ≥ the target, precision on lookalikes, determinism with the LLM stubbed (fake server returning fixed JSON), graceful behaviour when the model is absent (`--no-llm`), that the redacted window sent to the model contains no candidate value verbatim, baseline suppression with expiry, and SARIF output validity. Also test the git-history mode with a fixture repo where the secret was deleted in a later commit (must still be found).

## Pitfalls

- **The value must never be logged.** Reports show a fingerprint (`sha256[0:8]`), length, and location — never the secret. This is non-negotiable: the scanner becomes the leak otherwise.
- Entropy thresholds are provider-specific; a 16-char base32 token has ~3.1 bits/char and is *real*, so don't threshold it away.
- Test fixtures are the dominant false-positive class; file-role detection (path, `conftest.py`, `fixtures/`, `docs/`) must be first-class, not an afterthought.
- Deleting a secret from the working tree doesn't revoke it: always print the rotation checklist and the "assume compromised" line.
- LLM false *negatives* are invisible; never let the model suppress a high-confidence deterministic finding.
- Don't scan binaries/base64 blobs with entropy rules; classify file type first.

## Definition of done

On the 400-file labelled corpus, the hybrid beats `detect-secrets` on recall for custom secrets by ≥10 points at ≤3 points of precision cost, every finding is explainable via `--explain`, no secret value ever appears in output, and the report is SARIF-loadable in CI.
