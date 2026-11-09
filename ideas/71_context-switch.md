# 71 — `switch` (start work on a project in one command)

> **Difficulty 6/10** · **Effort ~7 days** · **Tier: hard**
> **Prior art: ⚠️ crowded at the edges** — `direnv` (per-directory env), `mise`/`asdf` (tool versions), `just`/`make` (tasks), `tmuxinator`/`tmuxp` (session layouts), `devcontainer-cli` (containers), `nix develop`/`devbox` (reproducible envs), `docker compose up`, editor CLIs (`code .`, `nvim .`), `worktree` helpers (`git-worktree`, `wt`).
> **Pivot required?** Yes and it's the hard part: this is *orchestration* of tools people already have, and the value depends entirely on the reliability of the glue.

## The problem

Switching from project A to project B means: `cd`, remember which services B needs, `docker compose up -d`, export 4 env vars, activate the right Python, open the editor at the right place, and remember which branch/context you were in. Everyone has a shell alias; nobody has something that survives a reboot, reports what's already running, and cleans up.

## What already exists, honestly

`mise` covers tool versions and tasks; `direnv` covers env; `tmuxinator` covers layouts; `devcontainer` covers containers (and requires a heavy toolchain). Nothing covers the *combination with state awareness*: "for project B, these 2 of 4 services are already up, the venv is stale, and port 5432 is taken by project A's Postgres".

## Design

```toml
# ~/.config/switch/projects/shop.toml
[project]
dir = "~/code/shop"
editor = "nvim"
tools = { python = "3.12", node = "22" }

[env]
DATABASE_URL = "postgres://localhost:5433/shop"   # literal ok; secrets via ${file:…}
PYTHONPATH = "src"

[services]
postgres = { type = "docker", compose = "compose.yaml", service = "db", port = 5433 }
redis    = { type = "docker", compose = "compose.yaml", service = "redis", port = 6380 }
worker   = { type = "process", cmd = "uv run python -m shop.worker", health = "tcp:127.0.0.1:9100" }

[hooks]
setup  = "uv sync --quiet"          # runs only when pyproject/uv.lock changed
layout = "tmux:shop"                # optional
```

```bash
switch shop                 # start what's missing, export env, cd, open editor
switch shop --no-editor --no-services
switch status               # what's running per project, ports, docker containers
switch down                 # stop only this project's services
switch ls                   # configured projects + last used
```

The *stateful* behaviour is what makes it better than a shell function:

- **Port allocation tracking**: a state file maps project→service→port, and `switch` refuses (with a precise message) if a port is taken by another project, offering the next free one.
- **Idempotence**: `docker compose up -d` is safe; a `process` service needs a PID file + a liveness probe before restarting.
- **Setup staleness**: hash `pyproject.toml`/`uv.lock`/`package.json` and run the setup hook only when the hash changed (the "it's been a month" problem).
- **Cleanup on exit** (`switch down`) that never touches services owned by another project.
- **State recovery**: last branch, last files opened (`vim` `.viminfo` is not portable), and "what I was doing" notes in `~/.local/state/switch/`.

## Implementation

```
switch/
  config.py   # TOML projects, validation, ${file:}/${env:} secret refs
  ports.py    # bind test + state map + allocation
  services.py # docker (via `docker compose` CLI, not the SDK), process (Popen, pidfile, health)
  env.py      # export via a generated env file the user's shell sources; never mutate the parent shell
  state.py    # sqlite or json
  cli.py
```

**The shell integration is the fundamental constraint**: a child process cannot change the parent's cwd or environment. So `switch` must emit a shell snippet and the user's shell must eval it:

```bash
# in .zshrc
switch() { eval "$(command switch "$@")"; }     # --shell-integration prints `cd …; export …`
```

Design for that explicitly: `switch` prints (a) progress to **stderr**, (b) the shell commands to **stdout**; `--plain` prints a human report instead. Getting this wrong makes the tool useless in a subtle way, and every "just use os.chdir" attempt fails. Document the `eval` requirement loudly; provide `switch init --shell zsh`.

## Tests

- Port allocation: bind a socket in `tmp_path`, assert refusal and the suggested alternative; two projects declaring the same port → error naming both.
- Service lifecycle: a fake `docker`/`compose` script on `PATH` that records calls (assert `up -d` only for missing services, `down` only for owned ones); a `process` service with a real `python -m http.server` and a health probe.
- Setup staleness: touch lockfile → hook runs; run again → skipped (assert via a marker file).
- Shell integration: assert stdout contains only shell commands and is `eval`-able (run through `bash -n`); assert stderr has progress.
- Failure modes: missing project dir, port occupied by a non-managed process, docker daemon down → each gives one actionable line and exit 2.

## Pitfalls

- Never write to the user's `~/.zshrc` automatically; print the snippet.
- `docker compose down` without the right project name stops *everything* — always pass `-p <project>`.
- Secrets in a TOML that gets committed: keep the config outside the repo by default and support `${file:}`.
- Killing a `process` service must kill the process *group* (supervisors respawn children), and must not kill a PID that was reused (store the start time from `/proc/<pid>/stat`).
- Cross-platform: Linux only for the MVP (the request says so) — don't scatter `if sys.platform` throughout.

## Definition of done

`switch shop` after a reboot brings up exactly the missing services in <10 s, exports a working env, and `switch down` leaves other projects untouched; the printed shell snippet is valid for bash and zsh.
