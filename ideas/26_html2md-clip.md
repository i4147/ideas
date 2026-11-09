# 26 — `html2md-clip` (clipboard → clean Markdown)

> **Difficulty 3/10** · **Effort ~2 days** · **Tier: warm-up**
> **Prior art: ⚠️ partial** — `markitdown` (Microsoft, converts many formats incl. HTML→Markdown), `html2text` (the mature converter), `trafilatura` / `readability-lxml` (main-content extraction), `pandoc -f html -t gfm`, `clipboard`/`xclip`/`wl-paste`.
> **Pivot required?** Yes — the value is the *pipeline and the defaults*, not the conversion.

## The problem

Copying a section of a web page and pasting it into a Markdown note yields either (a) rich text that fights you, (b) `xclip -o | pandoc` with 40 lines of nav junk, or (c) an image-less, table-mangled mess. Everyone does this several times a day and the result is always mediocre.

The work is a three-stage pipeline where each stage is a known library, and the *choices* are the product:

```bash
html2md-clip                      # clipboard → Markdown on stdout
html2md-clip --save notes/x.md --title "Postgres locking"
html2md-clip --url https://… --save notes/x.md        # fetch instead of clipboard
html2md-clip --frontmatter --source-url               # add YAML with title/source/date/word-count
```

## Stage design

1. **Acquire.** Wayland: `wl-paste --type text/html` (fall back to `--type text/plain`). X11: `xclip -selection clipboard -t text/html -o` or `xsel`. macOS `pbpaste`. Detect session via `WAYLAND_DISPLAY`/`DISPLAY`. If HTML is unavailable, accept plain text and *still* run minimal cleanup (list restoration from bullets, code fence detection from indentation).
2. **Extract main content.** Prefer the HTML flavour of *boilerplate* removal: `trafilatura.extract(..., output_format="markdown", include_links=True, include_tables=True)` — it already handles nav/footer/comment stripping and emits Markdown. Use `readability-lxml` as an alternative (`--engine readability`), and "no extraction" (`--engine raw`) for cases where you copy from a docs page where the whole structure matters.
3. **Clean.** This is where a tool earns its keep:
   - collapse ≥3 blank lines, strip trailing spaces, normalise list markers to `-`;
   - **absolutise relative URLs** against the source URL (broken relative links are the #1 defect in pasted Markdown);
   - strip tracking params (`utm_*`, `fbclid`, `gclid`, `ref`, `si`) from links, with a `--keep-params` escape;
   - convert inline images ≤ 200 KB? No — instead, list image URLs in a footer or `--download-images DIR`;
   - unwrap `<figure>` captions into italic lines, keep table alignment, fence code blocks with the detected language (from `class="language-py"` / Prism `brush:` / highlight.js classes);
   - strip zero-width characters and soften curly quotes optionally (`--ascii-quotes`).
4. **Emit.** Markdown to stdout (so it pipes), or write a file with an optional front matter block (`title`, `source`, `captured`, `words`).

## Why nobody has exactly this

`markitdown` is a library-first converter for documents, aimed at LLM ingestion; it doesn't care about your clipboard, your note format, or link cleanliness. `html2text` is a converter with 60 options and raw HTML expectations. `pandoc` needs you to get the HTML out of the clipboard first (which is the annoying part) and produces a different Markdown dialect. The missing 40 lines are platform clipboard handling + sane defaults.

Honest sizing: this is a **weekend tool**, not a project. Good warm-up for one person; do not put two people on it.

## Tests

Fixture HTML snippets: `example.com`-style article with nav/aside/footer, a GitHub README render, a table with colspan, a `<pre><code class="language-python">`, relative links + anchor-only links, tracking-laden URLs, an image with `srcset`, and a page whose content is inside a `<div role="main">` with no `<article>`. Assert on golden Markdown (normalise trailing whitespace). Clipboard tests are skipped when no display; test acquisition via a fake `wl-paste` script on `PATH` inside `tmp_path`.

## Pitfalls

- Clipboard HTML often *isn't* HTML (Chrome's `text/html` flavour includes `<!--StartFragment-->` markers — strip them).
- Footnotes and `<sup>` references break badly; if present, keep the raw HTML for that fragment rather than mangling (`--keep-html-fallbacks`).
- Don't make the network call for images by default.
- On Wayland, clipboard access requires the compositor to hand it over; if the owning app closed, the clipboard is empty — report that clearly instead of "no data".
- Non-UTF-8 legacy pages: decode with `charset-normalizer`.

## Definition of done

Copy a Wikipedia section and a Tailwind docs page; both produce Markdown that renders correctly in Obsidian/GitHub with working absolute links, in under a second, with zero manual editing.
