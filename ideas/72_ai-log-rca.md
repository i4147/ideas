# 72 — `log-rca` (root-cause summary for a huge log)

> **Difficulty 6/10** · **Effort ~7 days** · **Tier: hard**
> **Prior art: ⚠️ partial** — `logai` (Salesforce, research-grade anomaly detection), `llm`/`mods`/`aichat`/`sgpt` (generic LLM pipes, no log structure), `ollama` (local models), `lnav` (manual analysis), `logreduce`, `drain3` (templating), `kubectl-ai`-style add-ons, vendor features (Sentry, Datadog RCA — cloud).
> **Pivot required?** Yes — "pipe a log into an LLM" is a one-liner and produces confident nonsense; the product is **deterministic reduction before generation**, plus evidence.

## The problem

A 900 MB log, one incident. You want: what actually failed, where, when it started, what changed, and what to try. Naively truncating to 8,000 tokens loses the error (it's at byte 700 MB) and the model hallucinates a diagnosis from the surrounding noise.

## The design principle: the model never sees the raw log

Pipeline, with every stage deterministic and inspectable:

1. **Parse & classify** (`--format auto`): detect JSON lines vs plain text vs logfmt; extract timestamp, level, logger, message, exception type, and a stable `source` (file/service). Discard DEBUG/TRACE unless `--include-debug`.
2. **Reduce**: template the messages (reuse the masking/Drain approach from file 21), then produce a **ranked digest**, not a sample:
   - first occurrence and last occurrence of each template,
   - counts and rate per minute (a spike matters more than a count),
   - the exception *chains*: group by exception type + the top frame of the traceback (this is the key insight — 4,000 `ConnectionError`s are usually one root exception),
   - temporality: which template *appeared first* before the cascade (RCA is mostly ordering),
   - context lines around the first occurrence of the top 3 templates (with `logslice`-style buffering).
3. **Budget**: assemble a prompt of ≤ `--max-tokens` (default 6,000) from the digest only: top 10 exceptions, top 10 templates by novelty×rate, the 5-minute window histogram, and the first occurrence with 20 lines of context. Print the prompt with `--show-prompt`.
4. **Generate**: call a **local** model by default (`ollama` at `127.0.0.1:11434`, `--model llama3.1:8b`) or an API (`--provider openai|anthropic` with a key from the environment). Require citations: instruct the model to reference template ids (`T3`, `T7`), then **validate** that every cited id exists and that quoted lines appear verbatim in the digest. Drop unsupported claims and mark them.
5. **Explain the diff** (`--baseline previous.log`): "these 3 templates are new since the last good run" — the single most useful RCA signal, and fully deterministic.

## Output

```
ROOT CAUSE (high confidence, 3 cited templates)
  T1  psycopg.OperationalError: connection to server at "db" (10.0.3.7) port 5432 failed:
      FATAL: sorry, too many clients already            1,204×  first 09:12:04  last 10:48:31
      ↑ appears 4s before every other error template
  T4  requests.exceptions.ConnectionError (cascades, 3,190×, from api→db retries)
  T9  worker timeout after 30s (symptom, 412×)
TIMELINE
  09:11:58  deploy of db-pooler v2.3 (from your --changes diff, if provided)
  09:12:04  first FATAL: too many clients
  09:12:08  api errors begin (cascade)
  10:48:31  last occurrence (incident end)
HYPOTHESIS / NEXT STEPS (model-generated, flagged)
  - max_connections exhaustion: check pooler max_client_conn; 4s lag suggests the pooler, not the DB.
  - Verify with: `select count(*) from pg_stat_activity;`
EVIDENCE  9 of 9 citations verified against the digest · 2 claims dropped as unsupported
```

## Implementation

```
log_rca/
  parse.py    # format detection, record assembly (multi-line), level/source extraction
  reduce.py   # masking, templating, exception grouping, per-minute histogram, first-seen ordering
  budget.py   # digest -> prompt under a token budget (tiktoken optional; else chars/4 with a warning)
  cause.py    # llm providers (ollama HTTP, openai/anthropic), citation parsing + verification
  render.py   # report, --json, --show-prompt, --no-llm (digest only)
```

`--no-llm` is mandatory: it prints the deterministic digest, which is useful on its own and is the fallback when the model is unavailable. Ship it as the default in CI/sandboxed environments.

## Tests

Fixture logs: a synthetic incident (pool exhaustion → cascade) with 200k lines and a known root template; a log where the real error appears at line 190,000; a multi-line Java-style traceback; JSON logs with a nested `error.type`; a log with no errors at all (must say "no errors found", not invent). Tests assert: the root template is in the digest given a 6k budget (recall test), first-seen ordering is correct, every citation in a *recorded* model response is verified, and a fabricated citation is dropped. Use a **fake LLM server** (an `http.server` returning canned responses) so tests never call a model.

## Pitfalls

- Context windows: never let the digest overflow; count tokens for the target model, and fail loudly if the digest alone exceeds the budget.
- Hallucination is the default failure: the citation-verification gate is not optional, and the report must distinguish "observed" from "hypothesised".
- Privacy: logs contain PII/tokens. Local model by default, redaction before any API call (reuse file 22), `--redact strict` on by default for API providers, and a printed warning listing exactly what will be sent.
- Sampling must be *stratified* by time and template, never "first N lines".
- Zone: timestamps in logs are often naive — detect the offset from the log or require `--tz`; a wrong tz makes a timeline lie.
- Don't ship a model. Depend on `ollama` being present; degrade to `--no-llm` with a clear message.

## Definition of done

On a 200k-line incident log, the digest alone (no LLM) identifies the root template and the cascade order, and the LLM report has zero unverified citations on the fixture suite.
