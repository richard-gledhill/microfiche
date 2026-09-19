# Data model: sidecars, audit events, and rollback jobs

The target schema for everything microfiche writes to disk outside of the moved files
themselves. Where the current implementation doesn't yet produce data matching this, that's
tracked as an open item in [mvp-roadmap.md](mvp-roadmap.md), not restated here — this page
describes what the schema *is*, not what's currently wired up to write it.

## Sidecar metadata (`*.metadata.json`)

Written next to every filed document by `core/filer.py::_write_metadata_sidecar`:

```json
{
  "group": "Project Phoenix",
  "category": "01 Requirements",
  "unit_type": "file",
  "confidence": 0.91,
  "classified_by": "rules_engine",
  "processed_date": "2026-09-07"
}
```

This is narrower than the aspirational schema in `architecture.md` §7, which also lists a
`tags` field — not populated today, since Obsidian tag governance (`tag_mapper.py`) isn't
wired into the filing path yet ([mvp-roadmap.md](mvp-roadmap.md)). A folder unit's sidecar is
meant to additionally carry the per-document breakdown used to pick the dominant category
(architecture.md §4); that detail isn't in `_write_metadata_sidecar` yet either.

## `AuditEvent`

`core/models/audit_event.py` — one recorded action:

```python
class AuditEvent(BaseModel):
    original_path: Path
    new_path: Path | None = None
    action: AuditAction  # "move" | "rename" | "classify" | "override" | "rollback"
    timestamp: datetime
```

Of the five `AuditAction` values, only two are actually emitted today: `"move"` (from
`filer.py::file_unit`) and `"rollback"` (from `rollback.py::rollback_job`). `"rename"`,
`"classify"`, and `"override"` are defined for future use — a rename-rules event, a
classification-decision event, and a user-override event from the (not yet implemented)
review flow — but nothing produces them yet.

## `Job`

`core/models/job.py` — the set of moves made by one `sort`/`resort --apply` run:

```python
class Job(BaseModel):
    job_id: str
    created_at: datetime
    moves: list[AuditEvent]
```

**Canonical path:** `<library_root>/.logs/rollback/job_<id>.json` — dot-prefixed, matching
the `.microfiche-config/` convention, per `cli/commands.py::_LOGS_DIRNAME`. (`job.py`'s own
docstring currently says `logs/rollback/...` without the dot; that's wrong and should be
fixed, not treated as a second valid path.)

`core/rollback.py` provides both directions:

- `save_job(logs_dir, job)` — writes a `Job` to `<logs_dir>/rollback/job_<id>.json`. **Not
  currently called from anywhere** — see [mvp-roadmap.md](mvp-roadmap.md).
- `load_job(logs_dir, job_id)` / `rollback_job(logs_dir, job_id)` — read a job back and
  replay its moves in reverse. These work correctly today, given a job file to read.

## `.logs/` directory layout

```text
<library_root>/.logs/
├── audit.log              # human-readable trail; read by `microfiche audit`
└── rollback/
    └── job_<id>.json       # one Job per sort/resort --apply run; read by `microfiche rollback`
```

`audit.log`'s format isn't defined yet — nothing writes it, so there's no implementation to
derive a format from. The straightforward option is one line per `AuditEvent` (timestamp,
action, original path, new path), but that's a design decision for whoever wires up
[mvp-roadmap.md](mvp-roadmap.md)'s first must-fix item, not something this page prescribes.

## See also

- [architecture.md](architecture.md) §7 — the original sidecar schema sketch this page
  supersedes with the as-implemented version.
- [mvp-roadmap.md](mvp-roadmap.md) — tracks which parts of this schema aren't produced yet.
