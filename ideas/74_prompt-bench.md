# 74 — `model-bench` (same prompt, many local models, side by side)

> **Difficulty 6/10** · **Effort ~6 days** · **Tier: hard**
> **Prior art: ❌ effectively solved** — `promptfoo` (providers × prompts × assertions, matrix reporting, caching, CI), `lm-evaluation-harness` (EleutherAI, academic benchmarks), `ollama`'s own `bench` examples, `llm` + `llm-cache`, `genai-bench` (throughput), `vLLM bench serve`, `evals` (OpenAI), `text-generation-benchmark`.
> **Pivot required?** Yes — and only on **hardware-aware throughput/latency profiling**, not on prompt comparison.

## What already exists

`promptfoo eval -c config.yaml` with 6 providers gives you a side-by-side table of outputs, pass/fail against assertions, token counts, and latency, in a web UI or JSON, in CI. That is the stated idea, and it is done.

For pure performance: `llama-bench`, `vLLM bench serve`, and `ollama run --verbose` report tokens/s. For quality: `lm-eval-harness` reports MMLU/HellaSwag on standard sets.

## The remaining gap: "can my machine run this, and how does it feel?"

That's a hardware question, not a prompt question, and it's what people actually face when picking a local model:

```
$ model-bench scan --models ollama:* --prompt-file summarise.md --context 8k
MACHINE  RTX 3060 12GB · 32GB RAM · ollama 0.5.2

MODEL                        SIZE   TTFT   tok/s  VRAM  CTX   OOM?  QUALITY*
llama3.1:8b-instruct-q4_K_M  4.9G   180ms   58    5.1G  8k    no    ████░ 4/5
qwen2.5:7b-instruct-q8_0     7.8G   240ms   34    8.3G  8k    no    ████░ 4/5
mistral-nemo:12b-q4_K_M      7.1G   260ms   41    7.4G  8k    no    ███░░ 3/5
llama3.1:70b-q4_K_M         39.6G   —       —     —     8k    YES   skipped (needs 40G VRAM)
deepseek-coder:6.7b-q4_K_M   3.8G   150ms   71    4.1G  8k    no    ███░░ 3/5

RECOMMENDATION (fit × speed × quality): qwen2.5:7b-q8_0 for quality at 34 tok/s;
llama3.1:8b-q4 if you want 58 tok/s and 4GB headroom for other apps.
```

`*QUALITY` is the honest, hard part: a 5-line rubric scored by *you* (`--rubric`) or by a larger judge model, never presented as an absolute benchmark.

## Design decisions that make it trustworthy

1. **Measure, don't trust `--verbose`.** TTFT via the first streamed token timestamp, tok/s from `eval_count / eval_duration` returned by Ollama's API (`done: true` message), VRAM from `nvidia-smi --query-gpu=memory.used` before/after, and peak RSS for CPU-only. Take 3 runs, report median ± spread; the spread matters (thermal throttling, first-run model load).
2. **Context sensitivity**: prompt size changes throughput dramatically (attention is quadratic-ish in practice). Always report at a stated `--context` and include at least 2 sizes (e.g. 2k, 8k) — a single number is misleading.
3. **Warm vs cold**: the first run includes model load (seconds to minutes). Report both (`cold: 14.2s load`, `warm: 180ms TTFT`) or people conclude the model is slow.
4. **OOM handling**: attempt to run, catch the error, report "OOM (needs ~Xg)" instead of crashing the sweep; never partially load a 70B model into swap and hang the machine — pre-check `model size > VRAM + RAM*0.6` and skip with a warning.
5. **Determinism**: `temperature=0`, `seed=42`, fixed `num_ctx`, and record model digests (`ollama show --modelfile` / digest hash) — otherwise "the output changed" is uninterpretable.
6. **Quality rubric that isn't a lie**: the default is a *pairwise blind* comparison — the tool randomises A/B order, shows you both outputs, you pick, and it computes a Bradley-Terry ranking across models. Human judgement, statistically aggregated, instead of fake scores. `--judge-model` opts into LLM judging with the judge's identity recorded.

## CLI

```bash
model-bench list                                  # installed models with size/quant/digest
model-bench run --models ollama:* --prompt-file p.md --runs 3 --context 8k
model-bench compare --models a,b,c --cases cases/ --blind     # pairwise human ranking
model-bench fit --models ollama:*                  # which will fit on this GPU, and at what context
model-bench report --json --out bench.json
```

## Implementation

```
model_bench/
  backends/ollama.py  # /api/tags, /api/chat (stream=true) for TTFT, /api/show for digest+params
  backends/openai.py  # compatible endpoints (llama.cpp server, vLLM) via base_url
  hardware.py         # nvidia-smi / rocm-smi / lspci detection, VRAM, CPU, RAM
  runner.py           # warmup, N runs, timeouts, cancellation (Ctrl-C must stop generation)
  stats.py            # median/IQR, Bradley-Terry from pairwise votes
  render.py
```

Deps: `httpx` only; no model libraries. Talk to HTTP endpoints, never import `torch` (a 2 GB dependency for a reporting tool is a non-starter).

## Tests

Fake Ollama server (`http.server`) that streams a canned response with configurable delays and returns realistic `eval_count`/`eval_duration` in the final message; assert TTFT/tok/s calculations, median over 3 runs, OOM error handling when the fake returns 500 with "out of memory", skip logic for models larger than detected VRAM (inject a fake `nvidia-smi` output), and Bradley-Terry ranking on a fixture vote table. Assert Ctrl-C (`KeyboardInterrupt`) cancels an in-flight stream and prints partial results.

## Pitfalls

- Don't benchmark with an unloaded model and call it cold *and* warm — label states explicitly.
- Concurrent benchmarks on one GPU invalidate each other: serialise runs, and refuse `--parallel` unless `--devices` are distinct.
- tok/s from client-side wall clock is wrong under network latency; prefer server-reported counts, fall back and label the source.
- Quantisation in the tag name is the single biggest quality factor — never compare across quants without saying so in the table header.
- Model digests change on `ollama pull` of the same tag: record the digest in every report.
- Don't claim a quality score from a benchmark subset; link to `lm-eval-harness` for real numbers.

## Definition of done

On a 12 GB GPU, `fit` correctly predicts which 6 models run at 8k context, `run` produces a stable table (±10 % between repeats), and `compare --blind` ranks 3 models from 30 human choices.
