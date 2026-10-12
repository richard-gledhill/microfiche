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

The inbox is called `_sorting` by default. To use another name — for example `Incoming`, or `sorting`
if you already have a folder by that name — set `library_inbox` under `[library_structure]` in the config:

```toml
[library_structure]
library_inbox = "Incoming"
```

The inbox and the hidden `.microfiche/` folder are never treated as groups, whatever else you exclude.

Then edit `.microfiche/microfiche-library.json` in the library to add keyword hints and filename
rules for your categories (see below), and `.microfiche/microfiche-config.toml` for settings. See the
[configuration table](https://github.com/richard-gledhill/microfiche#configuration) for what each
config section does.

Confirm the config loads:

=== "Bash"

    ```bash
    uv run microfiche config --library ~/Documents/Library
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche config --library "$HOME\Documents\Library"
    ```

If the config has a mistake, such as a mistyped section or setting, or a value of the wrong type, the
command stops and tells you what to fix instead of carrying on with the defaults:

```text
Config file error: Library\.microfiche\microfiche-config.toml:
  classification.confidence_threshhold: unknown setting
```

`sort`, `reclassify` and `propose-categories` check the config the same way before they touch any file.
`audit` and `rollback` don't read it, so you can still undo a job while you fix the config.

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
`.microfiche/microfiche-library.json`. Each `name` must match the category folder name exactly,
including any leading number (the case is ignored). The `"*"` entry means every group, so you describe
the stages once:

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

If some documents are recognisable from their filename, add a filing rule to the category. A rule is a
pattern matched against the file name only (never the folder), ignoring case, and rules are checked
before keyword hints. `launch-plan*` matches `Launch-Plan.docx` and `launch-plan v2.pdf`:

```json
{ "name": "04 Launch", "hints": ["go-live", "rollout"], "rules": [{ "pattern": "launch-plan*" }] }
```

To give one group its own hints on top of the shared ones, add an entry for that group. Hints are
never inherited by the folders below, and an entry only helps match a folder that exists: the
library's folders decide what exists.

```json
{ "name": "Project Phoenix", "children": [{ "name": "02 Design", "hints": ["storyboard"] }] }
```

A library with no `microfiche-library.json` still works: documents are matched on group and
category names alone. A mistake in the file (a misspelt key, say) stops `sort` and `reclassify`
with a message saying where in the file the mistake is, and nothing is moved.

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

### How sure microfiche has to be

microfiche only files a document on its own when it is confident enough; anything less stays in
`_sorting/` under **Needs review**. How sure it is depends on how it matched:

| Match | Confidence |
|---|---|
| Group name found in the document | 1.0 |
| A filename rule | 0.95 |
| Category name found in the document | 0.90 |
| Group name nearly matches (fuzzy) | 0.85 and up |
| A category keyword hint | 0.75 |
| An answer from the AI fallback | 0.70 |

A document is only as confident as the weaker of its group and category. The threshold is set per
library in `.microfiche/microfiche-config.toml`, from 0 to 1, and defaults to **0.75**: filename rules,
category names and keyword hints all file automatically; answers from the AI fallback (0.70) are left
for you to review.

```toml
[classification]
confidence_threshold = 0.75
```

| Threshold | What files automatically |
|---|---|
| `0.7` | everything above, plus AI answers (see [`--use-ai`](#3-sort-documents)) |
| `0.75` (default) | group and category names, filename rules, keyword hints |
| `0.8` – `0.9` | the same, but keyword-hint matches are held for review |
| `0.95` | filename rules only |

The scores in the first table are settings too, and these are their defaults. You rarely need to
change them: moving the threshold gives the same effect, and the defaults were
[measured](https://github.com/richard-gledhill/microfiche/blob/main/docs/development/calibration.md).
Change one if a kind of evidence is more or less trustworthy in your library, for example if you
want keyword hints to count for less:

```toml
[classification]
name_match_confidence = 0.9       # a category's name found in the text
filename_match_confidence = 0.95  # a filename rule
hint_match_confidence = 0.75      # a keyword hint
fuzzy_group_threshold = 85        # how close (0-100) a near-miss must be to a group's name

[ai]
ai_confidence = 0.70              # any answer from the AI fallback
max_document_chars = 4000         # how much of a document's text is sent to the AI
```

Each score is from 0 to 1 and `fuzzy_group_threshold` from 0 to 100; `max_document_chars` must be at
least 1. Setting a score at or above the threshold lets that kind of evidence file on its own.

**Raising the threshold files less; it doesn't file more accurately.** The score says what *kind* of
evidence was found, not how reliable it is, so a stray word in the text can score higher than a
correct hint. In testing, the share of automatically filed documents that were wrong was about the
same at `0.75` as at `0.8` — the higher setting just held back far more documents. Measurements and
method: [calibration write-up](https://github.com/richard-gledhill/microfiche/blob/main/docs/development/calibration.md).

If documents are being misfiled, the usual causes are in the names, not the threshold:

- **Group names that are short or common words** (`Car`, `Home`) match inside other words
  (`carrier`, `homework`). Prefer distinctive names, like `Project Phoenix` or `Acme Ltd`.
- **Documents that mention another group** can be filed under it: of the groups named in the text, the
  one whose folder name sorts first wins, not the one the document is about. These are filed
  confidently, so they won't appear under **Needs review**; a `reclassify` dry run shows them as **move**.
- **Overlapping hints** — a word that is a hint for two categories goes to the category whose folder
  name sorts first. Keep hints specific.

**Check it on your own library.** Run `reclassify` (a dry run) on a library whose documents are
already filed correctly. **keep** means microfiche agrees with where you put a document; **move** means
it would have misfiled it. Change `confidence_threshold` and run it again to see how the numbers
change for *your* documents. The calibration write-up also describes a script that does this in
bulk.

## 3. Sort documents

Drop files (`.docx`, `.pdf`, `.md`, `.txt`, `.eml`, `.msg`) into the inbox (`_sorting/` unless you named another), then run:

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
its id (`Job: <id>`) — keep it if you might want to undo the run. No file is ever deleted.

A file microfiche can't open (corrupt or truncated, say) doesn't stop the run: it is listed under
**Needs review** as `Could not read '<file>': <reason>`, left in the inbox, and everything else is sorted
as normal. Fix or replace the file and sort again.

microfiche's own records live in the hidden `.microfiche/` folder inside your library: a ledger
of what was filed where and why (`ledger.jsonl`), a readable `audit.log`, one rollback file
per job, and a diagnostic log (`microfiche.log`, see [The log file](#the-log-file)). While a run is in
progress there is also a `lock` file there (see [Two runs at once](#two-runs-at-once)). No extra files
are written next to your documents.

A folder dropped in the inbox is kept together and filed whole, under the category most of its
documents belong to. That is the default (`[sorting] keep_folders = true` in your config). To file the
documents inside folders one by one instead, for one run, add `--keep-folders-off`:

=== "Bash"

    ```bash
    uv run microfiche sort --library ~/Documents/Library --keep-folders-off
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche sort --library "$HOME\Documents\Library" --keep-folders-off
    ```

`--keep-folders` does the opposite for one run, for a library whose config turns folders off. Passing
both is an error. To change it for good, set `keep_folders = false` under `[sorting]` in the library's
`.microfiche/microfiche-config.toml`. A flag beats that file, and the file beats microfiche's built-in
default (`true`), which is what a library with no `[sorting]` section gets.

With folders off, every supported document in an inbox folder, including those in sub-folders, is
classified and filed on its own, so one folder can end up in several categories. When all of a folder's
documents have been filed and nothing at all is left in it, the empty folder is removed (and its empty
sub-folders). This is the only thing microfiche ever removes, and `rollback` puts it back. If anything
is left in the folder — a file that isn't a document, a document that needs review, a duplicate — the
folder stays, and the `sort` summary says which file kept it there.

### Preview before you sort

To see what a run would do without doing it, add `--dry-run`:

=== "Bash"

    ```bash
    uv run microfiche sort --library ~/Documents/Library --dry-run
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche sort --library "$HOME\Documents\Library" --dry-run
    ```

The output is labelled **Preview**. It lists what would be filed and where, what would need review, which
files are duplicates, and (with `--keep-folders-off`) which emptied inbox folders would be removed. Nothing is
moved, and nothing is recorded: no job, no ledger or audit line, and no lock. A real run then does the same
thing, which is the point of a preview.

Two things a preview cannot know. It still classifies, so with `--use-ai` it asks the AI, and with OpenAI that
sends document text and costs money. And it cannot see that a file will be open in another program when you
do the real run (see below).

### Name clashes and duplicates

`sort` never overwrites, renames or deletes a file. Two situations leave a file where it is:

- **A name clash.** The file would be filed under a name that is already taken, either by a different file
  already in that category folder or by another document in the same run (the first one is filed, the
  next is held). It is listed under **Needs review** with the reason, for example
  `... but 'notes.md' already exists in Project Phoenix/02 Architecture`. Rename it, or the file that is
  already there, and sort again.
- **A duplicate.** The file is an exact copy (same content, whatever the name) of a file already
  anywhere in the library, or of another file in the inbox that is being filed in the same run. It is still
  classified, then listed under **Duplicates (left in the inbox)** with where the copy is. When the copy is in
  a different place from where microfiche would file this one, the line says both, for example
  `identical to Project Phoenix/03 Research/spec.md; this would be filed in Project Phoenix/02 Architecture`.
  That is worth a look: either the filed copy is in the wrong place or the classifier is. Delete the duplicate
  from the inbox yourself, or move it by hand if you did mean to keep a second copy.

Only the new files in the inbox are checked, against the library. Copies already inside the library, such as a
reference document kept in two projects, are normal and are never reported. An empty file is never counted as a
duplicate, and a folder kept whole is not checked as a duplicate (turn `keep_folders` off to check its files one
by one).

### The AI fallback

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

`--use-ai` asks the AI named in the `[ai]` section of the library's config. The default is a local
Ollama model; nothing leaves your machine. These are the settings, with their defaults:

```toml
[ai]
provider = "ollama"               # "ollama" or "openai"
model = ""                        # empty = the provider's own default model
host = ""                         # Ollama only; empty = Ollama's default address
timeout = 120                     # seconds to wait for one answer
api_key_env = "OPENAI_API_KEY"    # the NAME of the variable holding your OpenAI key
ai_confidence = 0.70              # how sure any AI answer is
max_document_chars = 4000         # how much of each document is sent; 0 = all of it
```

**Using OpenAI instead.** Set `provider = "openai"` and put your key in the environment variable named
by `api_key_env`, not in the file (microfiche refuses a value that looks like a key). This sends the
text of every document the AI is asked about to OpenAI, so `sort` says so each time it runs, even with `-q`,
and records that in the log. If the variable is not set, `sort` stops with a message naming it before anything
is moved.

=== "Bash"

    ```bash
    export OPENAI_API_KEY="your key"
    uv run microfiche sort --library ~/Documents/Library --use-ai
    ```

=== "PowerShell"

    ```powershell
    $env:OPENAI_API_KEY = "your key"
    uv run microfiche sort --library "$HOME\Documents\Library" --use-ai
    ```

**Sending whole documents.** `max_document_chars = 0` removes the limit. That uses more tokens
(and with OpenAI, costs more) and takes longer, and a document longer than the model's context window
may fail or be cut off, so `sort` prints a warning once before it starts (even with `-q`) and records it in the log.

**If the AI cannot be reached.** Ollama not running, a timeout, or the `ai` extra not installed does not stop
the run. The first failure switches the AI off for the rest of that run (so a dead server is waited on once, not
once per document), and `sort` shows one warning on screen: `AI fallback unavailable (<reason>): the rest of the
run uses the rules only, ...`. Everything the rules can decide is filed as usual. Anything only the AI could have
answered stays under **Needs review**. With `-q` the warning is not shown on screen, but it is still in the log
file (see [Troubleshooting](#5-troubleshooting)).

### Files that can't be sorted

One awkward file never stops a run. It stays where it is, and the summary says why:

- **Open in another program.** A document that Word (or another program) has open cannot be moved on
  Windows. It is listed under **Needs review** as `... but it could not be moved: it is open in another program;
  close it and sort again`. Moves are plain renames, so a failed move leaves nothing behind: no stray copy, and
  nothing recorded in the job, ledger or audit log. Close the file and sort again. With `--keep-folders-off`, a
  folder with a file that could not be moved stays in the inbox; a folder kept whole is not moved at all.
- **Too big.** A file over `[parsing] max_file_mb` (default 50) is not read. It is listed as
  `Could not read 'x.pdf': it is 120.0 MB, over the 50 MB limit ([parsing] max_file_mb)` and left in the inbox.
  Raise the setting to include it.
- **Names that are skipped.** Office lock files (`~$report.docx`) and OS clutter are skipped without comment: never
  read, filed or moved. These are the `[sorting] ignore` patterns, and a setting you write replaces the list:

  ```toml
  [sorting]
  ignore = ["~$*", ".DS_Store", "Thumbs.db", "*.tmp"]   # the defaults
  [parsing]
  max_file_mb = 50                                       # the default
  ```

  A skipped file still counts as something in its folder, so with `--keep-folders-off` a folder holding only a
  `Thumbs.db` stays (no file is ever deleted to empty it).
- **Links.** A symbolic link or a Windows junction in the inbox is never followed, read or filed, so a link can't
  lead `sort` out of the library. `sort` lists it as `Skipped <name>: links and junctions are never followed`.
  Files that OneDrive keeps online only are ordinary files and are sorted as usual.

### Two runs at once

`sort`, `reclassify --apply` and `rollback` change the library, so only one can run at a time. Each takes a lock
(a small `lock` file in `.microfiche/`, removed when the run ends), and a second one refuses to start:

```text
Another microfiche run is already in progress (sort, process 4242, started 2026-10-12 09:30:12). Wait for it to
finish and try again. If no run is active, delete <library>/.microfiche/lock and try again.
```

Wait for the first run, then try again. If a run was killed or the machine lost power, you need do nothing: the
lock records the process that took it, and a lock whose process is gone is cleared automatically. The run that clears
it warns you (`cleared a stale run lock left by a run that did not finish (sort, process 4242, started ...)`) and
records that in the log, which tells you an earlier run never finished. If the lock
file is damaged so that microfiche can't tell, it is treated as held, and the message names the file to delete.
A preview (`sort --dry-run`), `reclassify` without `--apply`, `audit`, `config` and `propose-categories` only read,
so they need no lock and run beside anything.

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

## 5. Troubleshooting

When a document didn't go where you expected, or a run did less than you thought, microfiche can tell you why.

### What microfiche shows while it runs

By default it shows only what needs your attention: warnings and errors. They are printed on screen (stderr), so the
summary `sort` prints (stdout) stays clean to pipe or redirect. Two options, on `sort`, `reclassify`, `rollback`,
`audit`, `config` and `propose-categories`, change how much you see:

| Option | What you see |
|---|---|
| none | Warnings and errors |
| `-v`, `--verbose` | Also progress messages, such as how many documents were found and how the run finished. The log file also records debugging detail. |
| `-q`, `--quiet` | Errors only. If you pass both, `-q` wins. |

=== "Bash"

    ```bash
    uv run microfiche sort --library ~/Documents/Library -v
    uv run microfiche sort --library ~/Documents/Library -q
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche sort --library "$HOME\Documents\Library" -v
    uv run microfiche sort --library "$HOME\Documents\Library" -q
    ```

`-q` never hides a notice about what leaves your machine: the OpenAI and unlimited-size notices
([The AI fallback](#the-ai-fallback)) are always printed.

**A progress bar.** On a terminal, a run of 20 or more documents, or any run with `--use-ai`, shows a bar on stderr
(`Classifying ━━━━━━╺━━━━━━ 12/48 0:00:07`) that disappears when the run ends. There is none with `-q`, and none
when output is piped or redirected, so a script sees no control codes. The 20-document threshold is fixed; there is
no setting for it.

### The log file

Every run that changes the library records what it did in `<library>/.microfiche/microfiche.log`. It is separate
from `audit.log`: the audit log is the permanent record of moves, and the log is for explaining a run.

- **Who writes it.** `sort`, `reclassify --apply` and `rollback`, the commands that take the lock. A preview
  (`sort --dry-run`, `reclassify` without `--apply`) and the read-only commands (`audit`, `config`,
  `propose-categories`) write nothing, and a preview never creates `.microfiche/`. A run that is refused because
  another is in progress leaves no trace either.
- **What is in it.** By default (level `INFO`), the number of documents found, each warning (a file that could
  not be moved, the AI being unreachable, a leftover lock being cleared) and a summary of how the run ended. With `-v` it also has one line for
  each document saying where it was classified and why. It never contains the text of your documents.
- **How big it gets.** It is rotated: when it reaches `max_bytes` it becomes `microfiche.log.1` and a new file
  starts, keeping `backup_count` old ones.

These are the settings, with their defaults (the `[logging]` table of `.microfiche/microfiche-config.toml`):

```toml
[logging]
level = "INFO"            # what the file records: DEBUG, INFO, WARNING, ERROR or CRITICAL (-v makes it DEBUG)
file = "microfiche.log"   # a file name inside .microfiche/: not a path, and not one of microfiche's own files
max_bytes = 1048576       # rotate when the file reaches this size
backup_count = 3          # how many old files to keep; 0 never rotates, so the file grows without limit
```

If the config can't be read, `rollback` still works (undoing a run must never be blocked), but it can't tell where
the log file should go, so it warns on screen and writes no file.

### Reading the log

=== "Bash"

    ```bash
    tail -n 50 ~/Documents/Library/.microfiche/microfiche.log
    grep WARNING ~/Documents/Library/.microfiche/microfiche.log
    ```

=== "PowerShell"

    ```powershell
    Get-Content "$HOME\Documents\Library\.microfiche\microfiche.log" -Tail 50
    Select-String WARNING "$HOME\Documents\Library\.microfiche\microfiche.log"
    ```

To find out why a document went to review, sort with `-v` and look for its name. Each line gives the group and
category microfiche chose with a confidence and the reason, and which method decided:

```text
2026-10-12 17:06:43,348 DEBUG core.classifier: research-summary.md: group Project Phoenix (1.00, Exact match on group name 'Project Phoenix'); category 03 Research (0.90, Category name '03 Research' found in document text); by rules_engine
2026-10-12 17:06:43,349 DEBUG core.classifier: SolarConstructionNotes.md: group None (0.00, No known group name found in document text); category None (0.00, Group unresolved); by rules_engine
2026-10-12 17:06:43,349 DEBUG core.organizer: SolarConstructionNotes.md: left for review (confidence 0.00)
2026-10-12 17:06:43,354 INFO core.organizer: sort finished: 2 filed, 1 for review, 0 duplicate(s)
```

## Current limitations

microfiche is pre-release. At the moment:

- `reclassify` doesn't use the AI fallback; it only applies the rule-based classifier.
- At the default confidence threshold, documents matched only by the AI fallback are left for
  review, so `--use-ai` only suggests until you lower the threshold to `0.7`. See
  [How sure microfiche has to be](#how-sure-microfiche-has-to-be).
- When the documents in a dropped folder disagree about where it belongs (a tie), the folder is
  left for review rather than guessed.
- If you re-file a document with `reclassify --apply` after a `sort`, undo the newer job first —
  rolling back the older one will stop with an error because the file is no longer where it
  was filed.
- Duplicates are found by exact content only: a copy saved again by another program, so that its bytes
  differ, is not recognised. A folder kept whole is not checked as a duplicate, and nothing moves a duplicate
  out of the inbox for you.
- A preview can't tell that a file will be open in another program when the real run happens, and it can be
  out of date if another run is changing the library at the same time.
- The inbox settings `[sorting] ignore` and the skipping of links apply to `sort`. `reclassify` honours
  `[parsing] max_file_mb` but not those two.
- A file open in another program is not retried: close it and run `sort` again.
- `review` is a placeholder and exits with a "not implemented" message. Until it is built, a document listed under
  **Needs review** stays in the inbox for you to file by hand.
- microfiche does not write Obsidian `index.md` folder notes or govern tags yet; that is planned as an optional
  integration after the first release.
- `-q` hides the "AI fallback unavailable" warning on screen. It is still in the log file.
- A file that can't be moved is reported twice on screen: as a warning when it happens (also in the log file), and
  again in the summary's **Needs review** list.
- The log file is written only by commands that change the library, and not by `rollback` when the config can't be
  read.
- `-q` also hides the warning that a leftover lock was cleared. It is still in the log file.
- The progress bar's threshold (20 documents, or any `--use-ai` run) is fixed; there is no setting for it.

Every command and option is listed in the [CLI reference](cli-reference.md), or run
`uv run microfiche <command> --help`.
