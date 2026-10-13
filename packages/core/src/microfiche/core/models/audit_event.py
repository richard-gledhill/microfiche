"""A single recorded filing action."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

AuditAction = Literal["move", "rename", "classify", "override", "rollback", "remove_folder", "restore_folder"]


class AuditEvent(BaseModel):
    """One recorded action: a file move, rename, classification decision, user override, or folder removal.

    ``remove_folder`` records an empty inbox folder removed after its files were filed (``new_path`` is ``None``);
    rollback recreates it and records ``restore_folder``. No file is ever deleted: only a folder that is empty.
    """

    original_path: Path
    new_path: Path | None = None
    action: AuditAction
    timestamp: datetime = Field(default_factory=datetime.now)
