# 66 — `later` (local-first read-it-later + bookmark search)

> **Difficulty 5/10** · **Effort ~6 days** · **Tier: hard**
> **Prior art: ❌ very crowded** — `buku` 5.1 (Python, bookmark manager with tags + full-text search + local HTML snapshots), `wallabag` (PHP server + CLI, the read-it-later reference), `archivebox` 0.9.77 (Python, self-hosted archiving), `trafilatura` (extraction), `readability-lxml`, `newsboat` (RSS + macros), `nb`, `urlwatch` (change monitoring), `monolith` (single-file snapshot), `pocket` (shut down 2025, which is exactly why this keeps being proposed).
> **Merged from:** "CLI read-it-later app", `mark` (local bookmarks with full-text search).
> **Pivot required?** Yes, sharply — `buku` + `trafilatura` covers 80 % of this in 300 lines.

## The problem

Pocket's shutdown pushed a lot of people to look for a local, terminal-friendly replacement: pipe a URL in, strip the clutter, read it in `less`, and be able to search everything you ever saved, offline.

## What is genuinely hard here (and what isn't)

Easy: SQLite table, `httpx` fetch, `trafilatura.extract` for main content, `pager` for reading, FTS5 for search. That's a weekend, and `buku`/`trafilatura` already prove it.

Actually hard, and where a new tool could win:

1. **Faithful offline reading.** Reader-mode extraction loses code blocks, tables, footnotes, and figure captions — precisely what technical readers save. Saving the *original HTML* plus extracted text (like `archivebox` does with a full headless browser, or `monolith` with inlined assets) is a storage/complexity trade-off you must make explicitly: `--keep=text|html|snapshot`.
2. **Paywalled / JS-rendered pages**: without a headless browser you get a cookie wall. Decide up front: no browser in v1, and detect the failure signature ("content < 200 words, page has `enable JavaScript`") and say so, rather than saving a useless stub.
3. **Reading state and resumption**: position (byte offset/paragraph index) per article, so `later next` resumes where you left off; a queue that respects "unread → reading → done" and can be filtered by domain/tag/age.
4. **Link rot**: a saved URL dies in 3 years. Store the content hash and a snapshot date, and offer `later verify` that reports dead links (see file 08's checker) — a genuinely useful maintenance command that no reader app gives you.
5. **Import from everywhere**: Pocket/Instapaper/Wallabag/Chrome bookmarks HTML exports, deduped by normalised URL (strip `utm_*`, trailing slash, `www`), preserving tags and timestamps. Migration friction is the main reason people don't switch.

## Design

```bash
later add https://example.com/post --tag postgres --title "Postgres locking"
later add --from-browser                   # read Chrome/Firefox bookmarks export
later list --unread --limit 20
later read 41                              # pager with the saved text (or the HTML snapshot via lynx/w3m if available)
later search "advisory lock"               # FTS5 over extracted text + title
later verify --older-than 1y               # dead-link report
later export --format markdown --out notes/
later stats                                # saved, read, words, domains
```

SQLite schema: `item(id, url, url_normalised, title, domain, added_utc, read_at, position, content_html, content_text, words, hash, status)`, `tag(item_id, tag)`, `item_fts(content_text, title)` with FTS5 external content triggers. Store text in SQLite (compressed with `zlib` if > 100 KB) — a file-per-article layout wastes inodes and breaks search.

## Honest verdict

Ship it only if you commit to the boring-but-rare features: resumption, link verification, and import. Otherwise `buku` (bookmarks + full-text) plus a `trafilatura` one-liner is already the tool, and it's maintained.

## Tests

`respx` fixtures: a normal article, a JS-wall page (must be flagged, not saved silently), a page with `<pre>` blocks and a table (assert they survive extraction), a duplicate URL with different utm params (dedupe), a redirect chain. FTS5 tests: search finds a phrase across two items, ranking sane, and an FTS index rebuilt after a bulk import. Import fixtures: Pocket HTML export, Chrome bookmarks HTML (nested folders), and a CSV with a BOM.

## Pitfalls

- Robots/ToS: fetching a personal copy for reading is normal, but never add a crawler that follows links.
- Respect `--user-agent`, rate limit per domain, and cache aggressively; a reader app that DDoSes a blog is a bug.
- Encoding: declare from meta charset, fall back to `charset-normalizer`; never assume UTF-8.
- Text content is a privacy surface (medical, legal pages): the DB is unencrypted by default — say so, and offer `--db` on an encrypted volume rather than inventing weak crypto.
- Don't store images by default (storage explodes); store the URL list and let the reader fetch on demand.

## Definition of done

`later add` + `later read` gives a clean, resumable reading experience on a technical article including code blocks, `search` finds phrases instantly over 500 saved items, and `verify` reports dead links.
