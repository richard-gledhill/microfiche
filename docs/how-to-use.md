# How to use microfiche

A quick guide to installing microfiche, setting up a library, and sorting documents into it.
Commands that differ between shells are shown in **Bash** and **PowerShell** tabs; the rest work
as-is in either.

## 1. Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). microfiche isn't on PyPI yet, so
install it from source:

```bash
git clone https://github.com/richard-gledhill/microfiche.git
```

```bash
cd microfiche
```

```bash
uv sync
```

Check it works:

```bash
uv run microfiche --help
```

**Optional — AI fallback.** To let a local [Ollama](https://ollama.com) model classify documents
the rules can't, install the `ai` extra:

```bash
uv sync --package core --extra ai
```

## 2. Set up a library

A library is a folder of `group/category` subfolders plus a `_sorting/` inbox. microfiche reads
the existing folders as its taxonomy, so create the categories you want first:

```text
Projects/                     <- library root
├── .microfiche/              <- config (copied from the repo's microfiche/ folder)
├── _sorting/                 <- drop new documents here
└── Project Phoenix/          <- group
    ├── 01 Requirements/      <- category
    ├── 02 Architecture/
    └── 03 Research/
```

Create the inbox:

=== "Bash"

    ```bash
    mkdir -p ~/Documents/Projects/_sorting
    ```

=== "PowerShell"

    ```powershell
    New-Item -ItemType Directory -Force "$HOME\Documents\Projects\_sorting"
    ```

Copy the default config into the library as `.microfiche/` (run from the repo root):

=== "Bash"

    ```bash
    cp -r microfiche ~/Documents/Projects/.microfiche
    ```

=== "PowerShell"

    ```powershell
    Copy-Item -Recurse microfiche "$HOME\Documents\Projects\.microfiche"
    ```

Then edit `.microfiche/microfiche-config.toml` in the library to add keyword hints and filename
rules for your categories. See the [configuration table](https://github.com/richard-gledhill/microfiche#configuration)
for what each section does.

Confirm the config loads:

=== "Bash"

    ```bash
    uv run microfiche config --library ~/Documents/Projects
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche config --library "$HOME\Documents\Projects"
    ```

## 3. Sort documents

Drop files (`.docx`, `.pdf`, `.md`, `.txt`, `.eml`, `.msg`) into `_sorting/`, then run:

=== "Bash"

    ```bash
    uv run microfiche sort --library ~/Documents/Projects
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche sort --library "$HOME\Documents\Projects"
    ```

Anything classified with enough confidence is filed; the rest is listed under **Needs review**
and left in the inbox.

Keep dropped folders together (filed by their dominant category):

=== "Bash"

    ```bash
    uv run microfiche sort --library ~/Documents/Projects --keep-folders
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche sort --library "$HOME\Documents\Projects" --keep-folders
    ```

Use the Ollama fallback for low-confidence documents (requires the `ai` extra and a running
Ollama server):

=== "Bash"

    ```bash
    uv run microfiche sort --library ~/Documents/Projects --use-ai
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche sort --library "$HOME\Documents\Projects" --use-ai
    ```

## 4. Maintain the library

Suggest new category names based on what's in the inbox (prints suggestions only — never creates
folders):

=== "Bash"

    ```bash
    uv run microfiche propose-categories --library ~/Documents/Projects
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche propose-categories --library "$HOME\Documents\Projects"
    ```

Re-check already-filed documents against the current rules (dry run):

=== "Bash"

    ```bash
    uv run microfiche resort --library ~/Documents/Projects
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche resort --library "$HOME\Documents\Projects"
    ```

Limit the re-check to one folder:

=== "Bash"

    ```bash
    uv run microfiche resort --library ~/Documents/Projects --folder ~/Documents/Projects/"Project Phoenix"
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche resort --library "$HOME\Documents\Projects" --folder "$HOME\Documents\Projects\Project Phoenix"
    ```

View the audit log:

=== "Bash"

    ```bash
    uv run microfiche audit --library ~/Documents/Projects
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche audit --library "$HOME\Documents\Projects"
    ```

Undo a filing job:

=== "Bash"

    ```bash
    uv run microfiche rollback --library ~/Documents/Projects --job-id <id>
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche rollback --library "$HOME\Documents\Projects" --job-id <id>
    ```

## Current limitations

microfiche is pre-release. At the moment:

- `sort` doesn't yet save an audit trail or rollback job, so `audit` and `rollback` have nothing
  to work with after a sort.
- `resort --apply` only reports proposals; it doesn't move files yet.
- `review` and `index` are placeholders and exit with a "not implemented" message.

Run `uv run microfiche <command> --help` for every option on a command.
