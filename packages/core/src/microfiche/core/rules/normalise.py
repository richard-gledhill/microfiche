"""One spelling for comparing folder names, hints and document text, so punctuation and case style don't matter."""

from __future__ import annotations

import re
import unicodedata

_ORDER_PREFIX_RE = re.compile(r"^\d{1,3}[\s\-_.)]+(?=\D|$)")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_APOSTROPHES_RE = re.compile(f"['{chr(0x2018)}{chr(0x2019)}`]")
# Everything but letters, digits and the two symbols that are part of a name (C++, C#) separates words.
_SEPARATORS_RE = re.compile(r"[^\w+#]|_")
_WHITESPACE_RE = re.compile(r"\s+")


def normalise_for_matching(text: str, *, folder_name: bool = False) -> str:
    """Reduce ``text`` to lowercase words separated by single spaces, for comparing only.

    ``Meeting-Notes``, ``meeting_notes``, ``MeetingNotes`` and ``Meeting Notes`` all give ``meeting notes``, and
    ``R&D`` gives ``r and d``. Accents are dropped, apostrophes removed and ``+`` and ``#`` kept (``C++``, ``C#``).
    Nothing on disk is renamed.

    Args:
        text: A folder name, a keyword hint or document text.
        folder_name: Also split camelCase and PascalCase and strip a leading order prefix of one to three digits
            (``01-``, ``02 - ``), as for a folder name. Document text has its own capitalisation and numbers, so
            it is left alone.

    Returns:
        The normalised text, empty if nothing but separators was left.
    """

    if folder_name:
        text = _ORDER_PREFIX_RE.sub("", text)
        text = _CAMEL_BOUNDARY_RE.sub(" ", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = _APOSTROPHES_RE.sub("", text.casefold())
    text = text.replace("&", " and ").replace("@", " at ")
    return _WHITESPACE_RE.sub(" ", _SEPARATORS_RE.sub(" ", text)).strip()
