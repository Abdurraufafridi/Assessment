"""Text cleaning and normalisation."""

import re
import unicodedata

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_INLINE_WHITESPACE = re.compile(r"[ \t]+")
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """Normalise unicode and whitespace while preserving paragraph breaks."""

    normalised = unicodedata.normalize("NFKC", text)
    normalised = normalised.replace("\r\n", "\n").replace("\r", "\n")
    normalised = _CONTROL_CHARACTERS.sub(" ", normalised)

    lines = [_INLINE_WHITESPACE.sub(" ", line).strip() for line in normalised.split("\n")]
    normalised = "\n".join(lines)
    normalised = _EXCESS_BLANK_LINES.sub("\n\n", normalised)
    return normalised.strip()
