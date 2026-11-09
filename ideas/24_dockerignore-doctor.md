# 24 — `dockerignore-doctor` (what is actually being sent to the Docker daemon)

> **Difficulty 3/10** · **Effort ~3 days** · **Tier: medium**
> **Prior art: ✅ real gap** — `dive` analyses *image layers* after the build; `hadolint` lints the Dockerfile; `docker-slim` minimises images. Nothing shows the **build context** before the daemon receives it.
> **Pivot required?** No. High measurable value, additive to Docker.

## The problem

`docker build .` tars up the build context and ships it to the daemon before any instruction runs. With a stale `.dockerignore` that is 2.1 GB (`node_modules`, `.git`, `.venv`, `dist/`, a `data/` folder with test videos), and:

- the build takes 40 s of pure upload over a remote `DOCKER_HOST`;
- every cache invalidation triggers another 2 GB transfer;
- secrets (`.env`, `id_rsa`, `.npmrc`, `credentials.json`) are copied into the context, and one careless `COPY . .` puts them in a layer, permanently;
- `.git` (often 100 MB+) is included even though `git` isn't installed in the image.

`docker build` prints one line — `transferring context: 2.14GB` — and nothing else. Docker's own docs warn about this and give no diagnostic.

## What the tool prints

```
$ dockerignore-doctor audit .
CONTEXT 2.14 GB  in 41,204 files   (ignored: 1,208 files, 0.9 GB)
TOP INCLUDED
  1.41 GB  node_modules/                11,204 files   ← add `node_modules`
  402 MB   .git/                        3,118 files    ← add `.git`
  118 MB   data/sample-videos/          12 files
  89 MB    dist/                        41 files
  12 MB    .venv/                       2,041 files    ← add `.venv`
LIKELY SECRETS IN CONTEXT (severity: high)
  .env                              (matches your .env.example keys)
  deploy/id_rsa                     (PEM private key)
  app/firebase-credentials.json     (service-account key)
SUGGESTED .dockerignore
  node_modules
  .git
  .venv
  dist
  **/*.pyc
  __pycache__
  data/sample-videos
  .env*
  !.env.example
BUDGET: 2.14 GB > 50 MB  ✗
```

## Implementation: get `.dockerignore` semantics exactly right

This is not `gitignore`. Differences that matter:

- Patterns are matched against the context-relative path with `filepath.Match`-ish rules; `**` matches any number of directories (`**/*.pyc`).
- A leading `!` re-includes. **Last matching rule wins** (unlike gitignore in one respect: an excluded directory cannot be re-included by a later `!` if the directory itself was excluded — Docker documents this, and it confuses everyone).
- Directories are matched including their trailing `/` handling; `node_modules` (no slash) matches both a file and a directory at any depth.
- `Dockerfile` and `.dockerignore` are always sent (not excludable).

Don't hand-roll: `pathspec` supports gitwildmatch, which is close but not identical. Practical approach: implement a small matcher (~120 lines) that walks the pattern list in order, supports `**`, `!`, and directory-pruning, and **cross-check against real Docker with an integration test** (`DOCKER_BUILDKIT=1 docker build -f <probe Dockerfile> --target probe .` where the probe stage does `RUN find /ctx -type f | wc -l` — or cheaper: `docker buildx build --call=outline`/`--print` context info where available).

## CLI

```bash
dockerignore-doctor audit .                      # report
dockerignore-doctor audit . --json               # for CI
dockerignore-doctor suggest --write              # append (never overwrite) rules, comment-tagged
dockerignore-doctor budget --max-context-mb 50   # exit 2 when exceeded
dockerignore-doctor explain data/videos          # why is this file included? shows the matching rule
dockerignore-doctor dockerfile Dockerfile        # do COPY/ADD paths rely on now-ignored files? ← the killer check
```

That last one prevents the most common self-inflicted wound: adding `dist` to `.dockerignore` and breaking `COPY dist/ ./`.

## Build

```
dockerignore_doctor/
  ignore.py    # pattern parser + matcher + `explain(path) -> matched rule`
  walk.py      # os.scandir walk with pruning, file count/size aggregation
  secrets.py   # name/pattern/entropy heuristics (reuse file 22's detector)
  suggest.py   # rule generation from the top-N offenders + defaults
  dockerfile.py# parse COPY/ADD sources, check survival
  report.py, cli.py
```

Secrets detection is name-first and cheap: `*.pem`, `id_rsa*`, `.env*` (except `.env.example`), `*.p12`, `credentials*.json`, `secrets.y*ml`, plus content sniff for `-----BEGIN`.

## Tests

Fixture context trees, and a matrix test comparing our matcher against the expected results of the documented Docker examples (Docker's docs have ~15 canonical `.dockerignore` examples — use them as golden cases). Include: `!` re-inclusion inside an excluded directory, `**` in the middle, a pattern with a trailing space, an indented comment, CRLF `.dockerignore`, and a symlink cycle. Plus an optional `@pytest.mark.docker` test that builds a probe image and compares file counts.

## Pitfalls

- Symlinked directories: Docker follows them into the context (and can escape the root) — WARN loudly, it's an exfiltration risk.
- Hardlinks and sparse files: `st_size` overstates; use `st_blocks * 512` for the "real" number and show both.
- `docker compose build` may use per-service `context:`/`dockerfile:` paths — read `compose.yaml` and audit each service's context, not just `.`.
- Don't rewrite `.dockerignore` in `suggest --write` — append, with a `# added by dockerignore-doctor` comment, and never delete user rules.
- Windows-style separators in a context built on WSL: normalise `\` → `/`.

## Definition of done

`audit .` on a real Node+Python monorepo identifies >90 % of context bytes in the top 3 offenders, the suggested rules cut actual context transfer by >80 % as measured by `docker build`, and `dockerfile` check catches a `COPY dist/` that would break.
