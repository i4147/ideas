# 21 — `log-fold` (collapse repeated log lines into templates)

> **Difficulty 3/10** · **Effort ~4 days** · **Tier: easy→medium**
> **Prior art: ❌ already built** — PyPI `logfold` 0.5.0: *"Fold large logs into templates and compare two runs. Rust core, Python API and CLI."* Also `lnav` (clustering view), `logreduce`, `angle-grinder`, `drain3` (the algorithm itself), `logmine`.
> **Pivot required?** Yes — significantly. The core is solved; the operational wrapper is not.

## The problem

A 200 MB log has 12 distinct messages and 400,000 lines. You want:

```
3,412× ConnectionError to db:5432 after 5 retries       first 09:12:04  last 10:48:31
   11× ImportError: no module named 'yaml'              first 09:40:02  last 09:40:19
```

`logfold` (Rust core) does exactly this and does it fast. `drain3` gives you the template algorithm as a library. So a from-scratch reimplementation is wasted effort — unless you build the thing these tools deliberately don't: a **streaming pipeline filter with template-state awareness**.

## The pivot: `stdin` filter + new-template alerting

Existing tools are batch-oriented file processors. What an on-call engineer needs during an incident:

```bash
kubectl logs -f deploy/api | logfold --stream \
    --alert-on new-template \
    --diff baseline.fold.json \
    --exit-after 300s
NEW TEMPLATE (not in baseline):
  1× <*> WARN cache miss for key <*> latency=<*>
NEW TEMPLATE:
  7× FATAL cannot acquire advisory lock on <*>
```

That is: (1) **streaming** with a bounded template table (online Drain-style clustering), (2) **baseline comparison** — "this template never appeared in the last deployment's logs", and (3) a **stability signal** in CI: fold the logs of a canary run and diff template sets against staging. New templates = new failure modes, which is a *far* better test than grepping for "ERROR".

## If the pivot isn't enough, the honest alternatives

- Use `logfold` for batch folding; it is fast and maintained.
- Use `drain3` if you need the library inside your own service.
- Use `lnav` interactively (its `:filter-in`/clustering is excellent) but note it's not scriptable in a pipeline.

## Implementation sketch (only if you take the pivot)

```
log_fold/
  mask.py     # variable masking: UUIDs, IPs, hex ids, numbers, quoted strings, timestamps, paths
  template.py # prefix-tree (Drain) clustering: depth 4, similarity threshold 0.5, max children 100
  stream.py   # incremental: fold on the fly, bounded table (LRU), JSONL in/out
  compare.py  # load/save template sets; classify new/missing/changed-count
  render.py   # human table + --json
```

The masking order matters: mask timestamps and numbers *after* tokenising, or `<*>` swallows the log level and every line becomes one template. Keep a `--keep-tokens ERROR,WARN,FATAL,INFO` allowlist so severity survives masking — this is the single biggest cause of bad folding.

Log-format awareness is the differentiator over a generic implementation: detect JSON logs (`json.loads` per line, flatten keys, fold the *message* field) vs plain text (mask+tokenise) vs `logfmt` (`k=v` pairs). For JSON, fold on the template of `message` and aggregate by `(level, template, service)`.

## Tests

Public log corpora in `tests/fixtures/`: Linux `auth.log`, a Django traceback burst, JSON k8s logs, and a synthetic 1 M-line file. Assert: template count within ±10 % of hand-labelled truth, first/last timestamps exact, memory bounded (RSS < 150 MB on 1 M lines, `--stream`), and byte-identical determinism across runs (no set/dict ordering leaks).

## Pitfalls

- Multi-line stack traces: join continuation lines before folding, or every traceback becomes 20 templates. Join on "line doesn't start with a timestamp/level" with a cap.
- Don't lose the raw lines: `--keep-first-last` outputs the actual examples, which is what people paste into tickets.
- Truncate enormous messages (a 40 KB SQL query in a log line) before templating.
- Streaming mode must not grow unbounded — cap templates at e.g. 10k and report overflow.

## Definition of done

Piping a live `kubectl logs -f` through it surfaces a genuinely new error template within seconds, and the batch mode folds a 1 M-line file in under 5 s using <150 MB.
