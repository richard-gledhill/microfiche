"""Moves a classified unit into its target library folder and writes a metadata sidecar."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from core.library.folder_mapping import resolve_target_path
from core.library.naming import apply_naming_rules
from core.models.audit_event import AuditEvent
from core.models.classification import ClassificationResult
from core.models.unit import SortableUnit
from core.utils.filesystem import ensure_dir, safe_move


def file_unit(
    unit: SortableUnit,
    classification: ClassificationResult,
    library_root: Path,
    *,
    naming_rules: dict[str, str] | None = None,
) -> list[AuditEvent]:
    """Move ``unit`` into its classified (group, category) folder and write a metadata sidecar.

    Raises:
        ValueError: if the classification is unresolved - callers must route unresolved
            classifications to the review queue instead of calling this.
    """

    if classification.group.name is None or classification.category.name is None:
        raise ValueError("Cannot file a unit with an unresolved group or category")  # noqa: TRY003

    target_dir = resolve_target_path(library_root, classification.group.name, classification.category.name)
    ensure_dir(target_dir)

    new_name = apply_naming_rules(unit.source_path.name, naming_rules or {})
    destination = target_dir / new_name
    safe_move(unit.source_path, destination)

    _write_metadata_sidecar(destination, unit, classification)

    return [AuditEvent(original_path=unit.source_path, new_path=destination, action="move", timestamp=datetime.now())]


def _write_metadata_sidecar(filed_path: Path, unit: SortableUnit, classification: ClassificationResult) -> None:
    sidecar_path = filed_path.parent / f"{filed_path.name}.metadata.json"
    payload = {
        "group": classification.group.name,
        "category": classification.category.name,
        "unit_type": unit.kind,
        "confidence": classification.overall_confidence,
        "classified_by": classification.classified_by,
        "processed_date": datetime.now().date().isoformat(),
    }
    sidecar_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
