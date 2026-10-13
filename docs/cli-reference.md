# CLI reference

Organize project reference materials into a structured library.

**Usage**:

```console
$ microfiche [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--install-completion`: Install completion for the current shell.
* `--show-completion`: Show completion for the current shell, to copy it or customize the installation.
* `--help`: Show this message and exit.

**Commands**:

* `sort`: Process the library&#x27;s inbox: classify and...
* `review`: Decide where the documents `sort` left in...
* `propose-categories`: Suggest new category folder names from...
* `reclassify`: Re-review already-filed documents and...
* `audit`: Show the audit log.
* `rollback`: Undo a filing job by id (the id `sort`...
* `config`: Show the library configuration, or with...

## `microfiche sort`

Process the library&#x27;s inbox: classify and file everything above the confidence threshold.

**Usage**:

```console
$ microfiche sort [OPTIONS]
```

**Options**:

* `--library <directory>`: Path to the library root.  [required]
* `--keep-folders`: Sort whole folders from the inbox intact, filed under the group or category most of their documents belong to, for this run.
* `--keep-folders-off`: File the documents inside inbox folders one by one for this run, and remove each folder once it is empty, whatever the library&#x27;s keep_folders setting says.
* `--use-ai`: Fall back to the AI named in the library&#x27;s config (Ollama unless it says otherwise) for classifications the rules engine can&#x27;t resolve.
* `--dry-run`: Preview what would be filed and what would need review, without moving or recording anything. Classification, including any --use-ai calls, runs as usual.
* `-v, --verbose`: Also show progress messages on screen, and record debugging detail in the log file.
* `-q, --quiet`: Show errors only on screen. Wins over --verbose.
* `--help`: Show this message and exit.

## `microfiche review`

Decide where the documents `sort` left in the inbox should go.

For each one you can accept the best guess, pick a group and category (or plan a new folder), skip it, or quit.
Nothing is moved while you answer. At the end you see what you chose and confirm once; the chosen documents are
then filed as one job, which `rollback` can undo. Documents you skip stay in the inbox, and so do copies of
documents already in the library. Needs a terminal.

**Usage**:

```console
$ microfiche review [OPTIONS]
```

**Options**:

* `--library <directory>`: Path to the library root.  [required]
* `--use-ai`: Ask the AI named in the library&#x27;s config for a best guess where the rules have none, as `sort` does.
* `-v, --verbose`: Also show progress messages on screen, and record debugging detail in the log file.
* `-q, --quiet`: Show errors only on screen. Wins over --verbose.
* `--help`: Show this message and exit.

## `microfiche propose-categories`

Suggest new category folder names from common terms across documents in the sorting inbox.

Never creates folders - this only prints suggestions. Scoping to an existing library folder
instead of the inbox isn&#x27;t implemented yet.

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

Re-review already-filed documents and report where the classifier would file them now.

Without --apply this is a dry run. With --apply, the documents the table marks &quot;move&quot; are
re-filed as one job (undo it with `rollback`); the rest are left exactly where they are.

**Usage**:

```console
$ microfiche reclassify [OPTIONS]
```

**Options**:

* `--library <directory>`: Path to the library root.  [required]
* `--folder <path>`: Limit to this folder; defaults to the whole library.
* `--apply`: Actually move files; without this it&#x27;s a dry run.
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
* `-v, --verbose`: Also show progress messages on screen, and record debugging detail in the log file.
* `-q, --quiet`: Show errors only on screen. Wins over --verbose.
* `--help`: Show this message and exit.

## `microfiche rollback`

Undo a filing job by id (the id `sort` prints).

**Usage**:

```console
$ microfiche rollback [OPTIONS]
```

**Options**:

* `--library <directory>`: Path to the library root.  [required]
* `--job-id <str>`: [required]
* `-v, --verbose`: Also show progress messages on screen, and record debugging detail in the log file.
* `-q, --quiet`: Show errors only on screen. Wins over --verbose.
* `--help`: Show this message and exit.

## `microfiche config`

Show the library configuration, or with --sync bring its library file in step with its folders.

--sync adds an entry, with no hints, to .microfiche/microfiche-library.json for each group and category folder
that has none, creating the file if the library has none. It never changes or removes an entry, and never
creates or removes a folder. An entry whose folder is gone is listed each time, and kept.

**Usage**:

```console
$ microfiche config [OPTIONS]
```

**Options**:

* `--library <directory>`: Path to the library root.  [required]
* `--sync`: Instead of showing the configuration, add an entry to the library file for every folder that has none, and list entries whose folder is gone.
* `-v, --verbose`: Also show progress messages on screen, and record debugging detail in the log file.
* `-q, --quiet`: Show errors only on screen. Wins over --verbose.
* `--help`: Show this message and exit.
