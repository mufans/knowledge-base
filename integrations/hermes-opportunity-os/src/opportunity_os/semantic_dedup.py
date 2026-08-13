"""Deterministic semantic similarity for opportunity cards.

The knowledge loop discovered at least four groups of semantically duplicated
opportunity cards (Needle, token cost, self-evolving, validation loop, and
ObjC-to-Swift each appeared more than once). This module provides a title +
summary similarity measure so the save path can reject near-duplicates and a
merge command can collapse existing groups.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Mapping

_TITLE_WEIGHT = 0.7
_SUMMARY_WEIGHT = 0.3


def normalize_text(value: str) -> str:
    return re.sub(
        r"[^a-z0-9\u3400-\u9fff]+",
        "",
        unicodedata.normalize("NFKC", value).casefold(),
    )


def _ratio(left: str, right: str) -> float:
    normalized_left = normalize_text(left)
    normalized_right = normalize_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    return SequenceMatcher(None, normalized_left, normalized_right).ratio()


def semantic_similarity(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    title = _ratio(str(left.get("title", "")), str(right.get("title", "")))
    summary = _ratio(str(left.get("summary", "")), str(right.get("summary", "")))
    return round(_TITLE_WEIGHT * title + _SUMMARY_WEIGHT * summary, 4)


def is_semantic_duplicate(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    threshold: float = 0.85,
) -> bool:
    return semantic_similarity(left, right) >= threshold
