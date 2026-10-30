# microfiche

[![Release](https://img.shields.io/github/v/release/richard-gledhill/microfiche)](https://github.com/richard-gledhill/microfiche/releases)
[![Build status](https://img.shields.io/github/actions/workflow/status/richard-gledhill/microfiche/main.yml?branch=main)](https://github.com/richard-gledhill/microfiche/actions/workflows/main.yml?query=branch%3Amain)
[![Commit activity](https://img.shields.io/github/commit-activity/m/richard-gledhill/microfiche)](https://img.shields.io/github/commit-activity/m/richard-gledhill/microfiche)
[![License](https://img.shields.io/github/license/richard-gledhill/microfiche)](https://github.com/richard-gledhill/microfiche/blob/main/LICENSE)

A personal library file manager built in python.

`microfiche` automatically organizes, categorizes, and files reference materials —
requirements, design notes, research, correspondence — into a structured library. It takes a folder of uncategorized
documents and sorts them with minimal manual effort. It works on any folder tree, including an Obsidian vault, and `sort` can be run from a scheduled task.

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
- **Never deletes files** — every move is recorded and reversible with `microfiche rollback`. A name collision or an
  exact duplicate is left in the inbox with the reason, never overwritten. A file another program has open, or one
  that is too big, stays put without stopping the run, and `sort --dry-run` previews a run first.
- **Vault-friendly** — works on any folder tree, including an Obsidian vault: microfiche's own state lives in a hidden
  `.microfiche/` folder and nothing is written next to your documents. Obsidian-specific features (folder notes,
  tag governance) are planned as an optional integration after the MVP; see the
  [feature backlog](https://github.com/richard-gledhill/microfiche/blob/main/docs/development/rfcs/feature-backlog.md).
- **Fully offline-capable** — no cloud service is required; AI classification is opt-in.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for dependency management
- Optional, only if you enable AI-assisted classification: a running [Ollama](https://ollama.com)
  server, or an OpenAI API key

## Installation

microfiche isn't published to PyPI. Each [GitHub release](https://github.com/richard-gledhill/microfiche/releases)
has two wheels, `core` and `cli`, released as a pair. Download both and install them together by path (don't
`pip install cli` by name: `core` and `cli` are common package names):

```bash
uv tool install ./cli-*.whl --with ./core-*.whl
microfiche --version
```

PowerShell, `pip`, upgrading and the AI extra are in the
[install guide](https://richard-gledhill.github.io/microfiche/how-to-use/#1-install). To work on the code instead,
install from source:

```bash
git clone https://github.com/richard-gledhill/microfiche.git
cd microfiche
uv sync
```

This installs the `microfiche` CLI into the project's virtual environment, runnable via
`uv run microfiche`.

## How a library is organised

A library is a folder with two levels of subfolders — **library › group › category** — plus a
`_sorting/` inbox where new documents are dropped. (Prefer no categories? Set `depth = 1` for a flat library of
groups only; see [Flat libraries](https://richard-gledhill.github.io/microfiche/how-to-use/#a-flat-library-groups-only).)

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

Put the keywords in `.microfiche/microfiche-library.json`. Each `name` is a folder name exactly as written, and
`"*"` means every group, so the same stages can be described once:

```json
{
  "groups": [
    {
      "name": "*",
      "children": [
        { "name": "01 Discovery", "hints": ["interview", "problem statement", "user research"] },
        { "name": "02 Design", "hints": ["wireframe", "mockup", "design decision"] },
        { "name": "03 Build", "hints": ["implementation", "pull request", "release notes"] },
        { "name": "04 Launch", "hints": ["go-live", "rollout", "launch plan"] }
      ]
    }
  ]
}
```

Things to keep in mind when choosing names:

- **Groups are matched by name only** (in a library with categories there are no keyword hints for groups; a flat
  library's groups do have them), so pick names that
  actually appear in your documents — project, client or course names usually do. A document that
  doesn't mention any group goes to **Needs review** and stays in the inbox.
- **Categories can use hints**, so they don't need to appear literally in the text.
- **One or two levels** are supported (`depth = 1` is a flat library of groups only); deeper folder trees aren't.

See [How to use microfiche](https://richard-gledhill.github.io/microfiche/how-to-use/) for a
walk-through.

## Usage

Point microfiche at a library — a folder with a `_sorting/` inbox and `group/category`
subfolders (see [How a library is organised](#how-a-library-is-organised)). Set it up once with `init`, then sort
whatever's been dropped into it:

```bash
uv run microfiche init --library ~/Documents/Library   # write the default config, create the inbox, list the folders
uv run microfiche sort --library ~/Documents/Library
```

```text
Filed: 12
Needs review: 3
Duplicates (left in the inbox): 1
  architecture_notes.docx -> Project Phoenix/02 Architecture (confidence 0.91, via rules_engine)
  ...
Job: 20261004-153012-a1b2c3
Undo with: microfiche rollback --library <your library> --job-id 20261004-153012-a1b2c3
```

Other commands:

```bash
uv run microfiche sort --library ~/Documents/Library --dry-run   # preview a sort: nothing is moved or recorded
uv run microfiche sort --library ~/Documents/Library -v   # also show progress messages (-q: errors only)
uv run microfiche review --library ~/Documents/Library   # decide, one by one, what `sort` left in the inbox
uv run microfiche reclassify --library ~/Documents/Library   # re-review already-filed documents (dry run)
uv run microfiche reclassify --library ~/Documents/Library --apply   # ...and re-file the ones marked "move"
uv run microfiche reclassify --library ~/Documents/Library --use-ai   # ...with the AI's help, as `sort --use-ai`
uv run microfiche propose-categories --library ~/Documents/Library
uv run microfiche init --library ~/Documents/Library   # again: check the config, change settings one by one
uv run microfiche config --library ~/Documents/Library   # show the loaded configuration
uv run microfiche config --library ~/Documents/Library --sync   # list new folders in microfiche-library.json
uv run microfiche audit --library ~/Documents/Library
uv run microfiche rollback --library ~/Documents/Library --job-id <id>
uv run microfiche rollback --library ~/Documents/Library --last   # undo the newest job not yet undone
uv run microfiche --version
```

`sort`, `reclassify` and `propose-categories` stop on a library with no config and ask you to run `init`.

By default only warnings and errors are shown, on stderr; `-v` adds progress messages and `-q` shows errors only. A
command that changes the library also records what it did, and why, in `.microfiche/microfiche.log`; see
[Troubleshooting](https://richard-gledhill.github.io/microfiche/how-to-use/#5-troubleshooting).

Every command and option is listed in the [CLI reference](https://richard-gledhill.github.io/microfiche/cli-reference/).

Run `uv run microfiche --help` for the full command reference. A command exits `0` when it did what was asked, `1` when it
could not, and `2` for a wrong command line; see [Exit codes](https://richard-gledhill.github.io/microfiche/how-to-use/#exit-codes).

## Configuration

Each library reads its own `.microfiche/microfiche-config.toml` file (the folder is dot-prefixed so it stays out of
Obsidian's or similar file explorer). `microfiche init` writes it with the defaults; run again, it lets you change
the settings one by one, keeping the file's comments and a backup.
[`microfiche/`](https://github.com/richard-gledhill/microfiche/tree/main/microfiche) holds an example config and library
file to copy from:

| Section | Purpose |
|---|---|
| `library_structure` | The group/category hierarchy (`depth` 2, the default, or 1 for a flat library of groups only) and `library_inbox`, the name of the inbox folder (default `"_sorting"`). |
| `classification` | `confidence_threshold` (0–1, default 0.75, [measured](https://github.com/richard-gledhill/microfiche/blob/main/docs/development/testing/calibration.md)): how sure microfiche must be to file a document without review. Keyword hints score 0.75 and AI answers 0.70, so the default files hints but not AI answers; raise it to hold hints for review, lower it to 0.7 to file AI answers. Also how sure each kind of match is — `name_match_confidence` (0.9), `filename_match_confidence` (0.95), `hint_match_confidence` (0.75) — `fuzzy_group_threshold` (0–100, default 85), how close a near-miss must be to a group's name — `ambiguity_margin` (0–1, default 0.1), how close the runner-up group or category may be before the document is held for review instead of guessed — and `normalise_names` (default on), which compares folder names, hints and text in one spelling so `meeting-notes` and `R&D` match "Meeting Notes" and "R and D". |
| `ai` | Which AI `sort --use-ai` asks: `provider` (`"ollama"`, the default and local, or `"openai"`, which sends document text to OpenAI), `model` (required with `--use-ai`; there is no default, and one test question is asked before any document is read), `host` (Ollama), `timeout`, and `api_key_env` (the *name* of the variable holding the OpenAI key; never the key). `verify_below` (0–1, default 0 = off): with `--use-ai`, have the AI check rules answers scoring below this (0.8 checks keyword hints) and leave the document for review if it disagrees. `ai_confidence` (0–1, default 0.70): how sure any answer is. `max_document_chars` (default 4000; `0` sends the whole document, with a warning): how much text is sent. |
| `sorting` | `keep_folders` (default `true`): file a folder dropped in the inbox whole, under its dominant category. `file_in_empty_groups` (default `false`): at depth 2, file a document that names a group with no category folders straight into that group instead of leaving it for review. `sort --keep-folders-off` files the documents inside folders one by one for one run, then removes each folder once it is empty; `--keep-folders` does the opposite. `ignore` (default `~$*`, `.DS_Store`, `Thumbs.db`, `*.tmp`): file and folder names the inbox scan skips without comment. |
| `learning` | `enabled` (default `false`): after a `review` commit, add keyword hints to `learned_hints` in `microfiche-library.json`, learned from the documents you filed by hand. `min_decisions` (3), `max_hints_per_run` (3) and `min_word_length` (4) keep it cautious. Your own hints are never changed; delete a learned hint to remove it. |
| `parsing` | `max_file_mb` (default 50): a file bigger than this is not read; it stays in the inbox for review, with the reason. |
| `logging` | The diagnostic log, separate from the audit log. `level` (default `INFO`): how much the log file records. `file` (default `microfiche.log`): its name, kept in `.microfiche/`. `max_bytes` (default 1048576) and `backup_count` (default 3): when the file is rotated and how many backups are kept. |
| `exclusions` | Folders never treated as a group or category and never scanned into: names or globs, matched at any level. The default (what `init` writes) lists `sorting*`, `_sorting*`, `.*`, `_*` and `attachments`; a list you write replaces it. |
| `naming_rules` | Regex rename rules applied to filenames before filing, as `rules = { 'pattern' = "replacement" }` (empty by default); see [Renaming on the way in](https://richard-gledhill.github.io/microfiche/how-to-use/#renaming-on-the-way-in). |

Keyword hints and filename rules are not in the config. They live in `.microfiche/microfiche-library.json`, a tree of
folder names with `hints` and `rules`; a `"*"` entry applies to every group, and a named group adds to it for that
group only. The library's folders decide what exists; the file only helps match them, and a missing file means
documents are matched on folder names alone.

A section or setting that isn't listed here is an error rather than being ignored, so a typo such as
`[classifcation]` is caught instead of silently leaving the defaults in place.

See [docs/development/architecture/overview.md](https://github.com/richard-gledhill/microfiche/blob/main/docs/development/architecture/overview.md)
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
│   ├── core/src/microfiche/core/    # scanning, classification, filing, library logic
│   └── cli/src/microfiche/cli/      # the microfiche Typer CLI
├── microfiche/     # example per-library config and library file (init writes the packaged defaults)
├── scripts/               # release-wheel checks, the module diagram, the sample library builder
├── tests/
│   ├── core/, cli/        # unit tests, mirrors the packages/ layout
│   ├── scripts/           # tests of the scripts, including the sample library every sort route is checked on
│   ├── calibration/       # a labelled corpus that measures the confidence threshold
│   ├── mock_library/      # a hand-built library fixture for integration-style tests
│   └── mock_flat_library/ # the same for a flat (depth 1) library
└── docs/                  # the published guide (mkdocs source) and, in development/, the design docs
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
