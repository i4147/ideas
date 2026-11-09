# 63 — `api-runner` (chained API calls defined in YAML)

> **Difficulty 5/10** · **Effort ~6 days** · **Tier: hard**
> **Prior art: ⚠️ crowded** — `hurl` (Rust, the strongest: HTTP files, chaining, asserts, CI), `tavern` (pytest-native API testing with YAML, actively maintained), `stepci`, `newman` (Postman CLI), `bruno` (git-friendly GUI+CLI), `httpyac`, `vegeta`/`k6` (load), `restish`, `httpie` (0.28-era single requests), `karate` (JVM).
> **Pivot required?** Yes — chaining and assertions are solved. Only the **stateful, data-driven workflow with real credentials and idempotency** is thin.

## The problem

"Define a sequence of API calls in YAML, pass the output of one as a variable into the next" is exactly what `hurl` does:

```hurl
POST {{base}}/auth/login
{"user": "{{user}}", "pass": "{{pass}}"}
HTTP 200
[Captures]
token: jsonpath "$.token"

GET {{base}}/orders
Authorization: Bearer {{token}}
HTTP 200
[Asserts]
jsonpath "$.items" count > 0
```

And `tavern` does it inside pytest with fixtures. So why build another? Only for things these two don't do well:

1. **Multi-step state that persists across files** — a session (auth token, created resources) that later files reuse, plus **cleanup** of created resources even on failure. `hurl` has no teardown; `tavern` gets there via pytest fixtures but the YAML grows awkward.
2. **Data-driven runs**: `--data cases.csv` runs the whole flow once per row (a smoke test over 40 tenants), with per-row isolation and aggregated results. `hurl --test --variables-file` covers a single variable set; loops over datasets are manual.
3. **Idempotency/rerun safety**: `POST` creates get a `X-Idempotency-Key` derived from `run_id + step + row`, so a retried CI run doesn't create duplicates — the #1 reason API test suites get muted.
4. **Environments with real secret sourcing**: `${env:TOKEN}`, `${file:~/.secrets/x}`, `${keyring:svc/user}` — secrets never in the YAML or argv (see file 22).
5. **A readable report** with per-step timings, captured variables (redacted), and the failing request/response bodies truncated sensibly — plus JUnit XML for CI.

## Design

```yaml
# flows/order.yaml
name: create-order
teardown:                      # always runs, reverse order
  - DELETE ${base}/orders/${order_id}
steps:
  - id: login
    POST: ${base}/auth/login
    json: { user: "${env:API_USER}", password: "${env:API_PASS}" }
    expect: { status: 200 }
    capture: { token: "$.token", user_id: "$.user.id" }

  - id: create
    POST: ${base}/orders
    headers: { Authorization: "Bearer ${token}", "X-Idempotency-Key": "${run_id}-create" }
    json: { user_id: "${user_id}", sku: "${env:SKU:-default-sku}", qty: 1 }
    expect: { status: [200, 201], jsonpath: { "$.status": "pending" } }
    capture: { order_id: "$._id" }

  - id: verify
    GET: ${base}/orders/${order_id}
    expect: { status: 200, jsonpath: { "$.status": "pending" } }
```

```bash
api-runner run flows/ --env staging --data cases.csv --report junit.xml
api-runner run flows/order.yaml --dry-run            # print requests, values redacted
api-runner run flows/ --retry 2 --fail-fast
api-runner diff flows/ --env staging --env prod      # same flow, two environments
```

## Implementation

```
api_runner/
  flow.py      # YAML schema + validation (variables, step ids, teardown)
  templating.py# ${var}, ${env:NAME}, ${env:NAME:-default}, ${file:path}, ${keyring:...}
  http.py      # httpx client, retries with backoff (idempotent verbs only), timings
  extract.py   # JSONPath (jsonpath-ng), header regex, status capture
  assert_.py   # status, jsonpath, header, body-contains, schema (jsonschema), duration
  teardown.py  # run in reverse, collect errors, always execute
  report.py    # console, junit xml, json
  cli.py
```

Templating must be strict: an undefined variable is a hard error before any request is sent (`--allow-undefined` opt-in), because a silently empty `${token}` produces a confusing 401 rather than a config error.

## What to deliberately not build

A GUI, a Postman importer in v1, a load tester, OAuth2 flows beyond "get a token from an endpoint" (delegate: run `curl`-equivalents as a *setup* step, or support `token_command`), and any kind of test recording. Each is a project.

## Tests

`respx` fixtures for a 3-step flow: login → create → verify, with captures. Assert: variable propagation, teardown runs after a failed step (and its error is reported without masking the original failure), `--data` runs N times with isolated captures, undefined variable fails before any request, retry only on 5xx/connect errors and never on 4xx, and JUnit XML validates against the schema readers expect. Fixtures for templating: `${env:X:-default}`, `${file:...}` (tmp), a missing env var, a nested `${${a}}` (reject).

## Pitfalls

- Capture/redaction: never print a captured token in the report — mask values matching secret patterns and mark them `***` with a `--show-captures` override.
- Retries change semantics for non-idempotent verbs; require an explicit `retry: {on_status: [502,503], safe: true}` for anything but GET.
- Teardown order must be reverse and must skip steps whose capture is missing (don't DELETE `/orders/undefined`).
- YAML `yes`/`no` booleans bite (`expect: {status: no}`) — use a YAML 1.2 loader and validate types.
- Environment inheritance: `--env prod` must never fall back to staging values for a missing key silently.
- Sequencing without dependencies is a foot-gun: support `--parallel` only for flows with no captures between steps.

## Definition of done

A 6-step flow with auth, creation, verification, and teardown runs against a real staging API, 40 CSV rows in one command, no leaked secrets in output, and a JUnit report a CI pipeline accepts.
