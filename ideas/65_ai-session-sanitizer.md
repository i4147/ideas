# 65 — `ai-session-sanitizer` (export and scrub coding-agent transcripts)

> **Difficulty 5/10** · **Effort ~5 days** · **Tier: hard-ish**
> **Prior art: ⚠️ partial** — `chatgpt-exporter` (browser extension), `claude-code`'s own `--output-format json`/`--resume`, `llm` (Simon Willison: logs every conversation in SQLite with `llm logs`), `aichat` sessions, `claude-conversation-extractor` style scripts, `cursor`/`windsurf` local DBs, and `sentry`-style scrubbing libraries. Fragmented per-tool, none normalising.
> **Pivot required?** Yes — the **normalise + scrub + diff** pipeline is the product; every tool's exporter stops at its own format.

## The problem

You solved a nasty bug with an agent. Now you want to (a) keep the transcript as documentation, (b) share it in a PR or an issue, (c) diff two sessions to see what changed between attempts. Every problem in that list is caused by transcripts containing **your repo's code, absolute paths, API keys, customer data, and the agent's own tool calls**.

```
$ ai-session-sanitizer export --last --out docs/debug-session.md
scanned 412 messages / 61 tool calls
  redacted 3 secrets (openai key, DB url with password, JWT)
  collapsed 21 file-read tool outputs (kept paths, hashed contents)
  normalised 2 formats (claude-code jsonl + generic markdown)
  wrote docs/debug-session.md (41 KB, was 380 KB)
```

## Design

### 1. Format adapters (read-only, never phone home)

- **claude-code**: `~/.claude/projects/<slug>/*.jsonl`, one JSON object per event (`type: user|assistant|tool_use|tool_result`, `sessionId`, `cwd`, `timestamp`).
- **opencode / aider**: `.aider.chat.history.md`, `aider --message` logs, per-project markdown.
- **llm**: SQLite `~/.local/share/io.datasette.llm/logs.db` (`responses`, `prompts`, `conversations`).
- **generic**: markdown/JSON chat exports (ChatGPT/Claude web exports are `conversations.json` arrays with a `mapping` tree — flatten it).
- **generic fallback**: `--format md|jsonl` with a documented minimal schema so any tool can feed it.

Normalised intermediate model (the actual contribution):

```python
Message = {"role": "user|assistant|tool|system", "text": str, "ts": str,
           "tool": {"name": str, "input": dict, "output": str} | None,
           "model": str | None, "tokens": int | None, "source": {"adapter": str, "id": str}}
```

### 2. Scrub (layered, loggable)

Reuse the detector stack from files 22 and 56, plus transcript-specific hazards:

- **Absolute paths** → `~/…`, `<repo>/…`; usernames in paths.
- **Tool outputs**: a `Read` tool result contains entire files. Options: `--tool-output collapse` (default: `[file read: src/x.py, 214 lines, sha256:ab12]`), `keep` (full, with redaction), or `drop`. Collapsing is what turns a 380 KB transcript into 41 KB and removes most leak surface.
- **Code blocks**: keep, but run the secret scanner over them; highlight (don't remove) lines matching secret patterns so a human can review.
- **Customer data**: emails, names, IDs in prompts — mask local parts of emails, keep domain.
- **Session metadata**: strip `sessionId`, user account email, machine hostname, `cwd`.

### 3. Emit

- **Markdown** for humans (`## Turn 3 — tool: Bash` / fenced blocks with language from the tool name), with a front-matter header (tool, model, date, redaction summary, token counts).
- **JSONL** for machine reprocessing; **SARIF**-ish json for a report; a **`.md` with a collapsible `<details>` per turn** (`--collapsible`) for long sessions.
- **Diff mode**: `ai-session-sanitizer diff a.jsonl b.jsonl` → turn-aligned diff (align by user message similarity, not index) showing where the two attempts diverged — genuinely useful for "why did attempt 2 work".

## CLI

```bash
ai-session-sanitizer list                              # sessions found on this machine, with sizes
ai-session-sanitizer export --last --out session.md [--tool-output collapse] [--redact strict|loose]
ai-session-sanitizer preview --last                    # diff of what would be removed
ai-session-sanitizer diff a.md b.md --format md
ai-session-sanitizer stats                             # tokens, tool calls, files touched per session
```

`preview` before `export` mirrors file 56: show the redaction report and a *sample* of the output, then require confirmation.

## Safety and ethics

- Read-only on all source stores; never modify an agent's session files.
- No network. No telemetry.
- A 100 % scrub is impossible: the README must state that output is *reviewed-grade, not leak-proof*, and `--redact strict` should be the default for export to a file that could be shared.
- Handle the case where the transcript itself contains a secret the agent printed from an env var — the same detector catches it, but log it prominently ("secret appeared in output at turn 12; rotate it").

## Tests

Fixture transcripts for each adapter (small, handcrafted JSONL/SQLite). Assert: normalisation to the same model, tool-output collapsing (size reduction and correct placeholder), redaction of 6 planted secret types with no occurrence in the output (grep the emitted file), path normalisation, deterministic output, `diff` alignment on 3 turns with one inserted turn, and that a malformed JSONL line is skipped with a count rather than aborting. Build the SQLite fixture in `tmp_path` with `sqlite3`.

## Pitfalls

- Formats change per tool version: adapter version-detection with a clear "unknown event type, skipped N" counter rather than silent loss.
- Token counting is per-model and not in every record; report `None` honestly (don't estimate from characters and call it tokens).
- Binary/tool outputs (images, base64 screenshots) can be 10 MB per turn — always drop or hash.
- Unicode and ANSI escapes in terminal tool outputs must be stripped, and CRLF normalised.
- Never assume the newest session file is `--last` (concurrent sessions); use mtime + an explicit `--session <id>`.

## Definition of done

`export --last` turns a real 300 KB agent transcript into a 40 KB Markdown file with zero unmasked secrets on the hostile fixture, correct turn structure, and a diff mode that shows where two attempts diverged.
