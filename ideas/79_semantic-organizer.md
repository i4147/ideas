# 79 — `sortby-content` (organize files by what they contain)

> **Difficulty 7/10** · **Effort ~8 days** · **Tier: hard**
> **Prior art: ⚠️ thin, but the pieces exist** — `trafilatura`/`pypdf`/`python-docx` (text extraction), `sentence-transformers` (embeddings), `txtai` (embedding index + search), `ollama` (local LLM/embeddings), `langchain` document loaders, `organize`/`czkawka` (rule-based), macOS Hazel (rules), `docx2txt`, `pytesseract` (OCR).
> **Related:** rule-based sorting is file 06 (`download-sort`) — this is the embedding-based half.
> **Pivot required?** Yes, twice: **classification strategy** and **safety model**.

## The problem

`~/Downloads` and `~/Documents` are full of `Tax Invoice 2023.pdf`, `scan_0042.pdf`, `Research_Notes.txt`, `IMG_20240103.jpg`. Extension-based sorting puts all PDFs together; scanning a passport lands next to a conference ticket. The stated goal — "move documents related to taxes to Finance, based on content" — is a *classification* problem with three possible implementations, only one of which is defensible.

## Three approaches, ranked by honesty

| Approach | How | Verdict |
|---|---|---|
| **Zero-shot LLM labels** | ask a local model "is this Finance, Medical, Study, or Other?" per file | expensive (1 call/file), non-deterministic, unexplainable, but flexible |
| **Embeddings + centroids** | embed each file's text, cluster, name clusters | no names without human input; clusters are unstable run to run |
| **Exemplar-based (recommended)** | you give 3–10 example files per folder; each new file is assigned to the nearest folder centroid, with a confidence | deterministic-ish, explainable ("closest to `Finance/invoice-acme.pdf`, 0.83"), cheap, tunable |

Recommend the third. It also gives a natural UI: `sortby-content train ~/Documents` (learn folder structure from what you already organised), then `sortby-content plan ~/Downloads`.

## Design

```bash
sortby-content train ~/Documents --folders Finance,Medical,Study,Travel  # build centroids
sortby-content plan ~/Downloads --threshold 0.72 --json       # no changes, shows assignments
sortby-content apply --plan .sortby/plan-20261109.json --yes  # moves, with undo journal (file 06)
sortby-content explain ~/Downloads/scan_0042.pdf              # nearest exemplars + extracted text snippet
sortby-content review                                          # items below threshold, for manual filing
```

Output must include the *evidence*, or nobody will trust it:

```
plan: 412 files
  → Finance/Invoices   89  (avg conf 0.86)   e.g. "INVOICE #2026-0412 … Acme Ltd … Total 1,204.00"
  → Medical            23  (avg conf 0.81)
  → Study              54  (avg conf 0.78)
  → UNSURE             61  ← 0.60–0.72, listed for manual review
  → NO TEXT            185 ← scanned images/PDFs without a text layer (OCR disabled)
```

## Implementation

```
sortby_content/
  extract.py   # PDF (pypdf first page + metadata), docx, txt/md, html (trafilatura), images (EXIF + filename),
               # optional OCR via tesseract if installed (--ocr, slow, explicit)
  embed.py     # sentence-transformers (all-MiniLM-L6-v2, 80MB, CPU ~200 files/s) OR ollama /api/embeddings
  index.py     # npz/npy of vectors + a sqlite table of (path, hash, folder, text_len)
  classify.py  # cosine to per-folder centroid + kNN vote over exemplars; threshold + margin
  plan.py      # plan/apply/undo journal (reuse file 06's format)
```

Key technical choices:

- **Chunking**: embed the first ~2,000 characters (invoices put the key facts at the top) plus filename, and average with the filename embedding weighted 0.3. Whole-document averages dilute signal.
- **Margin over threshold**: assign only if `best_score - second_best ≥ --margin 0.05`; otherwise UNSURE. This single rule removes most bad assignments.
- **Incremental index**: hash file content; never re-embed unchanged files.
- **Determinism**: fixed model version pinned in the index metadata; a model change invalidates centroids (report it, offer `retrain`).
- **Fallback without ML**: `--no-embeddings` uses TF-IDF + cosine over the same exemplars. Slightly worse, zero 400 MB dependency, works offline immediately. Ship it as the default and make embeddings an extra.

## Safety (the part that matters most)

- **Never move without a plan**; `apply` requires `--yes` and writes an undo journal (see file 06).
- **Nothing leaves the machine**: models are local; a `--provider` option to a cloud API must print a warning listing file names that will be sent.
- **Symlinks, duplicates, and conflicts**: skip symlinks; dedupe by content hash first (report reclaimable space); never overwrite.
- **Don't touch** files modified in the last 24 h, anything > `--max-size`, `.git` dirs, or paths outside `--root`.
- **Privacy**: this tool reads *everything* in a folder. Print the exact file count it will read before reading, and store extracted text in a cache the user can delete (`sortby-content cache --clear`). Never persist raw text by default (`--keep-text` opt-in).

## Tests

Fixture corpus: 30 generated files (real minimal PDFs via `reportlab` or a checked-in 2 KB PDF, docx via `python-docx`, txt, a scanned-image-only PDF with no text layer). Assert: extraction yields expected snippets, assignments land in the right folders with the fixed exemplars, UNSURE catches a deliberately ambiguous file, no-text files are reported not guessed, plan changes nothing, apply+undo round-trips paths exactly, and `--no-embeddings` gives ≥90 % of the accuracy on the fixture. Determinism: two runs produce identical plans.

## Pitfalls

- Filenames lie ("Invoice" in a folder of templates) — weight content over name but keep the name as a feature.
- Multi-language corpora: MiniLM is English-centric; document that limitation loudly, and support `--model` for a multilingual alternative.
- OCR is slow (1–3 s/page) and error-prone: default off, cap pages, and never OCR inside `plan`.
- Empty/encrypted PDFs must be reported as no-text, not silently sorted as "Other".
- Moving files breaks links and recent-files lists: default to *copy* with `--copy` for a trial run, and print the difference.
- Embedding models are ~80–500 MB; install on first use with an explicit prompt and a size warning, not silently in a post-install hook.

## Definition of done

With 8 exemplar files per folder, ≥85 % of 30 unseen fixture files land in the correct folder, UNSURE catches the ambiguous third, `plan` → `apply` → `undo` is exact, and everything runs offline on CPU.
