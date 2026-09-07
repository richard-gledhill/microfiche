"""Combines stage 1 (group) and stage 2 (category) confidence into one overall score."""

from __future__ import annotations


def combine_confidence(group_confidence: float, category_confidence: float) -> float:
    """Overall confidence is the minimum of the two stages: a confident category guess under
    an unconfident group guess is still an unconfident result overall."""

    return min(group_confidence, category_confidence)
