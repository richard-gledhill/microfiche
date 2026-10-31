# How to use microfiche

A quick guide to installing microfiche, setting up a library, and sorting documents into it.
Commands that differ between shells are shown in **Bash** and **PowerShell** tabs; the rest work
as-is in either.

## 1. Install

Requires Python 3.11+. The commands below use [uv](https://docs.astral.sh/uv/); a `pip` route is given too.
microfiche isn't on PyPI. Each [GitHub release](https://github.com/richard-gledhill/microfiche/releases) has two
files, `core-<version>-py3-none-any.whl` and `cli-<version>-py3-none-any.whl`, and you install them together. To change
the code, or to try something that isn't released, [install from source](#install-from-source) instead.

### Install a release

!!! warning "Install both files, by path"
    The two wheels are released as a pair: `cli` needs exactly the same version of `core`. Install them from the
    files you downloaded, as shown. Don't run `pip install cli` or `uv tool install cli` by name: `core` and `cli`
    are very common package names, and a package of that name from the package index is not microfiche.

**1. Download both wheels** into a new folder. From the release page in a browser, or with the
[GitHub CLI](https://cli.github.com/), which fetches the latest release:

=== "Bash"

    ```bash
    mkdir microfiche-release && cd microfiche-release
    ```

    ```bash
    gh release download --repo richard-gledhill/microfiche --pattern "*.whl"
    ```

=== "PowerShell"

    ```powershell
    New-Item -ItemType Directory microfiche-release; Set-Location microfiche-release
    ```

    ```powershell
    gh release download --repo richard-gledhill/microfiche --pattern "*.whl"
    ```

**2. Install them** as a command-line tool, in an environment of its own so nothing else on your machine is touched.
Keep the `./` (or `.\`) in front of each wheel name: without it uv reads `cli-*.whl` as a package name and stops with
*"The wheel filename … is invalid: Must have a Python tag"*.

=== "Bash"

    ```bash
    uv tool install ./cli-*.whl --with ./core-*.whl
    ```

=== "PowerShell"

    ```powershell
    uv tool install (Get-Item .\cli-*.whl).FullName --with (Get-Item .\core-*.whl).FullName
    ```

**3. Check it works:**

```bash
microfiche --version
```

```bash
microfiche --help
```

If the command isn't found, run `uv tool update-shell` and open a new terminal: uv puts tools in a folder that may not be on
your `PATH` yet.

**Using pip instead.** Make an environment and give pip both files:

=== "Bash"

    ```bash
    python -m venv .venv && source .venv/bin/activate   # Git Bash on Windows: source .venv/Scripts/activate
    ```

    ```bash
    pip install ./core-*.whl ./cli-*.whl
    ```

=== "PowerShell"

    ```powershell
    python -m venv .venv; .\.venv\Scripts\Activate.ps1
    ```

    ```powershell
    pip install (Get-Item .\core-*.whl).FullName (Get-Item .\cli-*.whl).FullName
    ```

**Upgrade.** Download the new release's two wheels into a new folder and run the install command again with
`--reinstall` (`uv tool install --reinstall ...`; with pip, `pip install --force-reinstall ...`). Your libraries are
untouched: their settings and records live inside each library, in `.microfiche/`.

**Uninstall.** `uv tool uninstall cli` (the tool is named after its package; the command it provides is `microfiche`), or
`pip uninstall cli core`. Libraries are left as they are.

!!! note "Commands in the rest of this guide"
    The examples that follow start with `uv run microfiche`, which is how you run it from a source checkout. With a
    release install, leave out `uv run` and type `microfiche ...`.

### Install from source

To change the code, or to run something that isn't in a release:

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

```bash
uv run microfiche --version
```

### Optional: the AI fallback

To let a local [Ollama](https://ollama.com) model classify documents the rules can't, install the `ai` extra, which
is the `ollama` and `openai` packages. From a release, add them to the tool when you install it:

=== "Bash"

    ```bash
    uv tool install ./cli-*.whl --with ./core-*.whl --with ollama --with openai
    ```

=== "PowerShell"

    ```powershell
    uv tool install (Get-Item .\cli-*.whl).FullName --with (Get-Item .\core-*.whl).FullName --with ollama --with openai
    ```

From a source checkout:

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
├── .microfiche/              <- config, written by `microfiche init`
├── _sorting/                 <- drop new documents here (`init` creates it)
└── Project Phoenix/          <- group (here, a project)
    ├── 01 Requirements/      <- category (here, a document type)
    ├── 02 Architecture/
    └── 03 Research/
```

Create, to have something to sort into, one group with three categories:

=== "Bash"

    ```bash
    mkdir -p "$HOME/Documents/Library/Project Phoenix/01 Requirements" "$HOME/Documents/Library/Project Phoenix/02 Architecture" "$HOME/Documents/Library/Project Phoenix/03 Research"
    ```

=== "PowerShell"

    ```powershell
    "01 Requirements", "02 Architecture", "03 Research" | ForEach-Object { New-Item -ItemType Directory -Force "$HOME\Documents\Library\Project Phoenix\$_" }
    ```

Then set the library up with `init`:

=== "Bash"

    ```bash
    uv run microfiche init --library ~/Documents/Library
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche init --library "$HOME\Documents\Library"
    ```

On a library with no `.microfiche/microfiche-config.toml`, `init` asks nothing. It writes the default config there, with
a one-line comment on every setting; creates the `_sorting/` inbox if it is missing; and writes
`.microfiche/microfiche-library.json` listing your group and category folders (see
[Keeping the file in step with your folders](#keeping-the-file-in-step-with-your-folders)). It never creates, moves or
deletes your own folders or documents.

`sort`, `reclassify` and `propose-categories` need this config: on a library without one they stop, write nothing and
tell you to run `init`.

The default config leaves out of the library any folder whose name starts with `.` or `_` (such as Obsidian's
`.obsidian`), folders named like an inbox (`sorting*`, `_sorting*`) and `attachments`, as well as the inbox and `.microfiche/`. To
leave out other folders, add them to `[exclusions] exclude` (see **Keeping a folder out** in
[section 4](#4-maintain-the-library)). The `microfiche/` folder of the
[repository](https://github.com/richard-gledhill/microfiche/tree/main/microfiche) has an example library file with
hints for five document-type categories.

### Checking and changing the settings

Run `init` again at any time, with the same command. On a library that is already set up it checks the config:

- **Valid.** It says so and asks whether to go through the settings. If you do, it shows each of the common ones
  (`confidence_threshold`, `depth`, `library_inbox`, `keep_folders`, the AI `provider` and `model`) with what it
  means, its value and its default, then asks whether to go through all the others, section by section (you can skip
  a section). Press Enter to keep a value; type `-` to clear a text or list setting; type a list comma-separated. A
  value that isn't valid is explained and asked again. Nothing is written until the end, when you see the changes
  and confirm them once.
- **Invalid.** It lists every problem, then offers to revert only the invalid and unknown settings to their
  defaults (your other settings are kept), to revert all of them, or to leave the file alone. It then offers the
  walk-through.

Before it rewrites the file, `init` keeps the old one as `.microfiche/microfiche-config.toml.bak` (it asks before
replacing an older backup). Your comments and layout are kept: a changed setting rewrites only its value. Pressing
Enter at every prompt leaves the file exactly as it was, with no backup. Ctrl-C before the last confirmation writes
nothing. Like every run that changes the library, the write takes the run lock (see [Two runs at once](#two-runs-at-once)).

`init` asks questions only in a terminal. Without one (in a script), a new library is still set up, and an existing
one is checked: a valid config passes, and an invalid one is reported and `init` exits with code 1, changing nothing.
If `microfiche-library.json` can't be read, `init` reports why and offers to rebuild it from the folders, keeping the
old one as `microfiche-library.json.bak`.

The inbox is called `_sorting` by default. To use another name — for example `Incoming`, or `sorting`
if you already have a folder by that name — change `library_inbox` in `init`'s walk-through, or set it under
`[library_structure]` in the config:

```toml
[library_structure]
library_inbox = "Incoming"
```

The inbox and the hidden `.microfiche/` folder are never treated as groups, whatever else you exclude.

Then edit `.microfiche/microfiche-library.json` in the library to add keyword hints and filename
rules for your categories (see below). See the
[configuration table](https://github.com/richard-gledhill/microfiche#configuration) for what each
config section does.

To see the settings without changing anything:

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
Config file error: C:\Users\you\Documents\Library\.microfiche\microfiche-config.toml:
  classification.confidence_threshhold: unknown setting
Run `microfiche init --library C:\Users\you\Documents\Library` to fix it.
```

`sort`, `review`, `reclassify`, `propose-categories` and `config` check the config the same way before they touch any
file. `audit` and `rollback` don't read it, so you can still undo a job while you fix the config.

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

A few things about the file:

- A category is matched by its name appearing anywhere in the text, as a plain case-insensitive substring (with the
  leading number dropped), so `Research` also matches `researchers`. A hint is matched the same way. Prefer
  distinctive names and hints, as for group names (see **Choosing names that work** below).
- A filing rule's `pattern` is a shell-style glob (`*` any characters, `?` one character, `[ab]` one of a set) matched
  against the whole file name, including the extension, ignoring case.
- Each entry may also have a `description`, a note for people reading the file that microfiche does not use. The `$schema`
  line at the top of the shipped file points editors at `microfiche-library.schema.json` for completion and checking.

A library with no `microfiche-library.json` still works: documents are matched on group and
category names alone. A mistake in the file (a misspelt key, say) stops `sort`, `review`, `reclassify` and
`config --sync` with a message saying where in the file the mistake is, and nothing is moved.

#### Keeping the file in step with your folders

You don't have to write the file's folder entries yourself. `init`, and the first real `sort` in a library with no
`microfiche-library.json`, create one that lists your group and category folders, with no hints, and say so:

```text
Created microfiche-library.json listing 4 folder(s). Add keyword hints to it to help match documents.
```

After that, each real `sort` adds an entry for any folder you have created since, and says so once. To do the same
without sorting, run `init` again, or `config --sync`, which asks nothing:

=== "Bash"

    ```bash
    uv run microfiche config --library ~/Documents/Library --sync
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche config --library "$HOME\Documents\Library" --sync
    ```

What it never does:

- It never changes or removes an entry you wrote, or their order: new entries are added at the end.
- It never creates or removes a folder. The folders decide what exists.
- It writes only when it adds something. When it does, it saves the whole file in a standard layout (two-space
  indent, keys in a fixed order, empty lists left out), so hand-made spacing is not kept; the content is.
- A folder whose name can't be an entry (it contains `/` or `\`, starts or ends with a space, or differs from a
  sibling only by case) is skipped with a warning.
- An entry whose folder has gone is listed every time you sort, and kept. If exactly one entry went and one folder
  appeared in the same place, the message suggests it was renamed. The new entry starts with no hints, so move
  them across yourself.
- An entry named `"*"` stands for every folder at its level that has no entry of its own, so where you have one,
  no entries are added for those folders. A library file made only of `"*"` entries is left exactly as it is.
- `sort --dry-run` and plain `config` write nothing.

To leave a folder out of the library, list it under `[exclusions]` in the config; there is no per-entry setting
for it. If microfiche can't write the file (it is read-only, or another program has it open), `sort` warns and
carries on, and `config --sync` exits with an error.

**Other taxonomies.** The same shape works for other kinds of library:

| Use case | Group | Category | Example path |
|---|---|---|---|
| Client work | client | document type | `Acme Ltd/Contracts/` |
| Study | course or subject | topic or week | `Machine Learning/Week 04/` |
| Household admin | area | topic | `Home/Insurance/` |

**Choosing names that work:**

- In a library with categories, groups are matched by name only — there are no keyword hints for groups — so use names that
  appear in your documents (project, client or course names usually do). A document that doesn't
  mention any group is listed under **Needs review** and left in the inbox.
- Categories can use hints, so they don't need to appear literally.
- A document that names two groups about equally (both by name), or whose text points at two categories about equally
  (two hints, say), is not guessed: it is listed under **Needs review** with both candidates and their confidences.
  How close counts as "about equally" is `[classification] ambiguity_margin` (default 0.1; a category's name
  is 0.15 stronger than a hint, so it still wins). A filename rule is never held by this.
- Names are compared in one spelling (`[classification] normalise_names`, on by default), so `meeting-notes`,
  `meeting_notes`, `MeetingNotes` and `Meeting Notes` all match the words "meeting notes", `R&D` matches "R and D",
  an apostrophe or accent doesn't matter, and keyword hints are compared the same way. `+` and `#` are kept, so `C++` and
  `C#` stay different names. Names, hints and fuzzy group matches count only as whole words, so `Car` is not found in
  `scarf` or `carrier` and a hint `lecture` does not match `lectures` (add both spellings as hints). A leading one-to-three-digit number such as `01 `, `01-` or `01_` is ignored, so you can use
  it to order folders; a date such as `2024-03 Invoices` is not. Your folders are never renamed. If two sibling
  folders read the same (`meeting-notes` and `meeting_notes`), or a name has no letters or digits, `config --sync` says so.
- A folder is left out of the library, and so cannot be a group or category, if its name matches a pattern in
  `[exclusions] exclude`. The default excludes `sorting*`, `_sorting*`, `.*`, `_*` and `attachments`: anything starting with a dot
  or an underscore, anything named like an inbox, and Obsidian's attachments folder. A group called `_Archive` or `.notes` is therefore invisible, which is
  usually what you want for such folders and a surprise if it isn't. See **Keeping a folder out** in [section 4](#4-maintain-the-library).
- One or two levels are supported: group and category, or groups alone (see
  [a flat library](#a-flat-library-groups-only)). Folders deeper than that aren't part of the taxonomy.

### A flat library (groups only)

If you don't need categories, give the library one level of folders. Set the depth in the config:

```toml
[library_structure]
depth = 1
```

Then take the category entries out of `.microfiche/microfiche-library.json`: a file that describes more levels than the
depth is an error, and the shipped file (like one `sort` wrote while the depth was 2) lists categories under a `"*"` group.
Delete those `children` (or the whole `"*"` entry), and put hints on the groups themselves, as below. Until you do,
`sort`, `review`, `reclassify` and `config --sync` stop with "it describes 2 levels of folders, but the library's depth is 1".

```text
Library/
├── .microfiche/
├── _sorting/
├── Project Phoenix/        <- group: documents are filed straight into it
├── Project Atlas/
└── Household/
```

A document is filed into a group folder as soon as the group is found; there is no second step. With only the
folder names to go on, give a group its own hints and filename rules in `.microfiche/microfiche-library.json`,
on the group's entry (a flat library has no categories to put them on):

```json
{
  "groups": [
    {
      "name": "Household",
      "hints": ["invoice", "utility bill", "council tax"],
      "rules": [{ "pattern": "statement-*.pdf" }]
    }
  ]
}
```

A group is found by, in order: a filename rule on its entry (0.95), its name appearing in the document (1.00 for
an exact match), then one of its hints (0.75). At the default threshold (0.75) all three file the document. If hints
of two different groups appear in the same document, microfiche does not choose between them: it is left for review. A
group entry may not have `children`: a library file that describes more levels than the depth is an error.

`sort`, `rollback`, `reclassify` and `config --sync` all work as they do with categories; the output simply names the
group. A folder dropped into the inbox is filed under the group most of its documents belong to; if two groups tie it
goes to review. The AI fallback is asked for the group only.

=== "Bash"

    ```bash
    uv run microfiche sort --library ~/Documents/Library --dry-run
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche sort --library "$HOME\Documents\Library" --dry-run
    ```

Changing `depth` in a library that already has records is allowed, but nothing is moved for you: the ledger keeps
each record as it was written, and `reclassify` will propose moves to the new shape.

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

The confidence values in the first table are settings too, and these are their defaults. You rarely need to
change them: moving the threshold gives the same effect, and the defaults were
[measured](https://github.com/richard-gledhill/microfiche/blob/main/docs/development/testing/calibration.md).
Change one if a kind of evidence is more or less trustworthy in your library, for example if you
want keyword hints to count for less:

```toml
[classification]
name_match_confidence = 0.9       # a category's name found in the text
filename_match_confidence = 0.95  # a filename rule
hint_match_confidence = 0.75      # a keyword hint
fuzzy_group_threshold = 85        # how close (0-100) a near-miss must be to a group's name
ambiguity_margin = 0.1            # hold a document if the runner-up group or category is this close (0 = exact ties only)
normalise_names = true            # compare names, hints and text in one spelling ("meeting-notes" = "Meeting Notes")

[ai]
ai_confidence = 0.70              # any answer from the AI fallback
max_document_chars = 4000         # how much of a document's text is sent to the AI
```

Each of these is from 0 to 1 and `fuzzy_group_threshold` from 0 to 100; `max_document_chars` must be at
least 0 (0 sends the whole document). Setting one at or above the threshold lets that kind of evidence file on its own.

**Raising the threshold files less; it doesn't file more accurately.** The confidence says what *kind* of
evidence was found, not how reliable it is, so a stray word in the text can rate higher than a
correct hint. In testing, the share of automatically filed documents that were wrong was about the
same at `0.75` as at `0.8` — the higher setting just held back far more documents. Measurements and
method: [calibration write-up](https://github.com/richard-gledhill/microfiche/blob/main/docs/development/testing/calibration.md).

If documents are being misfiled, the usual causes are in the names, not the threshold:

- **Group names that are short or common words** (`Car`, `Home`) match inside other words
  (`carrier`, `homework`). Prefer distinctive names, like `Project Phoenix` or `Acme Ltd`.
- **Category names that are ordinary words** (`Advertising`, `Construction`, `Contracts`) match anywhere in a document's
  text, so a paper that mentions advertising once is filed under `Advertising` at confidence 0.90. A library whose
  categories are such words, and that has no hints or filename rules yet, gets confident wrong answers.
- **Documents that mention another group** can be filed under it: of the groups named in the text, the
  one whose folder name sorts first wins, not the one the document is about. These are filed
  confidently, so they won't appear under **Needs review**; a `reclassify` dry run shows them as **move**.
- **Overlapping hints** — a word that is a hint for two categories goes to the category whose folder
  name sorts first. Keep hints specific.

**Starting on a library that is already large.** Don't begin with a real `sort`. Run `sort --dry-run` and
`reclassify` (neither changes anything, and both are quick even on thousands of files) and read what they propose. If
many of the proposed moves look wrong, set `confidence_threshold = 0.95`: only filename rules then file on their own,
and everything else waits for `review`. Add hints and filename rules for your categories, check again, and lower the
threshold when the proposals look right. Every real run can be undone with `rollback`.

**Check it on your own library.** Run `reclassify` (a dry run) on a library whose documents are
already filed correctly. **keep** means microfiche agrees with where you put a document; **move** means
it would have misfiled it. Change `confidence_threshold` and run it again to see how the numbers
change for *your* documents. The calibration write-up also describes a script that does this in
bulk.

## 3. Sort documents

Drop files (`.docx`, `.pdf`, `.md`, `.markdown`, `.txt`, `.eml`, `.msg`) into the inbox (`_sorting/` unless you named another), then run:

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

A file of any other type (a photo, a spreadsheet) is not a document to microfiche: `sort` leaves it in the inbox without
a word, and it is not counted in the summary. A folder with no document in it is ignored the same way.

If `sort` prints `Filed: 0`, `Needs review: 0` and `Duplicates: 0` and exits 0, nothing was found to sort. Check that
`--library` is the library's root, that the inbox has the name in `library_inbox` (`_sorting` by default), and that its
files are of the types above.

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

### Name collisions and duplicates

`sort` never overwrites or deletes a file, and renames one only if you have set a [naming rule](#renaming-on-the-way-in). Two
situations leave a file where it is:

- **A name collision.** The file would be filed under a name that is already taken, either by a different file
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

### Renaming on the way in

By default a file keeps its name when it is filed. To tidy names as they are filed, add rules to the `[naming_rules]` table of
the config: each rule is a regular expression and what to replace it with, applied in order to the whole file name,
extension included. This turns every run of spaces into one hyphen, so `My  Atlas Notes.md` is filed as `My-Atlas-Notes.md`:

```toml
[naming_rules]
rules = { '\s+' = "-" }
```

The name checks above use the new name, and `rollback` puts the file back under its old one. A rule that changes a name
into one already taken is a name collision, like any other. Use single quotes around a pattern so TOML doesn't read its
backslashes as escapes.

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
model = ""                        # required with --use-ai: e.g. "llama3.1" (Ollama), "gpt-4o-mini" (OpenAI)
host = ""                         # Ollama only; empty = http://localhost:11434, or e.g. "http://gpu-box:11434"
timeout = 120                     # seconds to wait for one answer; raise it if Ollama is slow to load the model
api_key_env = "OPENAI_API_KEY"    # the NAME of the variable holding your OpenAI key
verify_below = 0                  # 0 = off; 0.8 has the AI check hint matches, 0.95 names and near-miss groups too
ai_confidence = 0.70              # how sure any AI answer is
max_document_chars = 4000         # how much of each document is sent; 0 = all of it
```

**A second opinion.** By default the AI is asked only about what the rules could not place, and its answers (0.70) are
not filed at the default threshold. Set `verify_below` above 0 and `--use-ai` also has it check the rules' answers that
would file but score below that: keyword hints score 0.75, so `0.8` checks hints, and `0.95` checks category names and
near-miss group names as well. If the AI picks the same folder the document files as it would have, with "confirmed
by the AI" in its reason. If it picks another folder, or none, the document is left in the inbox for `review` with both
answers in the reason; the AI never files a document anywhere the rules did not propose. If the AI stops answering,
the rules' answers stand and `sort` warns once. Each check is one more call (a few seconds on a local model), and `sort`
prints how many answers were checked, confirmed and overruled. On the calibration corpus with one model, `0.95` removed
every misfile that remained without losing a correct filing; that is one model on short synthetic documents (see
[the calibration notes](https://github.com/richard-gledhill/microfiche/blob/main/docs/development/testing/calibration.md#ai-second-opinion)).

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

**A test before the run.** `--use-ai` needs `[ai] model` set to a model you chose: there is no default, and an
empty `model` stops the command with a note on how to set one (`ollama list` shows the Ollama models you have;
`ollama pull <name>` installs one). Before `sort` or `review` reads a document, it asks the AI one test question
that contains no document text ("Reply with the single word: OK") and prints `AI check passed: ollama llama3
answered in 1.2 s` (hidden by `-q`). If the AI does not answer, nothing is moved and the command stops with
exit code 1, saying what failed and what to do: pull the model, start Ollama (`ollama serve`), raise
`[ai] timeout` (a model's first load can be slow), or install the `ai` extra. This happens for `sort --dry-run
--use-ai` too, so a preview is a good way to try your setup. In `microfiche init`, changing an `[ai]` setting
offers the same test.

**If the AI fails part-way.** If it answered the test but then fails (the server stops, say), the first failure
switches the AI off for the rest of that run (so a dead server is waited on once, not once per document).
Everything the rules can decide is filed as usual, and anything only the AI could have answered stays under
**Needs review**. `sort` says so in its summary, even with `-q`: `The AI fallback was unavailable (<reason>).`
The warning is also in the log file (see [Troubleshooting](#5-troubleshooting)).

### Working through Needs review

Whatever `sort` doesn't file stays in the inbox under **Needs review**. `review` goes through those documents one at a
time and asks you what to do with each:

=== "Bash"

    ```bash
    uv run microfiche review --library ~/Documents/Library
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche review --library "$HOME\Documents\Library"
    ```

```text
Item 1 of 6: phoenix-loose-ends.md (file)
  Classifier said: No category keyword or name matched
  (m) modify   (s) skip   (q) quit
What now? [s]:
```

That is a document with a group but no category. When the classifier has a guess that `sort` held back (for instance a
0.90 match in a library whose `confidence_threshold` you raised to 0.95), it is shown, and `(a)` is offered:

```text
  Best guess: Project Phoenix/02 Architecture (confidence 0.90; 0.95 is needed to file without asking)
  (a) accept the best guess   (m) modify   (s) skip   (q) quit
```

- **(a) accept** files it where the classifier would have, if that is possible. It is not offered when the guess is
  taken (a file of that name is already there) or when the classifier had no guess.
- **(m) modify** asks for a group, then a category (a flat library has no category), from numbered lists. Choose `n`
  to plan a new folder instead: you type a name and confirm the exact path, for example
  `Create 'Project Phoenix/04 Retrospectives' when the units are filed?`
- **(s) skip** leaves the document in the inbox. It is the default, so pressing Enter skips.
- **(q) quit** stops asking. What you have chosen so far is still offered for filing.

**Nothing is moved while you answer.** At the end you see what you chose and any new folders, and confirm once. Then the
chosen documents are filed together as one job, with its id and the command that undoes it, exactly as `sort` does.
Pressing Ctrl-C before that confirmation moves nothing.

- **Each choice is checked as you make it**, with the same checks `sort` makes: the name must be free in the folder you
  chose, and the content must not already be in the library (or be going there from an earlier choice in this session).
  If not, you are told why and asked again. A document that is replaced or edited between your choice and the final
  confirmation is left in the inbox, not filed, and `review` says so.
- **New folders are made when a document is filed into them.** A folder you planned but never used is never created,
  and one made for a move that then failed is taken back. A name is refused if it is already there (as a folder
  microfiche filed whole, a link or a file), is the inbox or state folder, matches `[exclusions]`, or is a reserved
  Windows name such as `CON`. Undoing the job moves the documents back but leaves the new folder in place, empty, because
  microfiche never deletes a folder it created. The next
  `sort`, or `config --sync`, lists the new folder in `microfiche-library.json`.
- **A folder dropped into the inbox is one unit.** You choose one destination for all of it. To file its documents
  separately, run `sort --keep-folders-off`.
- **Copies are not in the queue.** A document that is identical to another one stays in the inbox; `review` says how
  many, and `sort` lists them. It also says how many documents are confident enough for `sort` to file, which it does
  not ask about.
- **The run lock is taken only when filing.** You can take as long as you like to decide. If another run holds the lock
  when you confirm, `review` says so and asks whether to try again; your choices are kept until you say no.
- In the group and category lists, press Enter without a number to go back.
- `--use-ai` asks the AI for a best guess where the rules have none, as `sort --use-ai` does. `-v` and `-q` work as
  elsewhere.

`review` needs a terminal, because it asks questions. It reads the inbox afresh each time, so a document you skipped is
offered again next time.

### Letting `review` teach hints

`review` can learn from what you file by hand. It is off by default, because it writes to `microfiche-library.json`:

```toml
[learning]
enabled = true
```

After a `review` commit, for each category you filed into, microfiche looks at the documents you filed there (not the ones
`sort` filed) and adds `learned_hints` to that category's entry: words that most of them contain and that no document
under another category of the same group contains. It says what it added:

```text
Learned the hint 'remittance' for Finance/Bills
```

Learned hints match like your own hints (whole words, the hint score) and show as "Learned keyword hint" in a document's
reason; `sort` says how many documents they filed. The guardrails are `min_decisions` (a category needs 3 documents you
filed before anything is learned, default 3), `max_hints_per_run` (3) and `min_word_length` (4); common words, the words
in the group's and category's names and anything already a hint are never learned. Your own `hints`, `rules` and entries are
never changed.

To remove a learned hint, delete it from `learned_hints` in `microfiche-library.json`; microfiche remembers it (in the
ledger) and does not learn it again. `rollback` undoes the moves of a `review` job, not the hints it taught.

### When you move filed documents by hand

You can reorganise the library in Obsidian or Explorer. microfiche notices: `sort`, `review`, `file`, `reclassify`,
`rollback` and `config` compare what they have recorded with what is on disk, and tell you in one line when something
differs, such as `2 filed items: 2 moved, 1 missing; recorded`. They never move, rename or delete anything because of it.

- **Moved.** A document that is gone from where it was filed, but whose content is at exactly one other place in the
  library, is *moved*. A command that changes the library (`sort`, `review`, `file`, `reclassify --apply`, `rollback`)
  records the new place, so `rollback` and `reclassify` follow it; `--dry-run`, a `reclassify` preview and plain
  `config` only report. The next command says nothing more about it. A folder filed whole is followed the same way,
  if it keeps its name.
- **Missing.** Gone, and not found by content. A document that was moved *and* edited, or two identical copies elsewhere,
  also counts as missing: microfiche does not guess. `rollback` stops before moving anything and names the file.
- **Edited.** Present but changed since it was filed. Only commands that read the file anyway can say so: `reclassify`
  reports it, and `rollback` moves it back as it is and says it was edited. `sort` does not read filed documents, so it
  does not notice an edit.

The details are in the log (and with `-v`); `--json` output has a `drift` object. Finding a moved document searches the
library for same-type files that nothing else accounts for, which can take a moment on a large library but only runs when
something is missing.

### Files that can't be sorted

One awkward file never stops a run. It stays where it is, and the summary says why:

- **Open in another program.** A document that Word (or another program) has open cannot be moved on
  Windows. It is listed under **Needs review** as `... but it could not be moved: it is open in another program;
  close it and sort again`. A program that holds the file so that it can't even be read (Word with a document open for
  editing, say) gives `Could not read '<file>': PermissionError ...` instead, with the same remedy. Moves are plain
  renames, so a failed move leaves nothing behind: no stray copy, and nothing recorded in the job, ledger or audit log.
  Close the file and sort again. With `--keep-folders-off`, a
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

### Keeping the inbox filed with `watch`

`watch` runs until you stop it and files documents without you running `sort`. It looks at the inbox on a timer and files
a document once it has **stopped changing**, so a file that is still being saved, downloaded or synced is left alone.

=== "Bash"

    ```bash
    microfiche watch --library ~/Documents/Library             # one scan an hour (the default); Ctrl-C to stop
    microfiche watch --library ~/Documents/Library --interval 60   # one scan a minute
    microfiche watch --library ~/Documents/Library --use-ai -q     # with the AI fallback, errors only
    ```

=== "PowerShell"

    ```powershell
    microfiche watch --library "$HOME\Documents\Library"                 # one scan an hour (the default); Ctrl-C to stop
    microfiche watch --library "$HOME\Documents\Library" --interval 60   # one scan a minute
    microfiche watch --library "$HOME\Documents\Library" --use-ai -q     # with the AI fallback, errors only
    ```

- **When a document is filed.** Each scan only reads file sizes and times, never content, so a cloud-synced placeholder
  is not downloaded by being looked at. A document is *stable* when its size and time are the same in two scans in a
  row, and a batch runs when something is stable **and** the latest scan found nothing new or changed. So a folder you
  copy in is filed as one job after it has finished arriving, and a document lands in its folder between one and two
  intervals after it appears. A shorter `--interval` (or `[watch] interval_seconds`) files sooner.
- **What a batch is.** A normal `sort` of those documents: the same confidence threshold, collision and duplicate checks
  and drift check, and **one job** per batch that `rollback` undoes. It prints one line, for example
  `09:14:02 Filed 3, 1 for review, 0 duplicate(s); undo with rollback --job-id ...`. Idle scans print nothing (`-v` shows
  them); `-q` shows errors only.
- **Documents left for review** are not looked at again every scan. `watch` tries one again only when the document
  changes, or when the config or the library file changes (new hints, including learned ones). Work through them with
  `review`, which you can run whenever `watch` is between batches.
- **The run lock** is held only while a batch is filed. If another run (a `review` that is filing, a `rollback`) holds it,
  the batch waits up to `[watch] lock_timeout_seconds` (30), then is skipped and tried again at the next scan; `watch`
  never exits because the lock is busy.
- **The AI** is used only with `--use-ai`. It is checked once, when `watch` starts, and the OpenAI notice (if that is your
  provider) is shown once. If the AI fails later, the rest of the run uses the rules only.
- **Stopping.** Press Ctrl-C once: `watch` finishes the batch in progress, so no job is left half-filed, then stops. A
  second Ctrl-C stops at once.
- **A failure** (an unreadable config, a disk error) is shown and `watch` tries again at the next scan.
- **`--json`** prints one compact JSON line on stdout for each batch that filed or left something: the same document as
  `sort --json`. A failed batch is a line of `{"version": 1, "command": "error", "error": "..."}`; messages go to stderr.
- `watch` is started by you and runs in your terminal; it is not a Windows service. Pointing it at a OneDrive-synced
  inbox has not been tested by hand yet: check that no placeholder is downloaded just by being scanned, and that nothing is
  moved mid-sync, before relying on it.

### Two runs at once

`init`, `sort`, `reclassify --apply`, `rollback`, `config --sync`, `watch` (while it files a batch) and `review` (when it files, at the end) change the library,
so only one can run at a time. Each takes a lock (a small `lock` file in `.microfiche/`, removed when the run ends), and a
second one refuses to start:

```text
Another microfiche run is already in progress (sort, process 4242, started 2026-10-12 09:30:12). Wait for it to
finish and try again. If no run is active, delete <library>/.microfiche/lock and try again.
```

Wait for the first run, then try again. If a run was killed or the machine lost power, you need do nothing: the
lock records the process that took it, and a lock whose process is gone is cleared automatically. The run that clears
it warns you (`cleared a stale run lock left by a run that did not finish (sort, process 4242, started ...)`) and
records that in the log, which tells you an earlier run never finished. If the lock
file is damaged so that microfiche can't tell, it is treated as held, and the message names the file to delete.
A preview (`sort --dry-run`), `reclassify` without `--apply`, `audit`, `config` without `--sync` and `propose-categories`
only read, so they need no lock and run beside anything.

### Running unattended

`sort` asks no questions, so it can run from a scheduler. The things that matter when it does:

- **Use the full path to the command**, since a scheduler has a shorter `PATH` than your terminal: `which microfiche`
  (Bash) or `(Get-Command microfiche).Source` (PowerShell) prints it.
- **Add `-q`**, so that only errors are printed. Look at the exit code: `0` means the run did what was asked (including
  leaving some documents for review), `1` means it could not (a bad config, another run in progress). See
  [Exit codes](#exit-codes).
- **Overlapping runs are refused**, not queued (see above), so a slow run and the next scheduled one cannot collide.
  To keep the inbox filed continuously instead of on a schedule, see [Keeping the inbox filed with `watch`](#keeping-the-inbox-filed-with-watch).
- **`review` is never part of it.** Whatever `sort` leaves is waiting under **Needs review** until you run `review`.

=== "Bash"

    ```bash
    # cron: every day at 07:00 (crontab -e)
    0 7 * * * /home/you/.local/bin/microfiche sort --library /home/you/Documents/Library -q
    ```

=== "PowerShell"

    ```powershell
    # Task Scheduler: every day at 07:00
    schtasks /Create /SC DAILY /ST 07:00 /TN "microfiche sort" /TR "C:\Users\you\.local\bin\microfiche.exe sort --library C:\Users\you\Documents\Library -q"
    ```

Try the command by hand first, with `--dry-run`, and check `.microfiche/microfiche.log` afterwards: it records every run
that changes the library.

### Reading the results from a script

`sort`, `reclassify`, `rollback`, `audit`, `config` and `review --list` take `--json`. The command then writes **one JSON
document to stdout and nothing else there**; messages, warnings and the progress bar go to stderr, and the exit code is
what it always was. If the command cannot run (a bad config, another run in progress) stdout holds
`{"version": 1, "command": "error", "error": "..."}` and the exit code is 1.

=== "Bash"

    ```bash
    microfiche sort --library ~/Documents/Library --dry-run --json | jq '.needs_review[] | {path, reason}'
    microfiche review --library ~/Documents/Library --list --json     # what `review` would ask about, no terminal needed
    microfiche rollback --library ~/Documents/Library --last --json
    ```

=== "PowerShell"

    ```powershell
    microfiche sort --library "$HOME\Documents\Library" --dry-run --json | ConvertFrom-Json | Select-Object -ExpandProperty needs_review
    microfiche review --library "$HOME\Documents\Library" --list --json
    microfiche rollback --library "$HOME\Documents\Library" --last --json
    ```

What the document holds is what the human output shows: for `sort`, the units filed (with where each went), left for
review, and held as duplicates, each with its group, category, confidence and reason, plus the job id to give
`rollback`. Paths are relative to the library, with forward slashes, and **no document text is ever included**. Every
document has a `version` (now `1`) that changes only when a field is removed or its meaning changes; new optional
fields can appear without a bump. The shape of each is a JSON Schema in the repository's
[`schemas/`](https://github.com/richard-gledhill/microfiche/tree/main/schemas) folder, one per command.

`review` itself asks questions and has no JSON mode: use `review --list --json` to see the queue. `--json` with
`--dry-run` previews as it always did; the exit code is `1` if a move failed.

### Filing held documents from a script

`file` does for named documents what `review` does by hand, without asking. Name them by their path inside the inbox (as
`review --list` prints them) and give the folder with `--to`:

=== "Bash"

    ```bash
    microfiche file SolarConstructionNotes.md --library ~/Documents/Library --to "Project Phoenix/03 Research" --json
    ```

=== "PowerShell"

    ```powershell
    microfiche file SolarConstructionNotes.md --library "$HOME\Documents\Library" --to "Project Phoenix/03 Research" --json
    ```

The folder must already exist (`Group/Category`, or just `Group` in a library of groups only); case does not matter and
nothing is created. Several documents can be named for one folder: they are filed as **one job**, which `rollback`
undoes, recorded as your choice (so `[learning]`, if on, learns from it). The checks are `review`'s: the document is
still waiting for a decision (not one `sort` would file, not a copy of a document already in the library), its name is
free in the folder, and it has not changed. **If any document is refused, nothing is moved** and the exit code is `1`;
with `--json` the document says which and why (`refused`). A document that passed but could not be moved (open in another
program) is listed under `failed`, also with exit code `1`.

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

**With the AI.** `reclassify --use-ai` uses the AI as `sort --use-ai` does (see [The AI fallback](#the-ai-fallback)): it
is asked about documents the rules cannot place and, if `[ai] verify_below` is above 0, to check rules answers that score
below it. A document whose answer the AI disagrees with is shown as **review** and left where it is, so a second opinion
can only keep a document from moving, never move it somewhere the rules did not propose. The same test question runs
first, nothing is moved if it fails, and the table is followed by how many answers were checked, confirmed and
overruled.

**A folder that was filed whole stays whole.** When `keep_folders` is on, `sort` files a dropped folder as one unit.
`reclassify` treats it the same way: it is one row in the table, classified by the group and category most of its
documents belong to, and `--apply` moves the whole folder or none of it. A document inside it that reads as something
else does not leave it. (Microfiche knows which folders it filed from its ledger, and follows a folder you moved by hand as long as it kept
its name; see [When you move filed documents by hand](#when-you-move-filed-documents-by-hand).)

**Keeping a folder out.** A folder inside a category that microfiche did not file, such as `attachments/`, is just a
place files sit: `reclassify` reads its files one by one and may propose moving one out. To leave such a folder alone,
and to stop a folder being used for filing at all, list it under `[exclusions]` in the config. A name or a glob works,
at any level, so this skips every folder whose name starts with a date such as `20260115_`:

```toml
[exclusions]
exclude = ["sorting*", "_sorting*", ".*", "_*", "attachments", "[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_*"]
```

The first four patterns are the ones the shipped config already has: a list you write **replaces** the list, it doesn't add to
it. Leave them out and folders such as `.obsidian` or `_Archive` become groups. Keep them, and add yours at the end.

**If you reduce the depth.** Say you change `depth` from 2 to 1 (and, as in [a flat library](#a-flat-library-groups-only),
remove the category entries from `microfiche-library.json`, or every command stops on it). Nothing is moved. The old category folders are now
plain folders inside their group, an item in one is kept where it is while it is still in the group it belongs to, and
`reclassify` tells you how many filed items sit below the new depth (it counts the items microfiche filed itself, from
its ledger, so documents you put there by hand are not in the number):

```text
12 filed item(s) sit in folders below the library's depth (1). Those folders are no longer groups or categories; ...
```

Raising the depth needs nothing special: `reclassify` proposes moving the existing items into the new level.

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

To undo the newest job instead, so you needn't copy its id, use `--last`. It means the newest job that has not been
undone, so running it again steps back through earlier jobs one at a time, and it says which job it undid. Give
exactly one of `--job-id` and `--last`:

=== "Bash"

    ```bash
    uv run microfiche rollback --library ~/Documents/Library --last
    ```

=== "PowerShell"

    ```powershell
    uv run microfiche rollback --library "$HOME\Documents\Library" --last
    ```

## 5. Troubleshooting

When a document didn't go where you expected, or a run did less than you thought, microfiche can tell you why.

### What microfiche shows while it runs

By default it shows only what needs your attention: warnings and errors. They are printed on screen (stderr), so the
summary `sort` prints (stdout) stays clean to pipe or redirect. Two options, on `sort`, `review`, `reclassify`, `rollback`,
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

- **Who writes it.** `init`, `sort`, `reclassify --apply`, `rollback`, `config --sync` and `review` (when it files), the commands
  that take the lock. A preview (`sort --dry-run`, `reclassify` without `--apply`) and the read-only commands (`audit`,
  `config` without `--sync`, `propose-categories`) write nothing, and a preview never creates `.microfiche/`. A run that is refused because
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
2026-10-12 17:06:43,348 DEBUG microfiche.core.classifier: research-summary.md: group Project Phoenix (1.00, Exact match on group name 'Project Phoenix'); category 03 Research (0.90, Category name '03 Research' found in document text); by rules_engine
2026-10-12 17:06:43,349 DEBUG microfiche.core.classifier: SolarConstructionNotes.md: group None (0.00, No known group name found in document text); category None (0.00, Group unresolved); by rules_engine
2026-10-12 17:06:43,349 DEBUG microfiche.core.organizer: SolarConstructionNotes.md: left for review (confidence 0.00)
2026-10-12 17:06:43,354 INFO microfiche.core.organizer: sort finished: 2 filed, 1 for review, 0 duplicate(s)
```

### Exit codes

Every command ends with one of three exit codes, so a script can tell what happened:

| Code | Meaning |
|---|---|
| `0` | The command did what was asked. This includes a `sort` that left documents under **Needs review**, a `reclassify` dry run that proposes moves, and `--version`. |
| `1` | The command could not do what was asked: an invalid config or library file, a library run already in progress, a job that does not exist or was already rolled back, a rollback that stopped part-way, `sort`, `reclassify` or `propose-categories` on a library with no config (run `init`), `init` on an invalid config without a terminal or when you chose to leave it, `review` without a terminal, options that contradict each other or leave out a choice microfiche checks itself (`rollback` with neither `--job-id` nor `--last`), or a run you stopped with Ctrl-C. Nothing is half-done silently: the message says what to fix. |
| `2` | The command line itself was wrong: an unknown command or option, or a required option such as `--library` missing. Nothing ran. |

A run that files some documents and leaves others for review still exits `0`; read the summary, or the **Needs review**
list, for those.

## Current limitations

microfiche is pre-release. At the moment:

- `reclassify --use-ai` asks the AI the same questions as `sort`, so a preview costs the same calls; without `--use-ai`
  it applies the rule-based classifier only.
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
- The inbox setting `[sorting] ignore` applies to `sort`, not to `reclassify`, which honours `[parsing] max_file_mb`.
  Links are skipped by both: `reclassify` never lists a symbolic link or junction, or anything behind one.
- A file open in another program is not retried: close it and run `sort` again. (`watch` leaves it held until it changes.)
- `watch` is a command you start and leave running, not a service or a startup item. It has not been tested on a
  OneDrive-synced inbox.
- `review` offers only the classifier's best guess (and the AI's, with `--use-ai`); it does not rank alternatives. You
  cannot go back to an item once you have moved on, and it learns from your choices only if you turn `[learning] enabled` on (see **Letting `review` teach hints**);
  otherwise add a keyword hint to `microfiche-library.json` if a kind of document keeps coming up.
- `review` needs a terminal. A script reads its queue with `review --list --json` and files held documents with `file`.
  `file` cannot plan a new folder and does not use the AI.
- `init` has no options to answer its questions in advance, and does not edit `[naming_rules]` (edit it in the file),
  hints or filename rules. A fresh install uses the one default config; there are no templates to choose from.
- microfiche does not write Obsidian `index.md` folder notes or govern tags yet; that is planned as an optional
  integration after the first release.
- A folder you move by hand after `sort` filed it whole is no longer recognised as one unit by `reclassify` (the
  ledger names its old path), and `reclassify` reads a bundle's folder through the ledger, so a corrupt ledger stops it.
- There is no command to bring items up to the new depth after you reduce it; they stay where they are. An opt-in way
  is recorded as an idea, to be reviewed.
- In a two-level library, a folder you make directly inside a group is read as a category, listed in
  `microfiche-library.json` and used for filing, unless `[exclusions]` names it. The default `[exclusions]` list leaves
  out `attachments` (Obsidian's folder for pasted files), but a list you wrote replaces the default, so add it there
  yourself if your config predates that. Loose files saved directly in a group folder are never listed. `reclassify`
  treats such a file as out of place and proposes moving it into a category when one matches, unless the group has no
  category folders and `[sorting] file_in_empty_groups` is on (see below).
- A group with no category folders is not filed into by default: a document that names it goes to review, so a group you
  made as a placeholder gets nothing. Set `file_in_empty_groups = true` under `[sorting]` to file such documents
  straight into the group; `sort` and `review` then say how many went there. Once the group gains its first
  category folder, files already at group level are one level too high, and `reclassify` proposes moving them. Such a
  group is chosen by its name only (hints and filename rules apply to categories).
- A flat library (`depth = 1`) is matched on group names, filename rules and group hints only. A short group name
  that is also a passing mention (`car park`) can still beat the real group; see the
  [calibration notes](https://github.com/richard-gledhill/microfiche/blob/main/docs/development/testing/calibration.md#flat-libraries-depth-1).
  `propose-categories` has nothing to propose in a flat library and says so.
- The library file is synced by `init`, on a real `sort` and by `config --sync`, not on a preview, so `sort --dry-run` does not
  list folders that would be added or entries with no folder. The sync reads only down to the library's depth (1 or 2).
  A folder that is a link or junction is not a group or category.
- `-q` hides the "AI fallback unavailable" log warning on screen (it is still in the log file); the `sort`
  summary line says it anyway.
- A file that can't be moved is reported twice on screen: as a warning when it happens (also in the log file), and
  again in the summary's **Needs review** list.
- The log file is written only by commands that change the library, and not by `rollback` when the config can't be
  read.
- In a library with categories (`depth = 2`), `hints` or `rules` written on a *group's* own entry are accepted but not
  used: only a flat library matches on them. Put them on the group's category entries (`children`) instead.
- If an undo stops part-way (for example something now occupies a document's original place), that job stays the newest one not undone, so
  `rollback --last` tries it again and never reaches an older job. Fix the cause, or undo an older job by its id. "Newest"
  is by the time the job was made on this computer's clock. A job file that cannot be read is skipped with a warning.
- `-q` also hides the warning that a leftover lock was cleared. It is still in the log file.
- The progress bar's threshold (20 documents, or any `--use-ai` run) is fixed; there is no setting for it.

Every command and option is listed in the [CLI reference](cli-reference.md), or run
`uv run microfiche <command> --help`.
