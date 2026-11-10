"""Small lexical matching vocabulary. No regex policies or host path resolution."""

from __future__ import annotations

import re
import unicodedata


def identifier_supported(value: str) -> bool:
    if not value or value != value.strip() or value.startswith("//"):
        return False
    if any(character in value for character in ("\\", "%", "?", "#", "@", "*", "[", "]")):
        return False
    if any(unicodedata.category(character).startswith("C") for character in value):
        return False
    scheme, separator, remainder = value.partition("://")
    if separator:
        if not re.fullmatch(r"[a-z][a-z0-9+.-]*", scheme) or not remainder:
            return False
        path = remainder
    else:
        path = value
    parts = path.split("/")
    if any(part in (".", "..") for part in parts):
        return False
    return "" not in parts[1:-1]


def pattern_supported(pattern: str) -> bool:
    if pattern == "*":
        return True
    if "*" in pattern[:-1]:
        return False
    literal = pattern[:-1] if pattern.endswith("*") else pattern
    return identifier_supported(literal)


def matches(pattern: str, identifier: str) -> bool:
    """Callers validate this vocabulary before matching; invalid patterns never match."""
    if not pattern_supported(pattern) or not identifier_supported(identifier):
        return False
    if pattern == "*":
        return True
    return identifier.startswith(pattern[:-1]) if pattern.endswith("*") else identifier == pattern
