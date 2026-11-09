# `arena/` — session tooling

Helper scripts written while turning `prompt.md` into the 80 specs in `../ideas/`.
They are committed because the specs make **verifiable claims** (versions, dates,
"this name is taken") and these are the programs that produced and still check them.

| File | Language | What it does | When to run it |
|---|---|---|---|
| `pypi_probe.py` | Python | Queries `pypi.org/pypi/<name>/json` for ~250 candidate + reference names; reports existence, latest version, last upload date, summary. | When adding an idea, or re-checking prior art before starting one. |
| `build_index.py` | Python | Renders `INDEX.md` from the spec files (they are the source of truth). `--check` exits 1 if the committed index is stale. | After editing any spec. |
| `spec_checks.py` | Python | The invariants: contiguous numbering, `NN_slug.md` names, H1 matches prefix, difficulty header, difficulty sorted, required sections, no stubs, cross-refs resolve, index fresh. | Any time; also runs in CI via `tests/`. |
| `run_checks.sh` | Bash | Convenience wrapper: optional `--fix` (regenerate index), then `spec_checks`, then `pytest` if installed. | Before committing spec edits. |

## Examples

```bash
# what did the probe say about a name you are about to publish under?
python3 arena/pypi_probe.py sqlite-scout logfold envstamp

# every reference tool in the second batch, as JSON, for quoting versions
python3 arena/pypi_probe.py --extra --json /tmp/prior-art.json

# after editing a spec
python3 arena/build_index.py          # or: ./arena/run_checks.sh --fix
python3 arena/spec_checks.py

# the pytest wrapper (same checks, CI-friendly)
python3 -m pip install pytest && python3 -m pytest -q
```

## Why these are committed rather than thrown away

- The prior-art verdicts in `ideas/*.md` are load-bearing: 29 of the 80 ideas are marked
  *already solved*. Anyone can re-run the probe and see whether that is still true.
- `INDEX.md` is generated, so a hand-edit would silently drift from the specs.
  `spec_checks.py` makes that drift a test failure instead of a review comment.
- The checks encode the two promises the collection makes: **one file per unique idea**
  and **numbered in difficulty order**.

## Notes

- Python 3.9+ (the sandbox ran 3.11); the specs themselves target 3.12+ on Linux.
- No third-party dependencies. `pytest` is only needed for the wrapper in `tests/`.
- The probe is rate-limit-friendly by default (24 threads, one request per name, no auth).
  A full `--all` run is ~330 requests and takes a few seconds.
