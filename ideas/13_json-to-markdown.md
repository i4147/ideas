# 13 — `json-to-markdown` (JSON/YAML/TOML → Markdown tables)

> **Difficulty 2/10** · **Effort ~half a day** · **Tier: warm-up**
> **Prior art: ❌ fully solved, several times** — `jq -r` + shell, `json2md` (npm), `json-to-markdown-table`, `yq -o json | mlr`, pandas `df.to_markdown()`, `tabulate`.
> **Verdict: skip unless you take the pivot.** This is a 60-line function, not a tool.

## The problem

Turning an API response or config file into a table for a README or a chat message. Genuinely annoying, but the amount of code involved is trivial.

## What exists

```bash
jq -r '(.[0]|keys_unsorted) as $k | $k, (.[]|[.[$k[]]]) | @tsv' data.json | column -t -s $'\t'
python -c 'import json,sys,pandas as pd; print(pd.json_normalize(json.load(sys.stdin)).to_markdown())'
```

Plus `csvkit`'s `in2csv -f json`, `miller`'s `mlr --ijson --omd cat`, `yq`, and (for docs) `pandas.DataFrame.to_markdown` inside a notebook. Every one of these already covers "flatten and tabulate". A new package with this exact name would be pure duplication.

## Where any remaining value is

Only two sub-cases are inconvenient in one-liners:

1. **Very large / streaming input** — a 2 GB JSONL file where you want a table of a sample plus a schema summary, not the whole file in memory. (`mlr --ijsonl` already does this well.)
2. **GitHub-flavoured Markdown with escaped pipes, aligned numeric columns, and truncation** — programs that emit tables usually forget that a `|` in a cell breaks the table, that `:` alignment matters for readability, and that a 4,000-character cell should be truncated with a marker.

If you build anything here, build a *library-quality* Markdown table renderer:

```python
from mdtable import render
print(render(rows, columns=["name","size","url"], align={"size": "right"},
             escape=True, max_width=40, truncate_marker="…"))
```

...and expose it as `mdtable --input data.jsonl --columns name,size --max-width 40`. Requirements that make it better than `tabulate`: correct pipe/newline escaping, CJK width awareness via `wcwidth`, alignment inference (numeric right, date centre), and streaming from JSONL.

## Tests

Cells containing `|`, newlines, backticks, emoji, CJK, RTL; zero-width columns; a 1 M-row JSONL with constant memory (assert RSS under a threshold with `tracemalloc`); CRLF input.

## Recommendation

Do not spend a college-team project slot on this. If someone wants a warm-up task, port the escaping/width logic into a 150-line library and publish it as `mdtable` — but check `tabulate` first, since it already handles most of it and is battle-tested.
