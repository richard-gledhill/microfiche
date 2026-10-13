"""The library's classification ledger: an append-only record of what was filed where, and why."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from microfiche.core.models.ledger import LedgerRecord
from pydantic import ValidationError

LEDGER_FILENAME = "ledger.jsonl"


class LedgerCorruptError(ValueError):
    """Raised when a line of the ledger file can't be read back as a ``LedgerRecord``.

    The ledger is never silently repaired or skipped past: an unreadable line means a record of
    something microfiche did is missing, which the user should know about.
    """

    def __init__(self, path: Path | str, line_number: int, error: Exception | str) -> None:
        self.path = Path(path)
        self.line_number = line_number
        super().__init__(f"Ledger {path} is unreadable at line {line_number}: {error}")


class Ledger:
    """Append-only JSON-lines store of ``LedgerRecord``s at ``<state_dir>/ledger.jsonl``.

    Records are only ever appended, so history is never lost; what the library *currently*
    looks like is derived by replaying them (see ``current``). A unit is identified by its
    ``(path, content_hash)`` pair, so a record can still be found after the file has been moved
    or renamed outside microfiche (see ``lookup``).

    Args:
        state_dir: The library's ``.microfiche`` folder. Created on the first append.
    """

    def __init__(self, state_dir: Path) -> None:
        self._path = state_dir / LEDGER_FILENAME

    @property
    def path(self) -> Path:
        """Where the ledger file lives (it may not exist yet)."""

        return self._path

    def append(self, records: Iterable[LedgerRecord]) -> None:
        """Append ``records`` to the ledger in one write. Does nothing (and creates nothing) if empty."""

        lines = [record.model_dump_json() + "\n" for record in records]
        if not lines:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # newline="\n" keeps the file identical across OSes, so a synced library doesn't churn.
        with self._path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(lines))

    def read_all(self) -> list[LedgerRecord]:
        """Return every record ever written, oldest first, including rolled-back ones.

        Raises:
            LedgerCorruptError: if any line can't be parsed.
        """

        if not self._path.exists():
            return []
        records: list[LedgerRecord] = []
        for line_number, line in enumerate(self._path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                records.append(LedgerRecord.model_validate_json(line))
            except ValidationError as err:
                raise LedgerCorruptError(self._path, line_number, err) from err
        return records

    def current(self) -> list[LedgerRecord]:
        """Return the record for each unit currently filed in the library, oldest first.

        Replays the history: a ``"rolled_back"`` record cancels the ``"filed"`` record it names
        (same job, same path), and a ``"filed"`` record for a unit that was *moved* (its
        ``original_path`` is an earlier record's ``path``) supersedes that earlier record - so
        rolling the move back brings the earlier record back.
        """

        records = self.read_all()
        rolled_back = {(record.job_id, record.path) for record in records if record.event == "rolled_back"}

        by_path: dict[str, LedgerRecord] = {}
        for record in records:
            if record.event != "filed" or (record.job_id, record.path) in rolled_back:
                continue
            by_path.pop(record.original_path, None)
            by_path.pop(record.path, None)  # re-insert so dict order follows recency
            by_path[record.path] = record
        return list(by_path.values())

    def folder_units(self) -> set[str]:
        """The library-relative paths of the folders currently filed whole (``keep_folders``).

        These are content, not parts of the library's structure: a folder microfiche filed as one unit.
        The ledger is read once, however many paths are then tested against the result.
        """

        return {record.path for record in self.current() if record.unit_type == "folder"}

    def lookup(self, path: str, content_hash: str) -> LedgerRecord | None:
        """Find the current record for the unit at ``path`` with ``content_hash``.

        Tries the exact ``(path, hash)`` pair first. If nothing is filed there with that content
        (the file was moved or renamed outside microfiche), falls back to the hash alone - but
        only when exactly one current record has that hash, since identical content filed in two
        places can't be told apart. A file at the right path whose content has since changed
        does not match.

        Args:
            path: Library-relative path with forward slashes.
            content_hash: The unit's ``microfiche.core.utils.hashing.unit_hash``.

        Returns:
            The matching record, or ``None`` if there is no match or the hash alone is ambiguous.
        """

        current = self.current()
        for record in current:
            if record.path == path and record.content_hash == content_hash:
                return record
        same_content = [record for record in current if record.content_hash == content_hash]
        return same_content[0] if len(same_content) == 1 else None
