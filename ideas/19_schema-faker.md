# 19 — `schema-faker` (realistic payloads from JSON Schema / OpenAPI / Pydantic)

> **Difficulty 3/10** · **Effort ~2 days** · **Tier: warm-up**
> **Prior art: ❌ already built, well** — `polyfactory` (3.5.0, Pydantic/dataclass/attrs factories), `hypothesis-jsonschema`, `jsfaker`, `faker` + `jsonschema`, `openapi-generator` (examples), `prism mock`, `mimesis`.
> **Pivot required?** Yes — and only one is interesting: **stateful, relationally-consistent fake data**, not random objects.

## The problem

"I need 30 realistic JSON bodies to hit this endpoint" is real, and `polyfactory` already answers it for models you own:

```python
from polyfactory.factories.pydantic_factory import ModelFactory
class UserFactory(ModelFactory[User]): ...
UserFactory.batch(30)
```

`hypothesis-jsonschema` generates valid instances from any JSON Schema. `faker` provides the primitives (IBAN, address, company names with locale support). Building "Faker for schemas" from scratch is a solved problem with a mature, better-tested answer.

## The pivot: consistency across entities

What every generator gets wrong is *relations*. Fake data that satisfies each schema individually is useless for testing: orders reference users that don't exist, `updated_at` precedes `created_at`, a price is negative, a "shipped" order has no shipping date.

```
$ fake-data --schema api/openapi.yaml --out ./fixtures \
    --entities 500 --seed 42 --consistency relational
wrote users.json (500) orders: 1,842  order_items: 4,113
invariants checked: 14 ok, 0 violated
```

Features that justify a package:

1. **Referential integrity**: `order.user_id ∈ users.id`; cardinality distribution (`--orders-per-user 0..6:zipf`).
2. **Temporal coherence**: `created_at < updated_at < fulfilled_at`, all within a business-hours-ish window, with monotone ordering across statuses (`paid` before `shipped` before `delivered`).
3. **Semantic value faking by field name**: `email` → faker email, `currency` → ISO 4217 from a list, `country` → ISO 3166, `slug` → derived from `title`, enum values drawn with a configurable distribution so *every* state gets exercised.
4. **Constraints honoured**: `minLength`/`pattern`/`minimum`/`multipleOf`/`format: date-time`, plus `x-faker` extensions and OpenAPI `example` precedence.
5. **Determinism**: `--seed` makes a byte-identical dataset, so fixtures are diffable in git.

## Build

```
fake_data/
  schema.py    # load JSON Schema / OpenAPI 3 (components + $ref resolution) / Pydantic model import
  gen.py       # value generation per type, using `faker` + `hypothesis-jsonschema` where it fits
  relate.py    # entity graph -> id pools, cardinality, FK sampling
  invariants.py# declarative checks (regex/enum/range/ordering) + report
  emit.py      # json | jsonl | sql insert | csv
```

Do **not** reimplement validation: emit with `jsonschema` in the loop and retry/report violations (bounded attempts). If a schema is over-constrained (e.g. `pattern` impossible to satisfy with faker), fail that field loudly rather than emitting junk.

## Tests

Use `hypothesis-jsonschema`'s own test corpus style: for 30 hand-written schemas, assert every generated document validates; assert determinism by seed; assert FK integrity on a two-entity graph; assert `minLength`/`pattern` for 10 tricky patterns (anchors, unicode classes); assert that an unsatisfiable constraint produces a clear error, not a hang.

## Pitfalls

- `faker` is 20 MB+ with locale data — lazy-load locales; make it an extra if size matters.
- OpenAPI examples are usually the *least* interesting value (one happy path); default to generated, offer `--use-examples`.
- Recursive schemas need a depth cap and cycle detection.
- Money and dates are where fake data misleads tests: always emit `Decimal`-safe strings, never floats, and document timezone assumptions (UTC everywhere).

## Definition of done

One command produces a 5-entity, 5,000-row dataset that validates against the OpenAPI schema, satisfies all declared invariants, and reproduces byte-for-byte from a seed. Otherwise use `polyfactory`.
