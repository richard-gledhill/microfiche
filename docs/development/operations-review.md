# Operations review

A review of the code against what well-run command-line file organisers usually have: robustness, safety
and diagnostics, as opposed to features. It is scheduled as Stages 4.2 to 4.4 of the
[build plan](mvp-build-plan.md), with a few items in Stage 6; what is postponed is listed in
[mvp-roadmap.md](mvp-roadmap.md#deferred-beyond-mvp). Nothing here is built yet. The configuration side of
the same exercise is in [config-review.md](config-review.md).

## Gaps worth fixing in the MVP

| # | Gap | What the code does today | Where it goes |
|---|---|---|---|
| 1 | Name collisions crash `sort` | `file_batch` raises `FileExistsError` part-way through a batch. `commands.sort` doesn't catch it, so the user gets a traceback and a half-finished job. `reclassify` already has a `conflict` action; `sort` has no equivalent. | Stage 4.2 |
| 2 | One failure aborts the run | Ollama not running raises an uncaught exception during classification. A permission or "file in use" error (common on Windows with Obsidian or Word open) does the same during filing. | Stage 4.3 |
| 3 | `sort` has no preview | `reclassify` is a dry run by default, but `sort` moves files straight away. Classification already happens before filing, so `--dry-run` is cheap. | Stage 4.3 |
| 4 | No concurrency guard | Two `sort` runs, or a sync tool running during one, could interleave ledger and audit appends. A `.microfiche/lock` file holding a process id would prevent it. | Stage 4.3 |
| 5 | Symlink policy | The scanner uses `rglob` and `is_file()`, which follow links. A symlink or junction in the inbox that points outside the library would be read and hashed. | Stage 4.3 |
| 6 | Inbox ignore patterns | Office lock files such as `~$report.docx` match the `.docx` check and land in review as "unreadable". `.DS_Store` and `Thumbs.db` are similar. A `[sorting] ignore` setting fixes this. | Stage 4.3 |
| 7 | Size limits | Parsers read whole files, so a 2,000-page PDF is fully parsed. A `[parsing] max_file_mb` limit that sends oversize files to review caps it. | Stage 4.3 |
| 8 | No logging | `core/utils/logging.py::get_logger` is unused and writes `organization.log` outside the `.microfiche/` convention. There is no `--verbose` or `--quiet`, and nothing to read afterwards when a unit lands in review. | Stage 4.4 |
| 9 | Privacy of the OpenAI provider | `OpenAIProvider` sends document text off the machine, while the design says classification stays offline. The provider must be chosen explicitly, the run must say so, and the key comes from an environment variable. | Stage 4.1 (`[ai]`) |
| 10 | Release and CI gaps | The release workflow only builds the docs, so there is no wheel build or install test although Stage 6 promises "installable from a tagged release". `core` and `cli` are separate packages, so `cli` alone won't install. CI runs on Ubuntu only. | Stage 6 |
| 11 | CLI polish | No `--version`, no `rollback --last` (the job id has to be copied from `audit`), no progress feedback on long runs, and no documented exit codes. | Stage 4.4 (progress), Stage 6 (the rest) |

## Decisions

- **Collision policy:** a unit whose destination is taken stays in the inbox for review, with the reason.
  Nothing is renamed, suffixed or overwritten, which matches `reclassify`'s `conflict`. Renaming on collision
  is deferred.
- **Duplicate policy:** an inbox file whose content matches a file already in the library, or one filed earlier in
  the same run, is classified as usual and then held in the inbox with the reason, which names the existing copy
  and, if the classifier would file it elsewhere, where. Only new files are checked: duplicates already inside the
  library are normal in a project (reference documents) and are never reported, so there is no setting. Moving
  duplicates into a `_sorting/duplicates/` folder is deferred.
- **Audit log versus diagnostic log:** `audit.log` and the ledger are product data that `rollback` reads and
  must stay stable. The diagnostic log is for people and can change. `core` uses the standard `logging` module
  and installs no handlers; only the CLI configures them.
- **A failure belongs to a unit unless it belongs to the run:** a bad file, a locked file, a symlink or an
  oversize file sends that unit to review with a reason. A held lock stops the run with exit code 1.
- **Order of the 4.x stages:** 4.1 first because the others add settings; 4.2 before 4.3 because turning
  `keep_folders` off makes collisions common; 4.4 last because it records what the others do, but it is small
  enough to move earlier if debugging needs it.

## Deferred beyond the MVP

Listed in the roadmap with the rest of the deferred work: OCR for scanned PDFs,
a `doctor`/`verify` command, watch mode, `--json` output, ledger and `audit.log` rotation, dependency and
security scanning, and a statement that there is no telemetry.
