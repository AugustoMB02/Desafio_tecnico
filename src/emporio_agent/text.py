"""Text normalization for accent- and case-insensitive matching."""

from __future__ import annotations

import re
import unicodedata


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize(text: str) -> str:
    """Lowercase, accent-free, punctuation collapsed to single spaces."""
    text = strip_accents(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


def compact(text: str) -> str:
    """Normalized text with no separators: "Takamine GD-20" -> "takaminegd20"."""
    return normalize(text).replace(" ", "")


def tokens(text: str) -> list[str]:
    return normalize(text).split()


def digits(text: str) -> str:
    return re.sub(r"\D", "", text)
