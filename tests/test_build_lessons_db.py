"""Tests for scripts/build_lessons_db.py defaults. No textbook data used."""

from pathlib import Path

import pytest
from build_lessons_db import DB_PATH, PAGES_PATH, ROOT, load_lesson_pages


def test_default_pages_file_is_layout_extraction() -> None:
    assert PAGES_PATH == ROOT / "data" / "extracted" / "pages_layout.jsonl"
    assert DB_PATH == ROOT / "data" / "lessons.db"


def test_missing_pages_file_points_to_extract_layout(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        load_lesson_pages(tmp_path / "missing.jsonl")
    assert "scripts/extract_layout.py" in str(exc.value)
