"""A single recorded filing action."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

AuditAction = Literal["move", "rename", "classify", "override", "rollback"]


class AuditEvent(BaseModel):
    """One recorded action: a file move, rename, classification decision, or user override."""

    original_path: Path
    new_path: Path | None = None
    action: AuditAction
    timestamp: datetime = Field(default_factory=datetime.now)
