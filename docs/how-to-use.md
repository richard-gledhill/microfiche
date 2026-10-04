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

A library is a folder with two levels of subfolders — **library › group › category** — plus a
`_sorting/` inbox. microfiche reads the existing folders as its taxonomy, so create the groups and
categories you want first. Here a project is the group and a document type is the category (see
[Other ways to organise a library](#other-ways-to-organise-a-library) for alternatives such as
project › stage):

```text
Library/                      <- library root
├── .microfiche/              <- config (copied from the repo's microfiche/ folder)
├── _sorting/                 <- drop new documents here
└── Project Phoenix/          <- group (here, a project)
    ├── 01 Requirements/      <- category (here, a document type)
    ├── 02 Architecture/
    └── 03 Research/
```

Create the inbox:

=== "Bash"

    ```bash
    mkdir -p ~/Documents/Library/_sorting
    ```

=== "PowerShell"

    ```powershell
    New-Item -ItemType Directory -Force "$HOME\Documents\Library\_sorting"
    ```

Copy the default config into the library as `.microfiche/` (run from the repo root):

=== "Bash"

    ```bash
    cp -r microfiche ~/Documents/Library/.microfiche
    ```

=== "PowerShell"

    ```powershell
    Copy-Item -Recurse microfiche "$HOME\Documents\Library\.microfiche"
    ```

Then edit `.microfiche/microfiche-config.toml` in the library to add keyword hints and filename
rules for your categories. See the [configuration table](https://github.com/richard-gledhill/microfiche#configuration)
for what each section does.

Confirm the config loads:

=== "Bash"

    ```bash
    uv run microfiche config --library ~/Documents/Library
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche config --library "$HOME\Documents\Library"
    ```

### Other ways to organise a library

The tree above uses a project as the **group** and a document type as the **category**, but those are
only roles — you choose what they mean. Whatever you pick, the same rules apply: microfiche finds
the group by its name in the document's text, then the category by its name or by keyword hints.

**Project › stage.** A common alternative is to file each project's documents by the stage of work
rather than by document type. The project is still the group; the stage is the category:

```text
Library/
├── .microfiche/
├── _sorting/
├── Project Phoenix/          <- group: a project
│   ├── 01 Discovery/         <- category: a stage
│   ├── 02 Design/
│   ├── 03 Build/
│   └── 04 Launch/
└── Project Atlas/
    ├── 01 Discovery/
    └── ...
```

Stage names rarely appear word for word in a document, so give each one keyword hints in
`.microfiche/microfiche-config.toml`. The keys must match the category folder names exactly,
including any leading number:

```toml
[category_hints.categories]
"01 Discovery" = ["interview", "problem statement", "user research"]
"02 Design" = ["wireframe", "mockup", "design decision"]
"03 Build" = ["implementation", "pull request", "release notes"]
"04 Launch" = ["go-live", "rollout", "launch plan"]
```

If some documents are recognisable from their filename, add a filing rule too. Rules are checked
before keyword hints, and `category` must exist in the group the document is filed under:

```toml
[filing_rules]
rules = [
  { pattern = "launch-plan*", category = "04 Launch" },
]
```

**Other taxonomies.** The same shape works for other kinds of library:

| Use case | Group | Category | Example path |
|---|---|---|---|
| Client work | client | document type | `Acme Ltd/Contracts/` |
| Study | course or subject | topic or week | `Machine Learning/Week 04/` |
| Household admin | area | topic | `Home/Insurance/` |

**Choosing names that work:**

- Groups are matched by name only — there are no keyword hints for groups — so use names that
  appear in your documents (project, client or course names usually do). A document that doesn't
  mention any group is listed under **Needs review** and left in the inbox.
- Categories can use hints, so they don't need to appear literally.
- A leading number such as `01 ` is ignored when matching names, so you can use it to order
  folders.
- Exactly two levels (group, category) are supported today. Folders deeper than that aren't
  part of the taxonomy.

## 3. Sort documents

Drop files (`.docx`, `.pdf`, `.md`, `.txt`, `.eml`, `.msg`) into `_sorting/`, then run:

=== "Bash"

    ```bash
    uv run microfiche sort --library ~/Documents/Library
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche sort --library "$HOME\Documents\Library"
    ```

Anything classified with enough confidence is filed; the rest is listed under **Needs review**
and left in the inbox. Each run that files something is recorded as one *job*, and `sort` prints
its id (`Job: <id>`) — keep it if you might want to undo the run. Nothing is deleted.

microfiche's own records live in the hidden `.microfiche/` folder inside your library: a ledger
of what was filed where and why (`ledger.jsonl`), a readable `audit.log`, and one rollback file
per job. No extra files are written next to your documents.

Keep dropped folders together (filed by their dominant category):

=== "Bash"

    ```bash
    uv run microfiche sort --library ~/Documents/Library --keep-folders
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche sort --library "$HOME\Documents\Library" --keep-folders
    ```

Use the Ollama fallback for low-confidence documents (requires the `ai` extra and a running
Ollama server):

=== "Bash"

    ```bash
    uv run microfiche sort --library ~/Documents/Library --use-ai
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche sort --library "$HOME\Documents\Library" --use-ai
    ```

## 4. Maintain the library

Suggest new category names based on what's in the inbox (prints suggestions only — never creates
folders):

=== "Bash"

    ```bash
    uv run microfiche propose-categories --library ~/Documents/Library
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche propose-categories --library "$HOME\Documents\Library"
    ```

Re-check already-filed documents against the current rules. This is a dry run: it prints a table
with an **Action** for each document and changes nothing:

=== "Bash"

    ```bash
    uv run microfiche reclassify --library ~/Documents/Library
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche reclassify --library "$HOME\Documents\Library"
    ```

The actions are **move** (confident, and not already under the proposed category), **keep**
(already in the right place), **review** (not confident enough — never moved automatically) and
**conflict** (a file with that name is already at the destination, or another document in the
same run is headed there — left alone, never overwritten).

Limit the re-check to one folder (it must be inside the library):

=== "Bash"

    ```bash
    uv run microfiche reclassify --library ~/Documents/Library --folder ~/Documents/Library/"Project Phoenix"
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche reclassify --library "$HOME\Documents\Library" --folder "$HOME\Documents\Library\Project Phoenix"
    ```

Happy with the preview? Add `--apply` to move the **move** documents. Like `sort`, this is one
job: it prints a job id, is recorded in the ledger and audit log, and can be undone with
`rollback`:

=== "Bash"

    ```bash
    uv run microfiche reclassify --library ~/Documents/Library --apply
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche reclassify --library "$HOME\Documents\Library" --apply
    ```

`--folder` works with `--apply` too. Preview first: classification is rule-based, so it is worth
checking the table before moving anything.

View the audit log:

=== "Bash"

    ```bash
    uv run microfiche audit --library ~/Documents/Library
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche audit --library "$HOME\Documents\Library"
    ```

Undo a filing job (use the id `sort` printed; each job can be undone once, and if an undo stops
part-way — for example because a new file now sits where the original was — fix that and run the
same command again):

=== "Bash"

    ```bash
    uv run microfiche rollback --library ~/Documents/Library --job-id <id>
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche rollback --library "$HOME\Documents\Library" --job-id <id>
    ```

## Current limitations

microfiche is pre-release. At the moment:

- `reclassify` doesn't use the Ollama fallback; it only applies the rule-based classifier.
- If you re-file a document with `reclassify --apply` after a `sort`, undo the newer job first —
  rolling back the older one will stop with an error because the file is no longer where it
  was filed.
- `review` and `index` are placeholders and exit with a "not implemented" message.

Run `uv run microfiche <command> --help` for every option on a command.
