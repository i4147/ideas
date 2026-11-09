"""Guard rails for the idea specs: fail CI if the collection drifts out of shape.

Run with:  python3 -m pytest -q      (needs `pip install pytest`)
Each test delegates to arena/spec_checks.py so the same rules apply in a
pre-commit hook or a plain `python3 arena/spec_checks.py` run.
"""
from __future__ import annotations

import pytest

from arena import spec_checks


def test_eighty_specs():
    """Every deduped idea has exactly one file."""
    assert len(spec_checks.spec_files()) == 80


def test_filenames_are_nn_slug():
    assert spec_checks.check_filenames() == []


def test_numbering_is_contiguous():
    assert spec_checks.check_numbering() == []


def test_h1_matches_filename():
    assert spec_checks.check_titles() == []


def test_every_spec_has_a_header():
    assert spec_checks.check_headers() == []


def test_difficulty_is_sorted():
    """Files are numbered in difficulty order — that is the deliverable's contract."""
    assert spec_checks.check_difficulty_sorted() == []


def test_required_sections_present():
    assert spec_checks.check_sections() == []


def test_no_stub_specs():
    assert spec_checks.check_length() == []


def test_cross_references_resolve():
    assert spec_checks.check_crossrefs() == []


def test_index_md_is_current():
    """INDEX.md is generated; a hand edit to a spec must regenerate it."""
    assert spec_checks.check_index_fresh() == []


@pytest.mark.parametrize("name", sorted(spec_checks.CHECKS))
def test_check_is_callable(name):
    """Every registered check returns a list (no exceptions on the real tree)."""
    assert isinstance(spec_checks.CHECKS[name](), list)
