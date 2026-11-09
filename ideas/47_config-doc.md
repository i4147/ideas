# 47 — `config-doc` (turn config files into human documentation)

> **Difficulty 4/10** · **Effort ~4 days** · **Tier: medium**
> **Prior art: ⚠️ partial** — `json-schema-for-humans` (excellent for JSON Schema), `jsonschema2md`, `terraform-docs` (Terraform only), `helm-docs` (Helm only), `mkdocs` + macros, `datamodel-code-generator` (reverse direction), `yq`-based scripts.
> **Pivot required?** Yes — the input is *real config with comments*, and the output must explain required-vs-optional and defaults.

## The problem

Every project has a `config.yaml` (or TOML/JSON) with 80 keys; the README documents 20 of them, wrongly. New users copy an example and hope. `json-schema-for-humans` solves this *if* you have a schema — and the projects that need docs are exactly the ones without one.

## Design

```bash
config-doc generate config.yaml -o reference/configuration.md
config-doc generate config.yaml --from-example config.example.yaml --title "Server configuration"
config-doc check config.yaml --docs reference/configuration.md   # CI: undocumented / stale keys
config-doc schema config.yaml -o config.schema.json              # bonus: infer a JSON Schema
```

What must be in the output per key:

| element | source |
|---|---|
| key path | the structure (`server.tls.cert`) |
| type | inferred (with `oneOf`-style unions: `string \| list[string]`) |
| required? | present in *all* examples, or non-defaulted, or `--required` list; else "optional" |
| default | from the example file, from comments (`# default: 30`), or from a schema |
| description | comment above the key; if missing, derived from the key name (clearly marked "inferred") |
| deprecated | `# deprecated` / `# DEPRECATED:` marker in comments |
| allowed values | enum-ish inference from comments (`# one of: a, b, c`) or from a sibling `values:` list |
| example | the example file's value |

**Key insight: comments are the only documentation that exists,** and both YAML and TOML parsers throw them away. Use `ruamel.yaml` (round-trip mode, `ca.items`) for YAML and `tomlkit` for TOML — both preserve comment attachments per key. This is the whole technical justification for the tool; without comment extraction it's a worse `json-schema-for-humans`.

For JSON (no comments), support a sidecar convention (`config.json` + `config.json.md` keyed by JSON pointer) and the schema path.

## Rendering

Markdown with a nested table per section and an anchor per key; `--format html` via a tiny template; `--format man`. Include a generated `# Configuration` TOC, a "Required keys" summary at the top, and a diff-friendly stable ordering (schema order / file order, never alphabetical unless `--sort`).

```
### `server.tls`
| key | type | default | description |
|---|---|---|---|
| `enabled` | bool | `false` | Enable TLS. Self-signed allowed. *(required)* |
| `cert` | path | – | Path to the PEM certificate. Required when `enabled`. |
| `min_version` | string | `"1.2"` | Minimum TLS version. One of: `1.2`, `1.3`. |
```

**Conditional requirements** ("required when `enabled`") must be expressible: a small `constraints.yml` extension lets users declare `server.tls.cert: required_if(server.tls.enabled)` and `config-doc check` enforces it against a real config file. That enforcement half is what turns docs into a tool.

## CLI/CI behaviour

`check` compares docs to config: undocumented keys (error), documented keys that no longer exist (error), type mismatches in the example (warning), missing descriptions (info, `--strict` promotes to warning). Exit codes for a docs-drift pre-commit hook. Rewrite a marked region only (`<!-- config-doc:begin -->` … `:end -->`) so hand-written prose survives.

## Tests

Fixture configs: YAML with block and inline comments, anchors/aliases (`*default`), multi-document files, a key named `on` (YAML 1.1 boolean trap), TOML with `[tool.x]` nesting and arrays of tables, JSON with a sidecar md, and a 1,000-key file (performance < 1 s). Assert comment association survives anchors and that `on:`/`yes:` are treated as strings.

## Pitfalls

- YAML 1.1 vs 1.2 booleans (`on`, `off`, `yes`) — use a YAML 1.2 loader and say which you used.
- Secrets in configs (tokens as example values) must be masked by value-pattern, not by key name alone.
- Arrays of objects: document the item schema once with a note ("list of:"), don't repeat it per index.
- Never overwrite a hand-written doc; refuse unless the region markers exist or `--force`.
- Inferred descriptions must be visibly marked, or docs become confidently wrong.

## Definition of done

A 200-key `config.yaml` produces complete Markdown reference in <2 s with every key's type, default, and required status, and `check` fails CI when a new key lands undocumented.
