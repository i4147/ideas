# 67 — `zettel` (Zettelkasten in Markdown, with a graph you can see)

> **Difficulty 5/10** · **Effort ~6 days** · **Tier: hard**
> **Prior art: ❌ crowded and opinionated** — `zk` (Go, excellent: notes, backlinks, FTS, LSP, graph export), `nb` (bash, plain-text notes + links + search), `neuron` (Haskell, Zettelkasten with a web UI), `obsidian`/`logseq` (GUI), `zk`'s `--graph`, `markdown-note` (0.1.4 PyPI), `pandoc`, `mermaid` for rendering, `foam` (VS Code).
> **Merged from:** "CLI Zettelkasten with Mermaid export", "terminal digital-garden indexer".
> **Pivot required?** Yes — authoring and backlinks are solved by `zk`. Only **integrity auditing** of an existing vault is thin.

## What exists

`zk list --linked-by <id>`, `zk graph --format mermaid`, full-text search, LSP completion of links, templates — `zk` does all of it, in one static binary, with a plugin system. A Python reimplementation of note-taking + linking + search is a 2-week exercise that ends up worse than `zk`.

## The narrow pivot: the vault *auditor*

Real Zettelkasten vaults rot in specific, checkable ways, and no tool reports them:

```
$ zettel audit ~/vault
NOTES 1,204 (markdown) · LINKS 3,918 · ORPHANS 84
BROKEN LINKS (23)
  notes/atomic-notes.md:12  [[zettelkasten-method]]     → no such note (closest: zettelkasten-principles, 0.82)
  notes/pkm.md:4            ![[diagram.png]]           → missing attachment
DUPLICATE IDEAS (6 pairs, title+content similarity ≥ 0.85)
  notes/spaced-repetition.md ≈ notes/srs.md             → merge or link
HUB NOTES (fan-in)
  notes/index-pkm.md  41 backlinks, 0 outbound      ← is this intentional? (MOC or dumping ground)
DEAD ENDS (37)   notes with neither backlinks nor tags
TAGGING DRIFT (14 tags, 3 pairs too similar)
  #pkm / #PKM · #zettelkasten / #zettel · #note-taking / #notes
STALE (0 outbound links, untouched 400d) 212 notes   ← these are where the vault dies

EXPORT  mermaid graph → vault-graph.mmd (1,204 nodes, 3,918 edges)
```

That report is a maintenance ritual, not a note-taking app: run monthly, fix the top 10. It's also the only thing here that doesn't require you to *change* your editor.

## Design

- **Input**: any Markdown vault (Obsidian, Logseq, plain folders), links in `[[wikilink]]`, `[[target|alias]]`, `![[embed]]`, `[md](relative.md#heading)`, and tag syntax `#tag` / `#nested/tag`.
- **Parsing**: `markdown-it-py` tokens + a regex pass for wikilinks (which aren't standard Markdown). Build an index: note → outbound links (with line numbers), note → tags, note → headings (for `#heading` anchor validation), note → attachments.
- **Resolution**: wikilinks resolve by filename stem (case-insensitive), then by path suffix, then by title front-matter — matching Obsidian's rules rather than inventing your own, or every vault reports 200 broken links.
- **Similarity**: for duplicate detection, normalise (strip front-matter/code), compute TF-IDF cosine over shingles; report pairs ≥ threshold with the top shared terms as evidence. Cheap, no embeddings.
- **Graph export**: Mermaid `graph LR` with subgraphs per folder, node labels = titles, edges = links; cap nodes (`--max-nodes 200`) and pre-filter to the top-N by degree for the readable version, with `--full` for the raw one. Optionally Graphviz DOT for a full render.
- **Fix mode** (`--fix --dry-run`): only unambiguous repairs — retarget a broken link to the single high-confidence candidate (≥0.9 similarity), normalise tag case, and add a `[[missing-note]]` stub file. Never merge notes automatically.

## CLI

```bash
zettel audit ~/vault [--json]
zettel graph ~/vault --format mermaid|dot [--focus note-id --depth 2]
zettel search "advisory locks" --context 2      # grep-with-ranking over the vault
zettel orphans | deadends | tags --drift
zettel new "Atomic notes" --link zettelkasten-method   # create with a link back (the only authoring feature)
```

## Tests

Fixture vaults: a wikilink to a file with spaces, a case-mismatched link, an alias link, an embed of a missing image, a `#heading` anchor that no longer exists, a note with 40 backlinks, two near-duplicate notes, tag case variants, a folder with 500 notes (performance), and a vault with front-matter `title` differing from the filename. Assert counts exactly — audit tools live or die by precise numbers.

## Pitfalls

- Case-insensitive filesystems vs case-sensitive vaults: resolve case-insensitively but report the mismatch.
- Obsidian resolves duplicate filenames by shortest path; if you don't, you get false broken links.
- Front-matter is YAML: a note with invalid YAML front-matter must be reported as a parse error, not crash the audit (and it's a common vault defect).
- Emoji/unicode in filenames break Mermaid rendering; sanitise node ids.
- Never rewrite files without `--fix --dry-run` output shown first; a vault is irreplaceable (it's years of thinking).

## Definition of done

`audit` on a 1,000-note Obsidian vault finds real broken links and duplicate pairs in under 3 s, the Mermaid graph renders in Obsidian/GitHub, and `--fix --dry-run` proposes only repairs a human would accept.
