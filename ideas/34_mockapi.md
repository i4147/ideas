# 34 — `mockapi` (spec-driven mock server)

> **Difficulty 3/10** · **Effort ~4 days to reach parity** · **Tier: medium**
> **Prior art: ⚠️ crowded** — `prism` (Stoplight, OpenAPI mock + validation, Node), `mockoon` (GUI+CLI, Node), `moto` (23 AWS services), `responses`/`httpx.MockTransport` (in-process), `wiremock` (JVM), `json-server` (Node), `connexion`'s mock mode, `schemathesis` (test generation).
> **Pivot required?** Yes, and only one is credible: **Pydantic/FastAPI-native, with state**.

## The problem

A frontend team needs an API before the backend exists. Everyone's first instinct is "spin up a mock server from the OpenAPI spec", which `prism mock openapi.yaml` does in one command, including response validation and `Prefer: example=` selection. Building that again in Python would be strictly worse — Prism is battle-tested and speaks the spec correctly.

## Where Python-native wins

Two things Prism does badly, and one thing it can't do:

1. **Pydantic models are the spec.** Many Python teams have `app/schemas/*.py` and no OpenAPI file (or a generated, stale one). A tool that imports the models and serves them is genuinely faster than exporting OpenAPI and running a Node tool. FastAPI already half-does this — but it requires modifying the app.
2. **State.** `POST /orders` should make `GET /orders/{id}` work. Prism has no state; every response is synthetic. A mock with an in-memory store and real CRUD semantics lets frontend flows be tested end to end.
3. **Scenario switching**: `X-Mock-Scenario: slow|error|empty|stale` headers that change latency, status codes, and payload shape — so the frontend team can build the error states that usually get skipped.

## Design

```bash
mockapi serve app.schemas:User app.schemas:Order --port 8000
mockapi serve --from-openapi openapi.yaml --stateful --seed fixtures/    # the Prism-compatible mode
mockapi serve --from-openapi api.yaml --record proxied.jsonl             # record mode: proxy+save
```

Endpoints generated per model: `GET /{plural}` (with `?limit&offset`), `GET /{plural}/{id}`, `POST`, `PATCH`, `DELETE`, plus `GET /_admin/reset`, `/_admin/seed`, `/_admin/scenario`. FastAPI + `uvicorn` is the right stack (auto docs at `/docs` is a nice bonus, and it's what users expect).

Generation rules, driven by field types and constraints: `id`/`*_id` → UUID or int; `email` → faker; `created_at`/`updated_at` → coherent timestamps that respect ordering; enums → sampled to exercise all states; nested models → embedded objects unless `--refs=ids`. Reuse the relational-consistency ideas from file 19, but in-memory.

**Record mode** is the underrated feature: point it at the real API, `--record proxied.jsonl`, and it captures request→response pairs; `serve --replay` then answers from the capture with matching. That gives frontend work a realistic dataset without a database, and it's exactly what `vcrpy` does in-process but for a whole team over HTTP.

## Tests

Generate a spec from a fixture Pydantic module; assert every route returns a payload that validates against the model (`model_validate(response.json())`). CRUD state tests: create → get → patch → delete → 404. Determinism: same `--seed` gives the same ids. Latency injection respects `X-Mock-Scenario: slow` (assert ≥ configured delay). Record/replay round-trip with a fixture server.

## Pitfalls

- Auth: mock servers must be explicit about it — `--auth none|bearer|header:X-Api-Key` with a fake token, otherwise the frontend hardcodes a real one.
- CORS for browser frontends (`--cors '*'`), otherwise it's useless for a SPA and people blame the mock.
- Don't silently ignore unknown fields in `POST`; validate and return 422 (that's the point of mocking a contract).
- Persist state to disk only in `--stateful --persist`, and reset on restart by default (surprising state across restarts is a debugging nightmare).
- Version tagging response headers (`X-Mock-Version`) so nobody ships against a stale mock without noticing.

## Definition of done

Given a directory of Pydantic models, `serve` gives a working CRUD API in <10 s with valid payloads, deterministic with a seed, and record/replay reproduces a real API's responses byte-for-byte.
