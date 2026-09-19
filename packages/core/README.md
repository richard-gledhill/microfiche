# core

Core library for [microfiche](../../README.md): document scanning, classification, filing,
and library/Obsidian management logic.

This package is part of the microfiche uv workspace and isn't published or used standalone —
see the [root README](../../README.md) for installation, usage, and configuration, and
[CONTRIBUTING.md](../../CONTRIBUTING.md) for development guidelines.

## Contents

| Module | Purpose |
|---|---|
| `scanner.py`, `extractor.py`, `classifier.py`, `filer.py`, `organizer.py`, `resort.py`, `rollback.py` | The sort pipeline: scan the inbox, classify, file, and undo. |
| `parsers/` | Document parsing (PDF, DOCX, TXT, Markdown, MSG, EML). |
| `rules/` | Deterministic group/category classification rules. |
| `ai/` | Optional Ollama/OpenAI fallback classification. |
| `library/` | Taxonomy discovery, category suggestion, naming, templates. |
| `obsidian/` | `index.md` generation and `TagIndex.md`-governed tagging. |
| `models/` | Shared pydantic models (`Document`, `SortableUnit`, `Taxonomy`, ...). |
| `config.py` | Per-library YAML config loading. |
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
