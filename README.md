# microfiche

[![Release](https://img.shields.io/github/v/release/richard-gledhill/microfiche)](https://github.com/richard-gledhill/microfiche/releases)
[![Build status](https://img.shields.io/github/actions/workflow/status/richard-gledhill/microfiche/main.yml?branch=main)](https://github.com/richard-gledhill/microfiche/actions/workflows/main.yml?query=branch%3Amain)
[![License](https://img.shields.io/github/license/richard-gledhill/microfiche)](LICENSE)

`microfiche` automatically organizes, categorizes, and files project reference materials —
requirements, design notes, research, correspondence — into a structured, Obsidian-friendly
library, so individual developers can go from a folder of scattered documents to a ready-to-use
project workspace with minimal manual effort.

- **Documentation**: <https://richard-gledhill.github.io/microfiche/>
- **Source code**: <https://github.com/richard-gledhill/microfiche>

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Development](#development)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- **Rules-first classification** — filename and keyword rules handle the obvious cases; an
  optional local (Ollama) or cloud (OpenAI) AI fallback only kicks in for what the rules can't
  resolve confidently.
- **Your library's folders *are* the taxonomy** — microfiche discovers groups and categories
  from the structure that's already there, rather than imposing a separate category list to
  maintain.
- **Never deletes files** — every move is recorded and reversible with `microfiche rollback`.
- **Obsidian-aware** — generates `index.md` folder notes and governs tags against a canonical
  `TagIndex.md`, so a sorted library is immediately usable as a vault.
- **Fully offline-capable** — no cloud service is required; AI classification is opt-in.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) for dependency management
- Optional, only if you enable AI-assisted classification: a running [Ollama](https://ollama.com)
  server, or an OpenAI API key

## Installation

microfiche isn't published to PyPI yet — install it from source:

```bash
git clone https://github.com/richard-gledhill/microfiche.git
cd microfiche
uv sync
```

This installs the `microfiche` CLI into the project's virtual environment, runnable via
`uv run microfiche`.

## Usage

Point microfiche at a library — a folder with a `_sorting/` inbox and `group/category`
subfolders (see [Configuration](#configuration)) — and sort whatever's been dropped into it:

```bash
uv run microfiche sort --library ~/Documents/Projects
```

```text
Filed: 12
Needs review: 3
  architecture_notes.docx -> Project Phoenix/02 Architecture (confidence 0.91, via rules_engine)
  ...
```

Other commands:

```bash
uv run microfiche resort --library ~/Documents/Projects   # re-review already-filed documents (dry run)
uv run microfiche propose-categories --library ~/Documents/Projects
uv run microfiche audit --library ~/Documents/Projects
uv run microfiche rollback --library ~/Documents/Projects --job-id <id>
```

Run `uv run microfiche --help` for the full command reference.

## Configuration

Each library reads its own `.microfiche-config/` folder (dot-prefixed so it stays out of
Obsidian's file explorer) — copy the defaults from [`microfiche-config/`](microfiche-config)
into a new library to get started, then adjust as needed:

| File | Purpose |
|---|---|
| `library_structure.yaml` | Depth of the group/category hierarchy (default: 2 levels). |
| `exclusions.yaml` | Folders never treated as a category and never scanned into. |
| `obsidian.yaml` | Turns Obsidian `index.md` generation on/off and sets tag governance mode. |
| `categories.yaml` | Keyword hints per *existing* category name — not the category list itself. |
| `filing_rules.yaml` | Filename-glob rules, checked before keyword hints. |
| `naming_rules.yaml` | Regex rename rules applied to filenames before filing (empty by default). |
| `library_templates.yaml` | Category sets for a future `create-library`/`init` command. |

See [docs/development/architecture.md](docs/development/architecture.md)
for the full design behind these.

## Development

Clone the repo and set up the environment:

```bash
git clone https://github.com/richard-gledhill/microfiche.git
cd microfiche
make install
```

`make install` runs `uv sync` across the `core`/`cli` workspace and installs the pre-commit
hooks. Run the quality checks before committing:

```bash
uv run pre-commit run -a
make check
```

## Testing

```bash
make test
```

or directly:

```bash
uv run pytest
```

## Project Structure

microfiche is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) with
two packages:

```text
microfiche/
├── packages/
│   ├── core/src/core/    # scanning, classification, filing, library/Obsidian logic
│   └── cli/src/cli/      # the microfiche Typer CLI
├── microfiche-config/     # default per-library config, copied into a library's .microfiche-config/
├── tests/
│   ├── core/, cli/        # unit tests, mirrors the packages/ layout
│   └── mock_library/       # a hand-built library fixture for integration-style tests
└── docs/                  # PRD, architecture decisions, and mkdocs source
```

## Contributing

Contributions are welcome. Please open an issue before starting significant work so we can
agree on the approach, then:

1. Fork the repo and create a branch off `main`.
2. Make your change, with tests.
3. Run `uv run pre-commit run -a` and `uv run pytest` locally.
4. Open a pull request describing what changed and why.

See [CONTRIBUTING.md](CONTRIBUTING.md) for full guidelines.

Or if you are so inclined or use this for commercial work you can
[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/richardgledhill)

## License

Distributed under the MIT license. See [LICENSE](LICENSE) for details.
