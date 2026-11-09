# 05 — `whyport` (what is on this port, and why)

> **Difficulty 2/10** · **Effort ~2 days** · **Tier: warm-up**
> **Prior art: ⚠️ partial** — `ss`, `lsof -i`, `fuser`, `netstat`, `ss -p`; nothing human-oriented and Docker-aware.
> **Pivot required?** No — this is a genuine small gap, the trick is scope discipline.

## The problem

`EADDRINUSE :::8000` and then five minutes of `lsof -i :8000` returning a PID, `ps` showing `python`, and no clue which project it was, which compose file started it, or how to kill the whole tree. In Docker it's worse: the host PID is `docker-proxy`, the real process is in a container with a different PID namespace.

What a developer actually wants:

```
$ whyport 8000
:8000  LISTEN  pid 41233  python3.12 (runserver)
  cwd      /home/ana/code/shop-api
  cmd      python manage.py runserver 0.0.0.0:8000
  user     ana   started 2026-11-09 09:12 (2h 41m ago)
  parent   41201  poetry run manage.py
  docker   container shop_api_1  (compose project: shop)  published 8000->8000/tcp
  git      shop-api @ 3f2c1ab (branch: feat/cart)   ← and the repo has uncommitted changes
  kill     whyport 8000 --kill        (kills the process group)
```

That last block — cwd + git state + compose project — is the whole product. `ss` gives you the first four columns.

## How to read the data on Linux

1. **Sockets**: parse `/proc/net/tcp`, `/proc/net/tcp6`, `/proc/net/udp` (hex port, hex IP, inode, state). This is faster and more reliable than shelling out to `ss`, and gives you the *inode*.
2. **Inode → PID**: walk `/proc/*/fd/*` symlinks looking for `socket:[<inode>]`. Requires read permission on the fds (root or same-user; degrade gracefully to "permission denied, try sudo").
3. **Process facts**: `/proc/<pid>/cwd`, `/proc/<pid>/cmdline` (NUL-separated), `/proc/<pid>/status` (Uid, PPid), `/proc/<pid>/stat` start time in ticks → wall clock via `/proc/stat` `btime`.
4. **Process tree**: follow PPid up to PID 1, printing the chain (finds `poetry run`, `uvicorn --reload` supervisors, `npm run dev`).
5. **Docker**: if any ancestor comm is `docker-proxy`/`containerd-shim`, query the Docker socket (`/var/run/docker.sock` via `http.client` over a UNIX socket — no `docker` dependency) for containers with that published port; map container PID via `HostConfig`/`State.Pid`, then read `/proc/<containerpid>/root/<cwd>`. If the socket is unavailable, say so instead of guessing.
6. **Git**: from the resolved cwd, run `git -C <cwd> rev-parse --show-toplevel --abbrev-ref HEAD --short HEAD` and `git status --porcelain | head`.

Fallbacks: `ss -ltnp` if `/proc` parsing fails (some hardened kernels), `lsof` last.

## CLI surface

```bash
whoport 8000                 # human report
whoport 8000 --json
whoport --all                # table of every listening port with cwd+project
whoport 8000 --kill          # SIGTERM the process group, then SIGKILL after --timeout 5
whoport --watch 8000         # re-print when the owning PID changes (dev server restarts)
```

Exit codes: `0` found, `1` nothing listening, `2` permission insufficient (with the exact `sudo` hint).

## Layout & deps

```
whyport/
  procfs.py    # sockets, fds, stat parsing (pure stdlib)
  docker.py    # unix-socket HTTP to /var/run/docker.sock, JSON API v1.43+
  gits.py      # subprocess wrappers
  report.py    # rich table optional; plain fallback when not a TTY
  cli.py
```

Zero required dependencies for the MVP. Optional extra `[rich]` for colour/tables. Do **not** depend on `psutil` for the core (it hides the inode trick that makes this work); use it only if you add macOS.

## Tests

- Unit: given fixture strings for `/proc/net/tcp` lines, parse port/IP/state correctly (include IPv4-mapped IPv6 and `0.0.0.0` vs `127.0.0.1`).
- Integration: start `python -m http.server 0` bound to a random port in a subprocess, assert `whoport` finds that exact PID and its cwd.
- Docker test marked `@pytest.mark.docker`, skipped when no socket.
- Fuzz the fd-walk against permission-denied PIDs (must not raise).

## Pitfalls

- **Port reuse / TIME_WAIT**: report state; don't say "in use" for a `TIME_WAIT` socket with no listener.
- Namespaced container ports: the inode will not exist in the host namespace → detect and explain rather than showing "unknown".
- `--kill` must confirm unless `--yes`, must signal the *group* (`os.killpg`) so supervisors don't respawn instantly, and must refuse PID 1.
- Don't parse `/proc` with regex on the whole file; fields are positional and version-stable.
- systemd socket activation: the listener is `systemd`, the service is elsewhere — resolve with `systemctl list-sockets` if available, else note it.

## Definition of done

`whoport 8000` answers "which project, which commit, how do I stop it" in under 100 ms with no dependencies, and `--json` is stable enough to script against.
