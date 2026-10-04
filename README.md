# microfiche

[![Release](https://img.shields.io/github/v/release/richard-gledhill/microfiche)](https://github.com/richard-gledhill/microfiche/releases)
[![Build status](https://img.shields.io/github/actions/workflow/status/richard-gledhill/microfiche/main.yml?branch=main)](https://github.com/richard-gledhill/microfiche/actions/workflows/main.yml?query=branch%3Amain)
[![Commit activity](https://img.shields.io/github/commit-activity/m/richard-gledhill/microfiche)](https://img.shields.io/github/commit-activity/m/richard-gledhill/microfiche)
[![License](https://img.shields.io/github/license/richard-gledhill/microfiche)](https://github.com/richard-gledhill/microfiche/blob/main/LICENSE)

A personal library file manager built in python.

`microfiche` automatically organizes, categorizes, and files reference materials —
requirements, design notes, research, correspondence — into a structured library. It takes a folder of uncategorized
documents and sorts them with minimal manual effort. It's Obsidian-friendly, can run as an automated task.

- **Documentation**: <https://richard-gledhill.github.io/microfiche/>
- **Source code**: <https://github.com/richard-gledhill/microfiche>

---

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [How a library is organised](#how-a-library-is-organised)
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

- Python 3.11+
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

## How a library is organised

A library is a folder with two levels of subfolders — **library › group › category** — plus a
`_sorting/` inbox where new documents are dropped:

```text
Library/
├── _sorting/             <- inbox: drop new documents here (the name is configurable)
├── .microfiche/          <- config and records (hidden)
├── <group>/              <- level 1: what a document belongs to
│   ├── <category>/       <- level 2: where the file lands
│   └── <category>/
└── <group>/
    └── <category>/
```

microfiche reads those folders as the taxonomy, so there is no separate category list to maintain.
To file a document it first finds the **group** — the group's name appearing in the document's text
(with fuzzy matching for near misses) — then the **category** within that group: the category's
name appearing in the text, or any keywords you configure as hints for it. A leading number like
`01 ` is ignored when matching, so you can use it to keep folders in order.

*Group* and *category* are roles, not meanings: what they stand for is up to you. A few taxonomies
that fit:

| Use case | Group | Category | Example path |
|---|---|---|---|
| Project documents (the default example) | project | document type | `Project Phoenix/02 Architecture/` |
| Project documents by stage | project | stage | `Project Phoenix/03 Build/` |
| Client work | client | document type | `Acme Ltd/Contracts/` |
| Study | course or subject | topic or week | `Machine Learning/Week 04/` |
| Household admin | area | topic | `Home/Insurance/` |

For example, to organise by **project › stage**, create a folder per project with a folder per
stage, then give each stage some keywords so documents that don't literally say "design" or
"build" still land in the right place:

```text
Library/
└── Project Phoenix/        <- group: the project
    ├── 01 Discovery/       <- category: a stage
    ├── 02 Design/
    ├── 03 Build/
    └── 04 Launch/
```

```toml
# .microfiche/microfiche-config.toml — keys are the category folder names, exactly as written
[category_hints.categories]
"01 Discovery" = ["interview", "problem statement", "user research"]
"02 Design" = ["wireframe", "mockup", "design decision"]
"03 Build" = ["implementation", "pull request", "release notes"]
"04 Launch" = ["go-live", "rollout", "launch plan"]
```

Things to keep in mind when choosing names:

- **Groups are matched by name only** (there are no keyword hints for groups), so pick names that
  actually appear in your documents — project, client or course names usually do. A document that
  doesn't mention any group goes to **Needs review** and stays in the inbox.
- **Categories can use hints**, so they don't need to appear literally in the text.
- **Exactly two levels** are supported today; deeper folder trees aren't.

See [How to use microfiche](https://richard-gledhill.github.io/microfiche/how-to-use/) for a
walk-through.

## Usage

Point microfiche at a library — a folder with a `_sorting/` inbox and `group/category`
subfolders (see [How a library is organised](#how-a-library-is-organised)) — and sort whatever's
been dropped into it:

```bash
uv run microfiche sort --library ~/Documents/Library
```

```text
Filed: 12
Needs review: 3
  architecture_notes.docx -> Project Phoenix/02 Architecture (confidence 0.91, via rules_engine)
  ...
Job: 20261004-153012-a1b2c3
Undo with: microfiche rollback --library <your library> --job-id 20261004-153012-a1b2c3
```

Other commands:

```bash
uv run microfiche reclassify --library ~/Documents/Library   # re-review already-filed documents (dry run)
uv run microfiche reclassify --library ~/Documents/Library --apply   # ...and re-file the ones marked "move"
uv run microfiche propose-categories --library ~/Documents/Library
uv run microfiche audit --library ~/Documents/Library
uv run microfiche rollback --library ~/Documents/Library --job-id <id>
```

Run `uv run microfiche --help` for the full command reference.

## Configuration

Each library reads its own `.microfiche/microfiche-config.toml` file (the folder is dot-prefixed so it stays out of
Obsidian's or similar file explorer). To set up a new library, copy the defaults from
[`microfiche/`](https://github.com/richard-gledhill/microfiche/tree/main/microfiche) into it as `.microfiche/`, then adjust as needed:

| Section | Purpose |
|---|---|
| `library_structure` | The group/category hierarchy (only the default two levels are implemented today) and `library_inbox`, the name of the inbox folder (default `"_sorting"`). |
| `classification` | `confidence_threshold` (0–1, default 0.75, [measured](https://github.com/richard-gledhill/microfiche/blob/main/docs/development/calibration.md)): how sure microfiche must be to file a document without review. Keyword hints score 0.75 and AI answers 0.70, so the default files hints but not AI answers; raise it to hold hints for review, lower it to 0.7 to file AI answers. |
| `exclusions` | Folders never treated as a category and never scanned into. |
| `obsidian` | Turns Obsidian `index.md` generation on/off and sets tag governance mode. |
| `categories` | Keyword hints per *existing* category name — not the category list itself. |
| `filing_rules` | Filename-glob rules, checked before keyword hints. |
| `naming_rules` | Regex rename rules applied to filenames before filing (empty by default). |
| `library_templates` | Category sets for a future `create-library`/`init` command. |

See [docs/development/architecture.md](https://github.com/richard-gledhill/microfiche/blob/main/docs/development/architecture.md)
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
├── microfiche/     # default per-library config, copied into a library's .microfiche/
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

See [CONTRIBUTING.md](https://github.com/richard-gledhill/microfiche/blob/main/CONTRIBUTING.md) for full guidelines.

Or if you are so inclined or use this for commercial work you can
[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/richardgledhill)

## License

Distributed under the MIT license. See [LICENSE](https://github.com/richard-gledhill/microfiche/blob/main/LICENSE) for details.
