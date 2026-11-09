"""Metadata inference and normalisation for vector-store records."""

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

MetadataValue = str | int | float | bool
Metadata = dict[str, MetadataValue]

_TRAILING_DIGITS = re.compile(r"\d+$")


def normalise_metadata(metadata: Mapping[str, Any]) -> Metadata:
    """Keep only scalar values supported by Chroma metadata filters."""

    result: Metadata = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or not key:
            logger.warning("ignored_invalid_metadata_key", extra={"key": repr(key)})
            continue
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            result[key] = value
        else:
            logger.warning(
                "ignored_non_scalar_metadata",
                extra={"key": key, "value_type": type(value).__name__},
            )
    return result


def infer_metadata(path: Path) -> Metadata:
    """Infer useful filters from the seed corpus filename conventions."""

    stem = path.stem.lower()
    if stem.startswith("proposal_"):
        industry = _TRAILING_DIGITS.sub("", stem.removeprefix("proposal_")) or "general"
        return {
            "document_type": "proposal",
            "proposal_type": "past_proposal",
            "industry": industry,
        }
    if "transcript" in stem:
        return {
            "document_type": "transcript",
            "proposal_type": "client_transcript",
        }
    return {
        "document_type": "document",
        "proposal_type": "reference",
    }
