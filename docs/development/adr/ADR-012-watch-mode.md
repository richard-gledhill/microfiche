# ADR-012: Watch mode polls the inbox and files what has stopped changing

- **Status:** Accepted
- **Date:** 2026-10-31
- **Decision:** `microfiche watch` rescans the inbox every `[watch] interval_seconds` (default 3600), files the units that
  were unchanged between two scans in one batch, and waits for the run lock for up to `[watch] lock_timeout_seconds` before
  skipping the batch to the next cycle. No file-system event library. See [Decisions](#decisions).
- **Source:** [watch-mode-prd.md](../requirements/watch-mode-prd.md)

## Context

Filing only happens when the user remembers to run `sort`. Watch mode removes that step, which is acceptable only now that
confident misfiles are rare, the rules learn, results can be read by scripts and drift is noticed. The
[watchdog review](../architecture/watchdog-review.md) found events useful only as a trigger, since a rescan and a stability
check are needed either way.

## Decisions

- **Polling, no dependency.** A scan is a stat-only snapshot of the inbox (name, size, modification time per unit; a folder's
  is the aggregate of its members), never a read of content, so a cloud-synced placeholder is not downloaded by being scanned
  and links are skipped as the scanner does. A late or missed event cannot lose a file because there are no events.
- **Stable means unchanged between two scans.** A unit that is new or changed in this scan is not touched. A batch runs when at
  least one unit is stable *and* the scan itself was quiet (nothing new or changed), so a folder copied in is one job. One
  interval therefore does the work of the PRD's quiet period; there is no separate setting. The move stays a plain rename, which
  fails cleanly on a file that is still open.
- **Settings, with flags.** `[watch] interval_seconds` (default **3600**, an hour: the chosen default for an unattended,
  low-traffic inbox) and `lock_timeout_seconds` (default 30), in the config and in `init`'s walk-through. `--interval` overrides
  the interval for one run. Because stability needs two scans, a unit is filed between one and two intervals after it lands;
  a short `--interval` is for people who want faster filing.
- **Each batch is the normal pipeline** over the stable units: `run_sort` scoped to them, so the threshold, collision and
  duplicate checks, the drift check and the one rollback-able job per batch all apply unchanged.
- **Units held for review are not re-classified every batch.** A held unit is retried when it changes or when the config or
  the library file changes (hints, including learned ones), which is what could change the answer.
- **AI is opt-in: `watch --use-ai`.** The pre-run check runs once at start, the OpenAI notice is printed once, and the
  fallback and `verify_below` apply per batch. A provider failure falls back to rules only for the rest of the run, as in
  `sort`.
- **Lock.** The lock is held only while a batch is filed. `run_lock` gains a `timeout`: it polls until the lock is free or
  the timeout passes. Watch mode skips the batch on a timeout and retries on the next scan; it never exits because the lock
  is busy. `review` and `rollback` run between batches and wait for a batch in progress as they do today.
- **Ctrl-C finishes the current batch.** The handler sets a flag; the loop ends after the batch in progress, so no job is
  left half-filed. A second Ctrl-C during a batch is left to the interpreter.
- **Output.** One summary line per batch (nothing for an idle scan unless `-v`). With `--json`, one compact JSON line per
  batch: the batch's `sort` document (same schema as `sort --json`), and `error` lines for failures.
- **A seam for tests.** The loop takes a clock (`now`, `sleep`) and a scanner, so tests drive scans, stability and batching with
  fakes and never wait.

## Alternatives considered

- `watchdog` events: no "finished writing" event on Windows and dropped events under load, so a rescan is needed anyway.
- A separate quiet period setting: one more number for no more safety than a quiet scan.
- Exiting when the lock is busy: a long `review` session would end an unattended run.
- Always re-classifying held units: pointless work, and the AI costs money per document.

## Consequences

- With the default hour, a document is filed one to two hours after it arrives; users who want it sooner set a shorter
  interval. This is the user's choice of default, recorded here because it changes how "as files arrive" feels.
- `run_sort` needs a way to be scoped to given units, and the scanner a stat-only snapshot.
- Not tested on a OneDrive-synced inbox; that is the PRD's by-hand acceptance check, and is left to the user.
