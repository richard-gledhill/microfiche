"""Combines stage 1 (group) and stage 2 (category) confidence into one overall score."""

from __future__ import annotations

# The confidence a classification must reach before microfiche files a unit on its own.
# Deliberately high: filing is the risky action, and anything below it is left in the inbox for
# review. Against today's signal strengths it lets exact group/category names (0.9-1.0), filename
# rules (0.95) and near-exact fuzzy group matches (>= 0.85) file automatically, but sends keyword-hint
# matches (0.75) and AI-only answers (0.70) to review. A library can lower it with
# `[classification] confidence_threshold` in its config. See docs/development/mvp-roadmap.md for the
# planned calibration of this value against real documents.
DEFAULT_CONFIDENCE_THRESHOLD = 0.8


def combine_confidence(group_confidence: float, category_confidence: float) -> float:
    """Overall confidence is the minimum of the two stages: a confident category guess under
    an unconfident group guess is still an unconfident result overall."""

    return min(group_confidence, category_confidence)
