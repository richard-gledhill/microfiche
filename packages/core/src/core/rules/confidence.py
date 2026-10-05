"""Combines stage 1 (group) and stage 2 (category) confidence into one overall score."""

from __future__ import annotations

# The confidence a classification must reach before microfiche files a unit on its own.
# Chosen by measurement, not guesswork: see docs/development/calibration.md. It equals the keyword-hint
# score, so exact names (0.9-1.0), filename rules (0.95), near-exact fuzzy group matches (>= 0.85) and
# keyword-hint matches (0.75) all file automatically, while AI-only answers (0.70) go to review. On the
# calibration corpus a higher threshold files less but is no more accurate about what it does file.
# A library can change it with `[classification] confidence_threshold` in its config.
DEFAULT_CONFIDENCE_THRESHOLD = 0.75


def combine_confidence(group_confidence: float, category_confidence: float) -> float:
    """Combine the two stages' confidence into the overall confidence.

    The overall confidence is the minimum of the two stages: a confident category guess under
    an unconfident group guess is still an unconfident result overall.

    Args:
        group_confidence: Confidence in the resolved group.
        category_confidence: Confidence in the resolved category.

    Returns:
        The lower of the two.
    """

    return min(group_confidence, category_confidence)
