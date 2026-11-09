# 59 — `shell2py` (record what you did, get a real Python script)

> **Difficulty 5/10** · **Effort ~5 days** · **Tier: hard-ish**
> **Prior art: ⚠️ partial** — `atuin`/`mcfly` (shell history databases, SQL, not codegen), `shellhistory` (0.3.0, visualise history), `plumbum`/`sh` (Python libraries for *writing* shell-like code), `IPython %history -f` (dumps history, no conversion), `bash-to-python` one-off scripts, `bashlex` (bash parser), `thefuck` (fixes commands, no capture).
> **Pivot required?** Yes — capture must be *structured* (exit codes, cwd, timings, stdin/stdout) and the output must be runnable and reviewable, not a naive `subprocess.run` per line.

## The problem

You spend 40 minutes in a shell doing a migration: `cd`, `ls`, `python -c`, `awk`, `find | xargs`, `curl`, `sed -i`, a retry loop. Then someone asks "can you make that a script?" and the answer is "manually, in an hour, and it'll be subtly wrong". Shell history has the commands but not: which ones succeeded, which directory they ran in, what the globs expanded to, or which were exploratory dead ends.

## The honest difficulty

Converting arbitrary bash to Python is a research problem (pipes, redirections, subshells, variable capture, `set -euo pipefail` semantics, `$?`). Do not attempt general translation. Restrict to the "one command per line" case and make the restrictions explicit:

**In scope**: simple commands with args, `cd`, `export`, pipelines (→ `subprocess` with `shell=False` and explicit piping), redirections `>`/`>>`/`2>&1`, `&&`/`||`/`;` sequences, `for x in …; do …; done` with a literal list, and `if command; then …; fi`.
**Out of scope** (flagged, left as a comment): functions, arrays, process substitution, here-docs with interpolation, `eval`, arithmetic `$((...))`, globbing that depends on state, `xargs` with complex quoting.

## Capture: the part that makes it work

A plain history file is not enough. Two capture modes:

1. **Shell hook** (`shell2py install-hook --shell zsh|bash`): a `preexec`/`DEBUG` trap that appends one JSON line per command to `~/.local/state/shell2py/session.jsonl`:
   ```json
   {"seq": 41, "ts_start": "…", "ts_end": "…", "cwd": "/srv/app", "cmd": "python -m alembic upgrade head",
    "exit": 0, "user": "ana", "tty": "pts/4", "session": "2026-11-09T14:02:11Z"}
   ```
   `cwd` is the crucial field history lacks. Use `preexec` for zsh (`$1`, `$PWD`, `$?` from the last command), `PROMPT_COMMAND`/`DEBUG` trap + `history 1` for bash (bash's hook can't see the command directly, so read `history 1` and strip the number — and beware `HISTCONTROL` duplicates).
2. **Import history** (`shell2py import ~/.zsh_history --since today`): works without installing anything, with reduced fidelity (no cwd, no exit codes) — the output then marks every command "unknown result" and requires review.

Annotate interactively during capture: `shell2py mark "this is the migration step"` writes a comment marker, and `shell2py drop <seq>` marks a command as exploratory noise. Without curation, output is 90 % `ls`/`cd`.

## Code generation

Use `bashlex` to parse each command into an AST; for each node type emit a small, opinionated Python pattern:

```python
# from: python -m alembic upgrade head   (exit 0, 2026-11-09 14:07, /srv/app)
subprocess.run(["python", "-m", "alembic", "upgrade", "head"], cwd=ROOT, check=True)
```

Design decisions that reviewers will judge:

- **`check=True`** by default (a script that ignores failures is worse than the shell); commands that failed originally are emitted *commented out* with the exit code, so the transcript stays honest.
- **`cwd` as a parameter**: `ROOT = Path(__file__).resolve().parent` and `cwd=ROOT`, not the absolute path from the recording — portability is the point.
- **Path/variable detection**: any argument that was the current directory becomes `ROOT`, `$HOME` becomes `Path.home()`, `/tmp/xyz-1234` becomes `tempfile.mkdtemp()` with a comment, and hostnames/user names become CLI arguments (`argparse`) at the top of the file. Offer `--params host,db_name` and generate `argparse` automatically.
- **Pipelines** → `subprocess.run(a, stdout=subprocess.PIPE)` then feed `b`; or improve to `sh`/`plumbum` idioms behind `--flavor subprocess|plumbum|sh`. Default `subprocess`: universally readable, no dependency.
- **Idempotency warnings**: detect `mkdir` (→ `parents=True, exist_ok=True`), `cp`/`mv` repeated, `curl -o` overwrite, `rm`, and emit `# NOTE: not idempotent` above them.
- **Header block**: shebang, purpose (from `--title`/markers), `set -euo pipefail` equivalent note, `argparse`, `logging.basicConfig`, a `main()` with steps numbered as comments.
- Run `ruff format` and `ast.parse` on the output in-process (if `ruff` is available) so the generated file is syntactically valid **by construction**, and add a `--check` mode that compiles it.

## CLI

```bash
shell2py install-hook --shell zsh
shell2py list --session last            # the recorded commands, with exit codes
shell2py export --session last --out migrate.py [--params host,db] [--flavor subprocess]
shell2py export --session last --offline   # curated list, no hook data
shell2py explain --session last             # which commands can/can't be converted, and why
```

## Tests

Golden-file tests: fixture session JSONL + expected Python. Cases: a pipeline, `cd` then a relative command, a failing command (commented), `export FOO=bar` → a variable, a `for` loop with a literal list, `$HOME` substitution, an unconvertible function definition (must be emitted as a comment + a `# TODO`), a command containing spaces/quotes/unicode, and a command with a glob that expanded to 3 files (emit the explicit list plus a comment). Also assert the generator never produces code that fails `ast.parse` for 200 randomly generated commands (fuzz with `hypothesis` over an argument alphabet).

## Pitfalls

- Never execute the recorded commands during conversion.
- `shell=False` means globs won't expand: either emit the expanded list (captured via `printf '%s\n' glob` at record time) or use `glob.glob` — never `shell=True` with interpolated user data.
- Secret leakage: a recorded command may contain a token (see file 22). Run the history redactor over the capture and the generated script before writing.
- Bash's `DEBUG` trap fires for every simple command *inside* pipelines and loops, producing duplicate records — dedupe by `(ts_start, cmd)` and document the limitation.
- Don't claim the output is equivalent to bash. State: "positive-path translation; review the diff".

## Definition of done

A real 25-command session converts to a script that runs end to end on a second machine after editing three variables at the top, exit codes preserved, and `--explain` accounting for every command it could not convert.
