# CLI reference

Organize project reference materials into a structured library.

**Usage**:

```console
$ microfiche [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--version`: Show the version and exit.
* `--install-completion`: Install completion for the current shell.
* `--show-completion`: Show completion for the current shell, to copy it or customize the installation.
* `--help`: Show this message and exit.

**Commands**:

* `init`: Set up the library's configuration, or...
* `sort`: Classify and file what is in the inbox.
* `watch`: Keep the inbox filed: scan it on a timer...
* `review`: Decide where the leftover documents go.
* `file`: File held inbox documents into a folder,...
* `propose-categories`: Suggest new category folder names.
* `reclassify`: Re-check where filed documents belong.
* `audit`: Show the audit log.
* `rollback`: Undo a filing job.
* `config`: Show the library's configuration.

## `microfiche init`

Set up the library's configuration, or check it and change it.

With no configuration in .microfiche/, writes the default one, asking nothing. With a valid one, offers to go
through the settings one by one; with an invalid one, lists the problems and offers to revert only the invalid
settings, or all of them, to the defaults. Changes are written only after you choose or confirm them, and the
file as it was before the run is kept as microfiche-config.toml.bak. Then creates the inbox if it is missing and adds the library's folders to
.microfiche/microfiche-library.json, as `config --sync` does. Never touches your folders or documents.

**Usage**:

```console
$ microfiche init [OPTIONS]
```

**Options**:

* `--library <directory>`: Path to the library root.  [required]
* `-v, --verbose`: Also show progress messages on screen, and record debugging detail in the log file.
* `-q, --quiet`: Show errors only on screen. Wins over --verbose.
* `--help`: Show this message and exit.

## `microfiche sort`

Classify and file what is in the inbox.

Everything classified with enough confidence is filed as one job, which `rollback` can undo; the rest stays in the
inbox for `review`.

**Usage**:

```console
$ microfiche sort [OPTIONS]
```

**Options**:

* `--library <directory>`: Path to the library root.  [required]
* `--keep-folders`: Sort whole folders from the inbox intact, filed under the group or category most of their documents belong to, for this run.
* `--keep-folders-off`: File the documents inside inbox folders one by one for this run, and remove each folder once it is empty, whatever the library's keep_folders setting says.
* `--use-ai`: Fall back to the AI named in the library's config (Ollama unless it says otherwise) for classifications the rules engine can't resolve. Needs [ai] model set. Before any document is read, one test question (no document text) checks the AI answers; if it does not, nothing is moved and the command stops with the reason.
* `--dry-run`: Preview what would be filed and what would need review, without moving or recording anything. Classification, including any --use-ai calls, runs as usual.
* `--json`: Print the result as one JSON document on stdout and nothing else there (messages and progress go to stderr). The shape is versioned and documented in schemas/.
* `-v, --verbose`: Also show progress messages on screen, and record debugging detail in the log file.
* `-q, --quiet`: Show errors only on screen. Wins over --verbose.
* `--help`: Show this message and exit.

## `microfiche watch`

Keep the inbox filed: scan it on a timer and file what has stopped changing.

Each scan only looks at file sizes and times, never at content. A document is filed once it is unchanged between two
scans (so between one and two intervals after it arrives) and nothing else arrived or changed in the latest scan,
so a folder copied in is filed as one job. Each batch is a normal `sort` of those documents: the same checks, and
one job that `rollback` can undo. A document left for review is looked at again only when it changes or when the
config or the library file does. Press Ctrl-C to stop: the batch in progress finishes first.

**Usage**:

```console
$ microfiche watch [OPTIONS]
```

**Options**:

* `--library <directory>`: Path to the library root.  [required]
* `--interval <float>`: Seconds between scans of the inbox, for this run. Defaults to [watch] interval_seconds (3600).
* `--use-ai`: Fall back to the AI named in the library's config, as `sort --use-ai` does. The test question is asked once, at the start; if the AI later fails, the rest of the run uses the rules only.
* `--json`: Print one compact JSON line on stdout for each batch: the same document as `sort --json`, or an `error` line if the batch failed. Messages go to stderr.
* `-v, --verbose`: Also show progress messages on screen, and record debugging detail in the log file.
* `-q, --quiet`: Show errors only on screen. Wins over --verbose.
* `--help`: Show this message and exit.

## `microfiche review`

Decide where the leftover documents go.

Works through the documents `sort` left in the inbox. For each one you can accept the best guess, pick a group and category (or plan a new folder), skip it, or quit.
Nothing is moved while you answer. At the end you see what you chose and confirm once; the chosen documents are
then filed as one job, which `rollback` can undo. Documents you skip stay in the inbox, and so do copies of
documents already in the library. Needs a terminal, except with --list, which only prints the queue.

**Usage**:

```console
$ microfiche review [OPTIONS]
```

**Options**:

* `--library <directory>`: Path to the library root.  [required]
* `--list`: Only list what `review` would ask about, with the classifier's best guess for each, and ask nothing. Works without a terminal.
* `--use-ai`: Ask the AI named in the library's config for a best guess where the rules have none, as `sort` does, including the test question first (see `sort --help`).
* `--json`: Print the result as one JSON document on stdout and nothing else there (messages and progress go to stderr). The shape is versioned and documented in schemas/.
* `-v, --verbose`: Also show progress messages on screen, and record debugging detail in the log file.
* `-q, --quiet`: Show errors only on screen. Wins over --verbose.
* `--help`: Show this message and exit.

