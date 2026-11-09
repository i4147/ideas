# 64 — `doc-diff` (what actually changed in the instructions)

> **Difficulty 5/10** · **Effort ~6 days** · **Tier: hard**
> **Prior art: ✅ real gap** — `git diff`/`--word-diff`, `redlines` (Markdown-aware diff rendering), `daff` (CSV tables), `codediff`, `pandoc`+`diff`, doc tooling like `mike`/`mike`-style versioned docs, `docs-diff` niche scripts. No tool answers "which *instructions* changed and do they still work".
> **Pivot required?** No. This is one of the strongest remaining ideas: deterministic, testable, and useful to anyone maintaining a manual.

## The problem

`git diff docs/` on a user manual gives 400 lines of churn: reflowed paragraphs, a renamed heading, one moved step, and two genuine instruction changes. A support engineer, a translator, or a docs-as-product owner needs the *instruction-level* diff:

```
STEP CHANGED  "Configure API key" (was step 3, now step 5)
  before: Settings → Developer → API Keys
  after:  Developer tab → Credentials → API keys
STEP REMOVED  "Restart the service"  (v2 no longer requires it)
STEP ADDED    "Verify the webhook endpoint"
MOVED         "Enable 2FA" moved from section "Account" to "Security" (unchanged text)
CODE CHANGED  ```bash npm install acme-cli → npm i -g @acme/cli```
OK            no changes in 41 of 52 code blocks
```

## The design that makes it deterministic (not an LLM guess)

1. **Parse both versions into a step model**, not text. Markdown → `markdown-it-py` tokens → extract:
   - ordered lists (each item = a step, with its nested content flattened),
   - headings (section context for each step),
   - fenced code blocks with their language and position,
   - admonitions/notes,
   - images/tables by content hash.
2. **Match steps across versions** with a cascade:
   - exact normalised text match (lowercase, collapse whitespace, strip punctuation) → unchanged,
   - fuzzy match (token-set ratio ≥ 0.75, `difflib.SequenceMatcher` or `rapidfuzz`) → *changed* (keep as a pair, show a word-level diff),
   - positional match for short steps ("Click Save") disambiguated by parent heading,
   - unmatched old → removed, unmatched new → added.
3. **Classify each change by user impact**: instruction verb changed (`click` → `run`), path/menu changed (code-formatted tokens differ), command changed (code block differs), prerequisite added/removed, or cosmetic (typos, phrasing). Only the first four are reported by default — that's the whole value.
4. **Cross-reference code**: for `bash` blocks inside steps, run file 09's help parser (if the project's CLI is available) to detect commands that no longer exist (`acme init` removed). That's a killer feature for CLI manuals and no competitor does it.
5. **Optional LLM polish** (`--summarize`): feed the *structured* change list (not the raw diff) to a local model to phrase it for a human. Because the structure is computed deterministically, the LLM can only phrase it, never invent a change — the failure mode that makes every "AI doc diff" untrustworthy.

## CLI

```bash
doc-diff old.md new.md                            # human summary
doc-diff --ref v1.4 --ref v1.5 docs/               # git refs
doc-diff --ref v1.4 docs/ --format json            # structured, for translation pipelines
doc-diff --ref v1.4 docs/ --breaking-only          # "which instructions must I re-test?"
doc-diff --ref v1.4 docs/ --check-code             # verify CLI commands still exist
```

`--breaking-only` is what a QA engineer runs before a release: it yields the list of instructions whose *outcome* may have changed, which is a test plan.

## Implementation

```
doc_diff/
  mdmodel.py  # markdown-it-py -> Document(sections, steps, code_blocks, tables)
  match.py    # cascade matching, thresholds configurable
  classify.py # change taxonomy + severity
  gyb.py      # optional: CLI help cross-check (import from the help2docs idea)
  render.py   # text, json, markdown
```

Handle: nested lists (step with sub-steps — match the parent, then recurse), steps inside tables (`| Step | Action |`), steps inside `<details>`/admonitions, and images whose `src` changed (visual instruction change — easy to miss, high impact).

## Tests

Golden fixtures of paired Markdown versions covering: unchanged reflow, a reworded step (→ changed, not remove+add), a moved step (position change only → `MOVED`), a merged step (2 → 1), a split step (1 → 2), a changed code block, a changed menu path in inline code, a renamed heading with identical content, a table-based steps section, an image swap, and a file where 40 % of steps changed (report should not be a wall of noise — assert the summary groups by section). Word-level diff tests for escaping (backticks, `|`).

## Pitfalls

- Reflowed text (line breaks moved) must never count as a change: normalise whitespace *before* comparing.
- Fuzzy thresholds are the whole tool: too low → every step "changed"; too high → rewording reported as remove+add. Provide `--similarity 0.75` and show the score in `--format json` so users can tune it.
- Ordering changes alone are often meaningless (steps reordered for clarity) — report `MOVED` separately and *don't* count it as breaking.
- Screenshot-driven docs (images of UIs) can't be compared semantically; hash them and say "image changed, review manually".
- Localisation: run with `--ignore-words` for placeholder names, and never diff translated docs against the source (that's a different tool).
- Don't claim the LLM summary is exhaustive; print the deterministic list and treat prose as a convenience.

## Definition of done

On a 60-page manual between two tags, output is a 10-line summary that a support lead agrees with, `--breaking-only` produces a usable re-test list, and the deterministic core has zero false "changed" verdicts on the reflow fixture.
