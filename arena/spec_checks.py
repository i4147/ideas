#!/usr/bin/env python3
"""Mechanical invariants for the 80 idea specs.

Used by tests/test_specs.py (the authority) and runnable standalone:

    python3 arena/spec_checks.py        # human-readable report, exit 1 on failure

Everything here is a pure function over the repo, so the same rules apply in CI,
in a pre-commit hook, and in this script.
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
IDEAS = REPO_ROOT / "ideas"

NAME_RE = re.compile(r"^(\d{2})_([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
DIFFICULTY_RE = re.compile(r"^>\s*\*\*Difficulty\s+(\d+)/10\*\*", re.M)
PRIOR_RE = re.compile(r"^>\s*\*\*Prior art:", re.M)
FILE_REF_RE = re.compile(r"\bfile (\d{2})\b")
MIN_WORDS = 300

ADVISORY = ("## Recommendation", "## Verdict")   # "don't build this" specs
CLOSING = ("## Definition of done",) + ADVISORY


def spec_files(root: pathlib.Path | None = None) -> list[pathlib.Path]:
    """Spec files in filename (= difficulty) order."""
    root = root or IDEAS
    return sorted(root.glob("*.md"))


def _texts(root: pathlib.Path | None = None) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in spec_files(root)}


def check_filenames(root: pathlib.Path | None = None) -> list[str]:
    """Every file is NN_slug.md with a two-digit prefix."""
    return [f"{p.name}: does not match NN_slug.md" for p in spec_files(root) if not NAME_RE.match(p.name)]


def check_numbering(root: pathlib.Path | None = None) -> list[str]:
    """Prefixes are contiguous starting at 01 — no gaps, no duplicates."""
    nums = [int(NAME_RE.match(p.name).group(1)) for p in spec_files(root) if NAME_RE.match(p.name)]
    errors = []
    if nums != list(range(1, len(nums) + 1)):
        missing = sorted(set(range(1, len(nums) + 1)) - set(nums))
        dupes = sorted({n for n in nums if nums.count(n) > 1})
        if missing:
            errors.append(f"missing numbers: {missing}")
        if dupes:
            errors.append(f"duplicate numbers: {dupes}")
        if not missing and not dupes:
            errors.append("numbering is not in sorted order")
    return errors


def check_titles(root: pathlib.Path | None = None) -> list[str]:
    """The H1 carries the same number as the filename."""
    errors = []
    for p in spec_files(root):
        first = p.read_text(encoding="utf-8").splitlines()[0]
        if not first.startswith(f"# {p.name[:2]} —"):
            errors.append(f"{p.name}: H1 is {first[:60]!r}")
    return errors


def check_headers(root: pathlib.Path | None = None) -> list[str]:
    """Each spec declares a 1–10 difficulty and a prior-art verdict."""
    errors = []
    for p in spec_files(root):
        text = p.read_text(encoding="utf-8")
        m = DIFFICULTY_RE.search(text)
        if not m:
            errors.append(f"{p.name}: no '**Difficulty N/10**' header")
        elif not 1 <= int(m.group(1)) <= 10:
            errors.append(f"{p.name}: difficulty {m.group(1)} outside 1–10")
        if not PRIOR_RE.search(text):
            errors.append(f"{p.name}: no '**Prior art:**' header")
    return errors


def difficulty_scores(root: pathlib.Path | None = None) -> list[tuple[str, int]]:
    scores = []
    for p in spec_files(root):
        m = DIFFICULTY_RE.search(p.read_text(encoding="utf-8"))
        if m:
            scores.append((p.name, int(m.group(1))))
    return scores


def check_difficulty_sorted(root: pathlib.Path | None = None) -> list[str]:
    """Difficulty is non-decreasing across the numbering (the whole point of it)."""
    scores = difficulty_scores(root)
    return [
        f"{prev[0]} ({prev[1]}) comes before {cur[0]} ({cur[1]})"
        for prev, cur in zip(scores, scores[1:])
        if cur[1] < prev[1]
    ]


def check_sections(root: pathlib.Path | None = None) -> list[str]:
    """Advisory specs say why not to build; buildable specs carry a test plan."""
    errors = []
    for name, text in _texts(root).items():
        if not any(h in text for h in CLOSING):
            errors.append(f"{name}: no closing section (Definition of done / Recommendation / Verdict)")
        buildable = "## Definition of done" in text
        if buildable and "## Test" not in text:
            errors.append(f"{name}: buildable spec without a test section")
    return errors


def check_length(root: pathlib.Path | None = None) -> list[str]:
    """No stubs: a spec is at least MIN_WORDS words."""
    return [f"{name}: only {len(text.split())} words" for name, text in _texts(root).items()
            if len(text.split()) < MIN_WORDS]


def check_crossrefs(root: pathlib.Path | None = None) -> list[str]:
    """'see file NN' always points at a file that exists."""
    texts = _texts(root)
    known = {name[:2] for name in texts}
    errors = []
    for name, text in texts.items():
        for ref in sorted(set(FILE_REF_RE.findall(text))):
            if ref not in known:
                errors.append(f"{name}: refers to file {ref}, which does not exist")
    return errors


def check_index_fresh(root: pathlib.Path | None = None) -> list[str]:
    """INDEX.md matches what the renderer would produce right now."""
    if __package__ in (None, ""):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        from build_index import render_index  # type: ignore[import-not-found]
    else:
        from arena.build_index import render_index
    index = (root.parent if root else REPO_ROOT) / "INDEX.md"
    if not index.exists():
        return ["INDEX.md is missing"]
    if index.read_text(encoding="utf-8") != render_index():
        return ["INDEX.md is stale — run: python3 arena/build_index.py"]
    return []


CHECKS = {
    "filenames": check_filenames,
    "numbering": check_numbering,
    "titles": check_titles,
    "headers": check_headers,
    "difficulty sorted": check_difficulty_sorted,
    "sections": check_sections,
    "length": check_length,
    "cross-references": check_crossrefs,
    "index fresh": check_index_fresh,
}


def run_all(root: pathlib.Path | None = None) -> dict[str, list[str]]:
    """Run every check; map name -> list of problems (empty list means clean)."""
    return {name: fn(root) for name, fn in CHECKS.items()}


def main() -> int:
    results = run_all()
    width = max(len(n) for n in results)
    for name, errors in results.items():
        status = "ok" if not errors else f"{len(errors)} problem(s)"
        print(f"{name:<{width}}  {status}")
        for error in errors:
            print(f"  - {error}")
    failures = sum(1 for e in results.values() if e)
    print(f"\n{len(spec_files())} specs, {failures} failing check(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
