# 03 — `env-stamp` (reproducible environment fingerprints)

> **Difficulty 2/10** · **Effort ~2 days** · **Tier: warm-up**
> **Prior art: ❌ already built** — PyPI `envstamp` 0.2.1 ("atomic, reproducible fingerprints of installed Python distributions"), plus `pip freeze`, `pip-inspect`, `uv pip compile`.
> **Pivot required?** Yes — and the pivot is good: **environment bisect**, not environment printing.

## The problem

"It works on my machine" usually starts with "here is my `pip freeze`" — 200 lines that nobody diffs. The interesting facts (Python build, glibc, locale, which `libssl`, which env vars *differ*) are invisible. And when you do diff, you get 60 changes and no idea which one matters.

## What already exists

| Tool | Gap |
|---|---|
| `pip freeze` / `uv pip list` | versions only; no OS, no env, no redaction |
| `envstamp` (PyPI) | exactly this capture/diff idea, published 2026-10-30 |
| `pip-licenses`, `importlib.metadata` | metadata dumps without comparison workflow |
| `conda env export` | conda only, not portable, leaks paths |

Since `envstamp` ships the capture+diff, the only version worth building changes the question from *"what differs?"* to *"which difference causes the bug?"*.

## The pivot: `bisect`, not `diff`

```
env-stamp capture --out broken.json
env-stamp capture --out good.json          # on the machine where it works
env-stamp diff good.json broken.json       # ranked, grouped by likely relevance
env-stamp bisect --baseline good.json --test "pytest -x tests/test_x.py" --venv .venv
```

`bisect` builds candidate environments in a throwaway venv, applying **one axis at a time** (packages → interpreter patch version → env vars), and binary-searches the smallest change set that flips the test from pass to fail. That is categorically more useful than a diff, and nothing on PyPI does it.

Ranking heuristic for `diff` (this is the part people actually read):

1. interpreter major/minor/build, `sys.abiflags`, glibc/`musl` version
2. packages present/absent (binary-level C-extension packages first: numpy, cryptography, pydantic-core, lxml)
3. packages with changed *major* version
4. locale, `LANG`, filesystem case-sensitivity, umask
5. env-var **names** only, never values

## Capture format

```json
{"schema": 1, "captured_at": "2026-11-09T14:02:11Z", "host": "build-07",
 "python": {"version": "3.12.7", "implementation": "cpython", "abiflags": "",
            "executable_kind": "venv", "platform_tag": "manylinux_2_39_x86_64"},
 "os": {"name": "linux", "distro": "ubuntu 24.04", "kernel": "6.8.0-45", "libc": "glibc 2.39"},
 "packages": [{"name": "numpy", "version": "2.1.3", "direct": true, "installer": "uv"}],
 "env_keys": ["DATABASE_URL", "TZ"],
 "env_redacted": {"TZ": "UTC"},
 "tools": {"pip": "24.2", "uv": "0.5.2", "gcc": "13.2.0"},
 "hash": "blake2b:9f2c…"}
```

Redaction rules (default on, `--no-redact` must be explicit and prints a warning): values of any key matching `(?i)key|token|secret|pass|cred|auth|dsn|url` are dropped, values containing `://user:pass@` are masked, and only *names* of unknown keys are kept. Add `--allow-values TZ,LANG,PYTHONHASHSEED` for the safe, meaningful ones.

## How to build it

```
env_stamp/
  capture.py     # sys.*, platform.*, importlib.metadata.distributions(), /etc/os-release
  redact.py      # deny-list + entropy check; never logs values
  diff.py        # axis-based comparison, returns ranked Change objects
  bisect.py      # venv + pip/uv resolution + subprocess test runner + cache of (set -> bool)
  render.py      # terminal, markdown (for pasting in an issue), json
```

- Environments come from `importlib.metadata.distributions(path=[...])` on an arbitrary venv path — do not activate it.
- `bisect` cost control: cache results keyed by a hash of the package-set delta; cap runs with `--max-runs 12`; support `--parallel` only for axis-level checks, never for a shared venv.
- Never upload anything. `diff` takes two local files; add `--stdin` so a teammate can pipe you their stamp.

## Tests

Golden-file tests for the redactor (fixture of 40 hostile env names, assert no value survives), diff ordering tests, and a fake-package bisect test that installs tiny local wheels you build in `tmp_path` (one pass/fail pair) so no network is needed.

## Pitfalls

- `pip freeze` includes local editable paths and `file://` URLs — leak risk; strip with `--no-paths`.
- Same version, different wheel (e.g. `numpy` built against different BLAS) — capture `installer` and, best effort, `.dist-info/WHEEL` tag.
- `PYTHONHASHSEED` and `TZ` change behaviour silently; keep them in the "safe to show" list.
- Don't claim bisect works for C-level/system-library differences — refuse with a clear message instead of producing a wrong answer.

## Definition of done

`capture` on two machines, `diff` produces ≤10 lines of ranked differences with zero secret leakage, and `bisect` finds the offending package in a real 20-package venv in under 10 runs.
