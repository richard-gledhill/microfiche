# core

Core library for [microfiche](../../README.md): document scanning, classification, filing,
and library management logic. It imports as `microfiche.core`.

This package is part of the microfiche uv workspace and isn't published or used standalone —
see the [root README](../../README.md) for installation, usage, and configuration, and
[CONTRIBUTING.md](../../CONTRIBUTING.md) for development guidelines.

## Contents

| Module | Purpose |
|---|---|
| `scanner.py`, `classifier.py`, `duplicates.py`, `filer.py`, `ledger.py`, `organizer.py`, `reclassify.py` | The sort pipeline: scan the inbox, classify, check for copies, file (recording a job, ledger entries and audit lines), and undo. |
| `review.py`, `runlock.py` | The `ReviewSession` behind `microfiche review`, and the lock that lets only one changing run go at a time. |
| `parsers/` | Document parsing (PDF, DOCX, TXT, Markdown, MSG, EML) behind `read_documents`, with unreadable files reported rather than raised. |
| `rules/` | Deterministic group/category classification rules. |
| `ai/` | Optional Ollama/OpenAI fallback classification. |
| `library/` | The `Library` (layout, exclusions, taxonomy), the library file and its sync, category suggestion, naming. |
| `models/` | Shared pydantic models (`Document`, `SortableUnit`, `Taxonomy`, ...). |
| `config.py` | Per-library TOML config loading. |
| `utils/` | Filesystem, hashing, logging, and validation helpers. |

See [docs/development/architecture.md](../../docs/development/architecture.md)
for the design behind this package.

## Development

From the repo root:

```bash
make install
make test
```

Tests for this package live in [tests/core/](../../tests/core), mirroring the module layout
above.

## License

Distributed under the MIT license, as part of the microfiche project. See
[LICENSE](../../LICENSE).