## `microfiche file`

File held inbox documents into a folder, without asking.

Does what `review` does for the documents you name, from a script: the same checks (the folder exists, the name is
free there, the document is not a copy of one already in the library, it has not changed), and the same single
job, which `rollback` can undo. Only documents `sort` left for a decision can be filed. If any one is refused,
nothing is moved and the exit code is 1.

**Usage**:

```console
$ microfiche file [OPTIONS] {units}...
```

**Arguments**:

* `units...`: The inbox documents or folders to file, named by their path inside the inbox (`review --list` shows them).  [required]

**Options**:

* `--library <directory>`: Path to the library root.  [required]
* `--to <str>`: Where they go, as a folder that already exists: `Group/Category`, or `Group` in a library of groups only (or for a group that has no categories, with [sorting] file_in_empty_groups).  [required]
* `--json`: Print the result as one JSON document on stdout and nothing else there (messages and progress go to stderr). The shape is versioned and documented in schemas/.
* `-v, --verbose`: Also show progress messages on screen, and record debugging detail in the log file.
* `-q, --quiet`: Show errors only on screen. Wins over --verbose.
* `--help`: Show this message and exit.

## `microfiche propose-categories`

Suggest new category folder names.

Looks at common terms across the documents in the inbox. Never creates folders - this only prints suggestions. Scoping to an existing library folder
instead of the inbox isn't implemented yet.

**Usage**:

```console
$ microfiche propose-categories [OPTIONS]
```

**Options**:

* `--library <directory>`: Path to the library root.  [required]
* `-v, --verbose`: Also show progress messages on screen, and record debugging detail in the log file.
* `-q, --quiet`: Show errors only on screen. Wins over --verbose.
* `--help`: Show this message and exit.

## `microfiche reclassify`

Re-check where filed documents belong.

Reports where the classifier would file each already-filed document now. Without --apply this is a dry run. With --apply, the documents the table marks "move" are
re-filed as one job (undo it with `rollback`); the rest are left exactly where they are.

**Usage**:

```console
$ microfiche reclassify [OPTIONS]
```

**Options**:

* `--library <directory>`: Path to the library root.  [required]
* `--folder <path>`: Limit to this folder; defaults to the whole library.
* `--apply`: Actually move files; without this it's a dry run.
* `--use-ai`: Use the AI named in the library's config as `sort --use-ai` does: for what the rules can't place, and to check rules answers scoring below [ai] verify_below. A document the AI disagrees with is left where it is. Needs [ai] model set; one test question (no document text) checks the AI answers first.
* `--json`: Print the result as one JSON document on stdout and nothing else there (messages and progress go to stderr). The shape is versioned and documented in schemas/.
* `-v, --verbose`: Also show progress messages on screen, and record debugging detail in the log file.
* `-q, --quiet`: Show errors only on screen. Wins over --verbose.
* `--help`: Show this message and exit.

## `microfiche audit`

Show the audit log.

**Usage**:

```console
$ microfiche audit [OPTIONS]
```

**Options**:

* `--library <directory>`: Path to the library root.  [required]
* `--json`: Print the result as one JSON document on stdout and nothing else there (messages and progress go to stderr). The shape is versioned and documented in schemas/.
* `-v, --verbose`: Also show progress messages on screen, and record debugging detail in the log file.
* `-q, --quiet`: Show errors only on screen. Wins over --verbose.
* `--help`: Show this message and exit.

## `microfiche rollback`

Undo a filing job.

Give the id `sort` printed, or use --last for the newest job that has not been undone.

**Usage**:

```console
$ microfiche rollback [OPTIONS]
```

**Options**:

* `--library <directory>`: Path to the library root.  [required]
* `--job-id <str>`: The id `sort` printed. Give this or --last.
* `--last`: Undo the newest job that has not been undone.
* `--json`: Print the result as one JSON document on stdout and nothing else there (messages and progress go to stderr). The shape is versioned and documented in schemas/.
* `-v, --verbose`: Also show progress messages on screen, and record debugging detail in the log file.
* `-q, --quiet`: Show errors only on screen. Wins over --verbose.
* `--help`: Show this message and exit.

## `microfiche config`

Show the library's configuration.

With --sync it instead brings the library file in step with the folders. --sync adds an entry, with no hints, to .microfiche/microfiche-library.json for each group and category folder
that has none, creating the file if the library has none. It never changes or removes an entry, and never
creates or removes a folder. An entry whose folder is gone is listed each time, and kept.

**Usage**:

```console
$ microfiche config [OPTIONS]
```

**Options**:

* `--library <directory>`: Path to the library root.  [required]
* `--sync`: Instead of showing the configuration, add an entry to the library file for every folder that has none, and list entries whose folder is gone.
* `--json`: Print the result as one JSON document on stdout and nothing else there (messages and progress go to stderr). The shape is versioned and documented in schemas/.
* `-v, --verbose`: Also show progress messages on screen, and record debugging detail in the log file.
* `-q, --quiet`: Show errors only on screen. Wins over --verbose.
* `--help`: Show this message and exit.
