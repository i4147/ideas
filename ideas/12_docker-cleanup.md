# 12 — `docker-cleanup` (reclaim disk, with attribution)

> **Difficulty 2/10** · **Effort ~1 day (MVP)** · **Tier: warm-up**
> **Prior art: ❌ already built twice** — PyPI `docker-cleanup` 1.0.0 (2025) and PyPI `docker-gc`-style scripts; plus built-ins `docker system prune`, `docker builder prune`, `docker volume prune`.
> **Pivot required?** Only one exists. If it isn't the pivot below, **don't build this one.**

## The problem

`docker system prune -a --volumes` is a shotgun that also deletes the image you need offline tomorrow. What people actually want before deleting: *what will I get back, and what will I lose?* `docker system df -v` has the numbers but no attribution: you can't tell that 12 GB is one abandoned compose project and 3 GB is a builder cache from a build you ran this morning.

## What exists

`docker system prune` (built in, all-or-nothing, no attribution), `docker-cleanup` (PyPI, "clean all Docker resources quickly" — no preview/attribution), Docker Desktop's GUI (not Linux CLI), `docker-gc` (2014, unmaintained shell).

## The only pivot worth shipping

**Attribution + exclusions + preview.** Group everything by *label* (`com.docker.compose.project`), which is how modern Docker already tags objects, and let the user prune a whole project:

```
$ docker-cleanup preview
RECLAIMABLE 18.4 GB
  compose project "shop"     9.2 GB   3 images, 4 volumes, 2 networks   last used 41d ago
  compose project "old-etl"  6.1 GB   5 images, 6 volumes                last used 212d ago
  build cache                2.4 GB   (docker builder prune)
  dangling images            0.7 GB
PROTECTED (excluded by config): 1.2 GB
  image postgres:16  (in use by container shop_db_1, running)
```

```bash
docker-cleanup preview [--json]
docker-cleanup apply --project shop --yes          # whole compose project
docker-cleanup apply --cache-only --yes            # safe, high-value default
docker-cleanup config                              # show exclusions + where they came from
```

Safety rules that must be enforced in code, not docs:

1. Never touch anything with a running container referencing it (`docker ps -q` → inspect image/volume/network refs).
2. Never touch `docker volume` unless the name matches an explicit `--project`/`--volume` allowlist (`--volumes` alone is banned as a flag).
3. `--keep-image postgres:16,redis:7` and a `~/.config/docker-cleanup/keep.toml` exclusion list, with `why` fields.
4. Print the exact underlying command for every action before running it (`--dry-run` is the default).

## How to talk to Docker

Prefer the **CLI** (`docker ... --format '{{json .}}'`) over the HTTP socket for the MVP: it handles contexts, rootless, and permission errors for free. Parse JSON lines, do not parse tables. If the CLI is missing, fail with a clear message rather than importing `docker-py` (a heavy dep for a 1-day tool).

```
docker ps -a --format '{{json .}}'
docker image ls -a --format '{{json .}}' --no-trunc
docker volume ls --format '{{json .}}'
docker network ls --format '{{json .}}'
docker system df --format '{{json .}}'
docker inspect <id>        # labels, size, created, last used
docker builder du          # or `docker buildx du` where available
```

Sediment layers (`docker image ls` "SHARED SIZE" vs "UNIQUE SIZE") are the honest number for reclaim: `docker system df -v` gives `SharedSize`/`Size`. If unavailable, report the conservative unique size and say so.

## Tests

Golden-file tests on captured JSON (no Docker daemon needed) for the grouping logic; integration tests marked `@pytest.mark.docker` that create a container/volume/network with compose labels, run `preview`, assert protection logic, and clean up. Test that a container in `created` (not running) state also protects its image.

## Pitfalls

- BuildKit cache is not visible as images; `builder prune` is a separate namespace — handle both, and never delete cache the user is using mid-build (`--cache-only` requires no active build).
- Rootless Docker: socket path differs; always go through `docker context`.
- `docker system prune` prompts interactively — pass `--force` and never inherit stdin.
- Report bytes reclaimed *after* the fact by re-running `df` (honest verification), don't estimate.
- macOS/Windows VM disk doesn't shrink automatically — note it, don't promise space back.

## Definition of done

`preview` attributes ≥90 % of reclaimable bytes to a compose project or a named category on a real dev machine, and `apply --project X` deletes exactly that project and nothing else. Otherwise this idea is already served by `docker-cleanup` on PyPI.
