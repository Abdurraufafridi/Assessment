"""Unit tests for ingestion metadata helpers."""

from pathlib import Path

import pytest

from app.ingestion.metadata import infer_metadata, normalise_metadata

pytestmark = pytest.mark.unit


def test_infers_industry_from_proposal_filename() -> None:
    metadata = infer_metadata(Path("proposal_retail2.txt"))

    assert metadata == {
        "document_type": "proposal",
        "proposal_type": "past_proposal",
        "industry": "retail",
    }


def test_infers_transcript_metadata() -> None:
    metadata = infer_metadata(Path("client_transcript.txt"))

    assert metadata["document_type"] == "transcript"
    assert metadata["proposal_type"] == "client_transcript"


def test_metadata_normalisation_keeps_scalars_only() -> None:
    metadata = normalise_metadata(
        {
            "industry": "logistics",
            "priority": 2,
            "verified": True,
            "confidence": 0.9,
            "missing": None,
            "nested": {"not": "allowed"},
        }
    )

    assert metadata == {
        "industry": "logistics",
        "priority": 2,
        "verified": True,
        "confidence": 0.9,
    }
