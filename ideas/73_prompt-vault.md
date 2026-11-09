# 73 — `prompt-vault` (versioned, runnable prompts)

> **Difficulty 6/10** · **Effort ~7 days** · **Tier: hard**
> **Prior art: ⚠️ crowded** — `promptfoo` (Node, the strong one: YAML test cases, assertions, providers, CI; the PyPI package is a thin wrapper), `langfuse`/`agenta`/`promptlayer` (SaaS prompt management), `dspy` (programmatic prompts), `promptflow` (Azure), `llm` (`-f` templates, `llm logs`), VS Code prompt files, `aichat` roles, plain git.
> **Merged from:** "unified AI prompt manager", "local LLM prompt versioning tool (git for prompts)".
> **Pivot required?** Yes — "git for prompts" is literally *a git repo with .md files*; the product must be execution + substitution + evaluation.

## The problem

Prompts live in four places: a Python f-string, a Notion doc, a Slack message, and someone's `~/prompts.txt`. When a prompt regresses ("it used to summarise correctly"), there's no version, no test, no diff. Prompt engineering without version control and evaluation is folklore.

## What already exists (and why "git for prompts" is not a product)

- `promptfoo` runs a matrix of prompts × models × test cases with assertions and a web UI, in CI. It is exactly this tool, in YAML, for Node users.
- `langfuse`/`promptlayer` version and serve prompts for **production apps** (with an SDK, tracing, cost).
- `llm -f prompt.md -s var value` gives templates + local logging in one command.

So the honest scope is the *gap between* them: a **file-first, Python-native runner with deterministic substitution and snapshot evaluation**, for developers who want prompts in git next to code, run against local models, with no server and no SaaS.

## Design

```
prompts/
  summarize/
    prompt.md            # the prompt, with {{variables}} and YAML front-matter
    meta.yaml            # model, temperature, max_tokens, version history notes
    cases/
      short.md           # input
      short.expected.md  # optional expected/ideal output (or a rubric)
    CHANGELOG.md
```

```bash
prompt-vault list
prompt-vault run summarize -i cases/short.md -s tone=brief
prompt-vault run summarize --model ollama:llama3.1:8b --json
prompt-vault eval summarize --models ollama:llama3.1:8b,ollama:qwen2.5:7b
prompt-vault diff summarize --from v3 --to v4      # rendered prompt diff + which variables changed
prompt-vault promote summarize --to v4             # tag in git, update meta.yaml
```

Substitution must be strict and typed: `{{var}}` (single braces are literal), `{{var:-default}}`, `{{> include.md}}` (nested includes with cycle detection), `{{#if var}}…{{/if}}`? — **no**, keep logic out; a prompt with conditionals belongs in code. Document that decision; it prevents the tool becoming a template language nobody can debug.

## Evaluation: the part that justifies the tool

Without evaluation this is a template runner. Design `eval` as:

1. **Deterministic checks** (no judge model): exact match, regex, JSON validity (`json.loads` + JSON Schema), length bounds, required keywords, forbidden phrases ("as an AI"), refusal detection, and output-language detection.
2. **Snapshot comparison**: run and hash outputs; a change in output for an unchanged prompt+model is a *drift event* (model update or non-determinism at `temperature>0`) — report it distinctly from a regression.
3. **Optional LLM-as-judge**: only with `--judge`, with a rubric file, and with the judge's disagreements surfaced rather than averaged; record the judge model + version in the report because a judge upgrade changes scores.
4. **Report**: a matrix (prompt × model × case) with pass/fail per assertion, latency, token counts, and cost estimate where a price is known. `--format junit` for CI, `--baseline` to compare a change against `main`.

## Why local-first matters here

Prompts and their test cases contain real customer text, code, and internal docs. Sending them to a SaaS prompt manager is often a compliance problem. Defaulting to `ollama` (and `--provider openai|anthropic` as opt-in) is a defensible position no cloud product can take.

## Implementation

```
prompt_vault/
  store.py    # discover prompt dirs, front-matter (YAML), case loading
  render.py   # strict substitution, includes, no logic
  providers/  # ollama (HTTP /api/chat), openai-compatible (base_url+key), anthropic
  asserts.py  # deterministic check registry (json, regex, keywords, length, refusal)
  eval.py     # matrix execution, concurrency limit, caching by (prompt hash, model, params)
  report.py   # table, json, junit
  cli.py
```

Caching keyed by `sha256(rendered_prompt + model + params + version)` makes re-runs cheap and makes "no change" trustworthy. Pin the model *version* in `meta.yaml` (`llama3.1:8b-instruct-q4_K_M`) — floating tags are the #1 cause of unreproducible evals.

## Tests

Golden prompt rendering: variables, defaults, includes, a cycle (must error), an unescaped `{` (literal), unicode. Provider tests against a **fake HTTP server** returning canned completions (assert request shape, system/user separation, temperature, stop sequences). Assert layer tests: valid/invalid JSON, regex, refusal detection (a canned "I can't help with that"), and that a cached run makes no HTTP calls (assert request count). Report: JUnit XML schema, cost math with a fixture price table.

## Pitfalls

- Non-determinism at `temperature>0` breaks snapshot eval: default to `temperature=0` for `eval` and say so.
- Never store API keys in prompt dirs; read from env, and redact them from `--json` reports.
- Token counting differs per model; use the model's own tokenizer where available, else label estimates.
- Retries and rate limits on free/local providers: bounded concurrency (`--concurrency 2` default) with backoff.
- Prompts in git are the version control: don't invent a database. `promote` = a git tag + a line in `CHANGELOG.md`.
- If a team already uses `promptfoo`, don't compete: support importing its YAML so migration is one command.

## Definition of done

A repo of 8 prompts with 3 cases each evaluates across 2 local models in under a minute, reports per-assertion pass/fail with latency, and `prompt-vault diff --from v3` shows exactly what changed in the rendered prompt.
