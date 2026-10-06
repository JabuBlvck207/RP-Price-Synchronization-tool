"""Text and product attribute normalization utilities."""

from __future__ import annotations

import re
from typing import Optional


# Common size abbreviations
SIZE_MAP = {
    "sz": "size",
    "sz.": "size",
    "s/z": "size",
    "xl": "xl",
    "xxl": "xxl",
    "xxxl": "xxxl",
    "s": "s",
    "m": "m",
    "l": "l",
}

# Common colour / color normalizations
COLOUR_MAP = {
    "gray": "grey",
    "color": "colour",
}


def normalize_sku(sku: Optional[str]) -> Optional[str]:
    """Normalize SKU for exact matching.

    - Strip leading/trailing whitespace
    - Collapse internal whitespace
    - Uppercase for case-insensitive comparison
    """
    if sku is None:
        return None
    s = str(sku).strip()
    if not s:
        return None
    s = re.sub(r"\s+", "", s)  # remove all whitespace inside SKU
    return s.upper()


def normalize_name(name: Optional[str]) -> Optional[str]:
    """Normalize product name for comparison.

    Steps:
    - lowercase
    - remove unnecessary punctuation
    - normalize whitespace
    - standardize common abbreviations
    - normalize size notation
    """
    if name is None:
        return None
    s = str(name).strip().lower()
    if not s:
        return None

    # Replace common separators with space
    s = re.sub(r"[-_/\\|]+", " ", s)

    # Remove remaining punctuation except alphanumeric and spaces
    s = re.sub(r"[^\w\s]", " ", s)

    # Normalize size abbreviations
    s = re.sub(r"\b(sz|sz\.|s/z)\s*(\d+)", r"size \2", s)
    s = re.sub(r"\bsize\s*(\d+)", r"size \1", s)

    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_size(size: Optional[str]) -> Optional[str]:
    """Normalize size values."""
    if size is None:
        return None
    s = str(size).strip().lower()
    if not s:
        return None
    s = re.sub(r"^(sz|size|s/z)[\s\.\-]*", "", s)
    s = re.sub(r"\s+", "", s)
    return s


def normalize_colour(colour: Optional[str]) -> Optional[str]:
    """Normalize colour / color values."""
    if colour is None:
        return None
    s = str(colour).strip().lower()
    if not s:
        return None
    s = COLOUR_MAP.get(s, s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_brand(brand: Optional[str]) -> Optional[str]:
    """Normalize brand name."""
    if brand is None:
        return None
    s = str(brand).strip().lower()
    if not s:
        return None
    return re.sub(r"\s+", " ", s).strip()


def build_identity_key(
    brand: Optional[str] = None,
    title: Optional[str] = None,
    model: Optional[str] = None,
    colour: Optional[str] = None,
    size: Optional[str] = None,
    extra: Optional[str] = None,
) -> str:
    """Build a composite product identity key for secondary matching.

    Format: BRAND|TITLE|MODEL|COLOUR|SIZE|EXTRA
    """
    parts = [
        normalize_brand(brand) or "",
        normalize_name(title) or "",
        (model or "").strip().lower(),
        normalize_colour(colour) or "",
        normalize_size(size) or "",
        (extra or "").strip().lower(),
    ]
    return "|".join(parts)
