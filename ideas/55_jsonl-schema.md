# 55 — `jsonl-schema` (schema inference and drift for event streams)

> **Difficulty 5/10** · **Effort ~5 days** · **Tier: hard-ish**
> **Prior art: ⚠️ partial** — `genson` (infer JSON Schema from samples, batch, no streaming/union statistics), `jsonschema` (4.26, validation), `datamodel-code-generator` (schema→Pydantic), `pandera`/`pydantic` (DataFrame/model validation), `jsonschema-diff`, `frictionless`, `Great Expectations`. Nothing samples a *stream*, tracks nullability/union rates, and diffs schema versions.
> **Pivot required?** Yes — streaming + statistical inference + drift classification.

## The problem

Your service emits JSONL to disk/S3. Downstream, a pipeline assumes `event.user.id` is always a string; one deploy starts emitting an int, and the pipeline silently drops 4 % of rows. Nobody notices for a week.

JSON Schema tooling is file-oriented: `genson` reads a sample file into memory, `jsonschema` validates documents you already have. For a 40 GB JSONL stream you want: infer a schema from a *sample*, with **statistics** (how often is this field null? how many distinct types? is this union real or a bug?), validate new data *as it streams*, and compare today's schema to last week's.

## Design

```bash
jsonl-schema infer events.jsonl --sample 50000 --out schema.json
jsonl-schema infer events-*.jsonl --sample 1e6 --key-path user.id   # flatten/keys focus
jsonl-schema validate new.jsonl --schema schema.json --allow-new-fields --stats
jsonl-schema diff schema-old.json schema-new.json --format markdown
jsonl-schema gen-pydantic schema.json --out models.py
jsonl-schema gen-sql schema.json --table events --dialect duckdb
```

Inference output is a schema **plus** a `x-stats` block per node, which is where the value is:

```json
{"type": "object",
 "properties": {
   "event_id": {"type": "string", "format": "uuid", "x-stats": {"null_rate": 0.0, "distinct": 0.98}},
   "ts": {"type": "string", "format": "date-time"},
   "amount": {"type": ["number", "string"], "x-stats": {"types": {"number": 0.962, "string": 0.038},
              "note": "mixed types - likely a serialisation bug"}},
   "user": {"type": "object", "properties": {"id": {"type": ["string","integer"],
            "x-stats": {"types": {"string": 0.97, "integer": 0.03}}}}}},
 "x-stats": {"sample_size": 50000, "lines_skipped": 2, "key_frequency": 1.0}}
```

Rules that make inference *useful* rather than technically-correct-and-noisy:

- **Type union with a threshold**: if a type appears in <1 % of samples, keep it in the schema but mark `x-stats.warn` (it's probably a bug, not a legitimate union). `--strict-types` errors instead.
- **Nullable vs missing**: track separately (`null_rate` vs `key_frequency`). A field missing 3 % of the time is a different schema problem from an explicit `null`.
- **Array element merging**: union all elements; if an array is empty in the sample, `items: {}` with a `x-stats.empty: true` note.
- **Depth limit** (`--max-depth 12`) with `x-stats.truncated` rather than an explosion on pathological nesting.
- **Incremental/streaming**: update stats per line without keeping samples, using a `Counter` for types and a bounded reservoir for distinct-value estimation (HyperLogLog-lite or a capped set with a "≥N" flag). Memory must stay flat: `--sample` limits *lines read*, not buffered objects.
- **Number handling**: distinguish int vs float without losing `1.0` → `integer`; use `Decimal` parsing to detect values that would lose precision. Detect epoch timestamps (`1_700_000_000` ± range) and flag them as `x-format: epoch-seconds` candidates, never silently convert.

## Drift classification (the actual product)

```
$ jsonl-schema diff old.json new.json
BREAKING  user.id: integer added to a string-only field (3.1% of sample)
BREAKING  type: "#/properties/amount" number → ["number","string"]
WARNING   new field "context.trace_id" (present in 99% of rows) → consider required
INFO      field "legacy_flag" null_rate 0.00 → 0.92  (effectively removed)
INFO      max array length 12 → 240
```

Classification maps directly to downstream impact: a type union with a new member is breaking for typed consumers; a new *always-present* field is a warning (producers should document it); a field going 100 % null is a soft removal. `validate --allow-new-fields` mirrors Prism/protobuf semantics so consumers can opt into forward compatibility.

## Implementation

- Stream with `for line in file` over a binary buffer + `orjson` (optional; `json` fallback), skip malformed lines counting them (`lines_skipped`), never materialise the file.
- `validate` uses `jsonschema`'s `Draft202012Validator` with a compiled validator cached per schema, and `iter_errors` limited to `--max-errors` per class; report violation *rates* per JSON pointer, not a flood of messages.
- `gen-pydantic`: emit `Optional[...]` for nullable, `Union[...]` for unions, `datetime` for `date-time`, `Field(alias=...)` for non-identifier keys, and `model_config = ConfigDict(extra="allow")` when the schema allows extras. Run `ast.parse` + `ruff format` on generated code in a test.
- `gen-sql`: map to `VARCHAR/BIGINT/DOUBLE/BOOLEAN/TIMESTAMP/JSON` per dialect, with union types → JSON column and a comment.

## Tests

Fixture JSONL: 20 handcrafted lines covering every inference rule, a 1 M-line generated file for memory (assert RSS stays flat with `tracemalloc`, sample 10k), a file with a broken line mid-stream, a nested array of mixed types, unicode keys, and duplicate keys in one object (`json` keeps the last — document it). Golden schema JSON (sorted keys) so diffs are reviewable; assert `gen-pydantic` output round-trips through `model_validate` on the sample.

## Pitfalls

- Big integers (snowflake IDs > 2^53) must not become floats — parse ints as ints, never via `float`.
- Don't put `"required": [...]` on everything you saw; required means *expected always*, so derive it from `key_frequency == 1.0` **and** state it in `x-stats`.
- Schema bloat: a free-form object with 2,000 keys should become `additionalProperties: {}` past a threshold — otherwise the schema is unusable.
- `jsonschema`'s `date-time` accepts surprising formats; if you claim `format: date-time`, actually check with `rfc3339-validator` and count violations.
- Determinism: sample selection must be deterministic (`--skip/--every` or seeded reservoir), or CI diffs churn.

## Definition of done

`infer` on a 10 GB stream with `--sample 100k` finishes in <10 s using <200 MB, the generated Pydantic models validate the whole stream, and `diff` catches a real type change as BREAKING.
