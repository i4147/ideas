# 78 — `narrate` (turn a config or JSON blob into a story)

> **Difficulty 6/10** · **Effort ~6 days** · **Tier: hard**
> **Prior art: ⚠️ thin, with good reason** — `jq`/`yq` (structure, not prose), `json-schema-for-humans` (documentation, not narration), `datamodel-code-generator`, LLM pipes (`llm`, `mods`, `ollama`), `explain`-style one-liners, AWS Config/`terraform plan` human output, `diffoscope --text`, `stakeholder-report` scripts.
> **Pivot required?** Yes — and the pivot is *deterministic templating with an optional LLM only for phrasing*.

## The problem

"The system is configured for Production mode with 3 replicas and a 30-second timeout" — the request is to read a 2,000-line `config.yaml` (or a huge API JSON response) and produce a paragraph a non-technical stakeholder can follow: what this thing does, what's enabled, what's risky, what's different from the default.

Legitimate uses: change-review summaries ("what does this Terraform/Helm/Argo config actually change?"), onboarding ("what is this service configured to do?"), and compliance evidence ("is encryption enabled everywhere?").

## Why naive LLM narration fails (and what to do instead)

An LLM reading a config invents plausible settings, misses the dangerous ones, and can't be tested. Instead:

1. **Compute facts deterministically** with a small rule set per domain:
   - *k8s/Helm*: replicas, resource requests/limits (and whether limits are set — the #1 production risk), probes, image tags (`:latest` is a finding), `securityContext` (root user, privileged), `hostPath` mounts, `LoadBalancer` vs `ClusterIP`, node affinity.
   - *Docker Compose*: published ports vs internal, volumes (bind mount of `/var/run/docker.sock` is a finding), restart policies, healthchecks.
   - *App config (generic YAML/TOML)*: `environment`/`debug`/`log_level`/`timeout`/`replicas`/`workers`, secret-looking keys, feature flags, list sizes (`allowed_hosts` = 2 entries).
   - *Generic JSON*: shape summary — array length, key coverage, null rates, min/max — for "what's in this response".
2. **Narrate with templates** into a fixed structure: *What this is* / *What's enabled* / *What's notable* / *What's risky* / *What changed* (if two inputs). Templates produce sentences from facts, so every sentence is traceable to a key.
3. **Optional LLM polish** (`--polish`): the model receives **only the fact JSON** (not the raw config) and rewrites it into prose. Refuse to pass unknown keys. Validate the output against the facts by checking that every number/word it states appears in the fact set — drop sentences that don't.
4. **Diff narration** (`--change`): "replicas 1 → 3; memory limit added at 512Mi; image tag pinned" — a deterministic change list is more useful than prose, and it's what reviewers need.

## Output

```
$ narrate k8s/deploy.yaml
This is a Kubernetes Deployment for "shop-api" running 3 replicas of the image
shop-api:1.9.2 (tag pinned, no digest).

WHAT IT DOES
  - Listens on container port 8000 behind a ClusterIP service (internal only).
  - Has CPU/memory limits (500m / 512Mi) and a liveness + readiness probe on /healthz.
  - Moves traffic away from a pod after 2 failed readiness checks.

NOTABLE
  - Runs as non-root (runAsUser 1000) with a read-only root filesystem.
  - Pulls the image from a private registry (imagePullSecrets: regcred).
  - Auto-scales: HPA min 3 / max 12 at 70% CPU.

RISKS
  ⚠ No PodDisruptionBudget: node drains can take the service offline.
  ⚠ No anti-affinity: all 3 replicas may land on one node.
  ⚠ Memory limit equals request (512Mi): no burst headroom before OOMKill.

SOURCES: replicas (spec.replicas) · limits (…resources.limits) · probes (…livenessProbe)
```

The `SOURCES` footer is the trust mechanism: every statement maps to a path, and `--json` emits the fact objects.

## CLI

```bash
narrate config.yaml [--domain k8s|compose|app|auto] [--polish] [--format md|text|json]
narrate --change old.yaml new.yaml      # deterministic change summary
narrate api-response.json --shape       # what's in this blob (for analysts)
```

## Implementation

```
narrate/
  domains/k8s.py compose.py app.py json_shape.py   # fact extractors: (path, fact, severity)
  facts.py     # Fact(path, kind, value, sentence_template, severity)
  render.py    # narrative assembly, deterministic ordering (by section then path)
  polish.py    # optional LLM: fact JSON -> prose, with a grounding check
  cli.py
```

Extraction is plain dict walking with path recording — no schema required, no `pydantic` model per domain (models make it rigid; this tool must handle partial configs).

## Tests

Fixture configs with each finding, plus a "clean" config that must produce zero risks (false-positive control is the main risk). Assert: every risk cites the right path, the summary contains no number absent from the config (a grounding test over the rendered text), `--change` handles added/removed/nested changes, and `--polish` against a fake LLM never emits a sentence with an ungrounded number (the validator drops it). Performance: a 5,000-key YAML under 1 s.

## Pitfalls

- Configs contain secrets: narrate structure and *presence*, never values of secret-looking keys (`password`, `token`, `key`, `*_secret`); mask high-entropy strings.
- Determinism: sort facts by section then path so two runs produce identical text (diffable in review).
- Don't judge: phrase risks as "no X is set", not "this is insecure" — the tool doesn't know your threat model.
- Multi-document YAML (`---`) and Helm templates (`{{ }}` — refuse, tell the user to `helm template` first) are the two parsing traps.
- If `--polish` is used, print which provider/model and that the facts (not the config) were sent.

## Definition of done

A 1,200-line k8s manifest becomes a 15-line narrative where a non-engineer understands what runs, and a reviewer can verify every claim through the `SOURCES` footer; `--change` on two versions produces the 5 real differences with no noise.
