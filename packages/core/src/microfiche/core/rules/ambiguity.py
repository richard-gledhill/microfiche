"""Choosing one candidate from several, or holding the stage when the evidence is too close to call."""

from __future__ import annotations

from dataclasses import dataclass

from microfiche.core.rules.normalise import contains_words


@dataclass(frozen=True)
class Candidate:
    """One name the text gave evidence for.

    Attributes:
        name: The folder name, as written.
        confidence: How sure the evidence is, from 0 to 1.
        reason: Why it is a candidate, used as the match's reason if it wins.
        phrase: The words that matched (a folder name or a hint, as compared), used to drop a candidate whose words
            are part of another candidate's.
    """

    name: str
    confidence: float
    reason: str
    phrase: str


@dataclass(frozen=True)
class Choice:
    """The outcome of choosing among candidates.

    Attributes:
        winner: The one candidate that clearly leads, or ``None`` if there is none or the lead is too close to call.
        close: When the lead is too close to call, every candidate within the margin of the best, strongest first;
            otherwise empty.
    """

    winner: Candidate | None = None
    close: tuple[Candidate, ...] = ()

    @property
    def ambiguous(self) -> bool:
        return bool(self.close)

    def reason(self, kind: str) -> str:
        """The sentence for an ambiguous choice, naming what it is between and how sure each is."""

        listed = ", ".join(f"'{c.name}' ({c.confidence:.2f})" for c in self.close)
        return f"Several {kind} match about equally well: {listed}"


def choose(candidates: list[Candidate], margin: float) -> Choice:
    """Pick the leading candidate, unless another is within ``margin`` of it.

    A candidate whose words are a whole-word part of another candidate's (``Home`` inside ``Home Insurance``) is
    dropped first, so a long name is not ambiguous with its own prefix. The result does not depend on the order of
    ``candidates``.

    Args:
        candidates: Everything the text gave evidence for.
        margin: How close (0 to 1) the runner-up's confidence may be to the best's before neither is chosen. At 0 only
            an exact tie is held.

    Returns:
        The winner, or the candidates that are too close to call, or neither if there were no candidates.
    """

    kept = [c for c in candidates if not any(_inside(c, other) for other in candidates)]
    if not kept:
        return Choice()
    best = max(c.confidence for c in kept)
    close = sorted(
        (c for c in kept if round(best - c.confidence, 6) <= margin),
        key=lambda c: (-c.confidence, c.name),
    )
    if len(close) > 1:
        return Choice(close=tuple(close))
    return Choice(winner=close[0])


def _inside(candidate: Candidate, other: Candidate) -> bool:
    return candidate.phrase != other.phrase and contains_words(other.phrase, candidate.phrase)
