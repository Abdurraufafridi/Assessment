"""Unit tests for text cleaning."""

import pytest

from app.ingestion.cleaning import clean_text

pytestmark = pytest.mark.unit


def test_cleaning_normalises_line_endings_and_whitespace() -> None:
    raw = "  Hello\t world  \r\n\r\n\r\nSecond   line \r\n"

    assert clean_text(raw) == "Hello world\n\nSecond line"


def test_cleaning_removes_control_characters_but_preserves_newlines() -> None:
    assert clean_text("alpha\x00beta\ngamma\x7f") == "alpha beta\ngamma"


def test_cleaning_returns_empty_string_for_whitespace_only() -> None:
    assert clean_text(" \n\t\n ") == ""
