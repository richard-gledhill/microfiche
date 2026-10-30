# ADR-008: Learn keyword hints from review choices

- **Status:** Accepted
- **Date:** 2026-10-30
- **Decision:** After a `review` commit, microfiche may add contrastive keyword hints to the library file's
  `learned_hints`, from the documents the user filed. It is opt-in (`[learning] enabled`, default off). Learned hints are
  kept apart from the user's own, a deleted one is remembered through the ledger, and `rollback` does not remove them.
  See [Decisions](#decisions).
- **Source:** [hint-learning-prd.md](../requirements/hint-learning-prd.md)

## Context

A document filed by hand in `review` teaches microfiche nothing, so the same kinds of document return to the queue each
run. The ledger already records what the user decided (`classified_by = "user"`), so hints can be learned from it
without asking. The library file is the user's, so writing to it needs guardrails and a way out.

## Decisions

- **Opt-in:** `[learning] enabled = false` by default. Nothing is written to the library file unless the user turns it on.
  Revisit the default after it has been used on a real library; a prompt-before-adding mode stays parked.
- **Source of evidence:** only documents recorded with `classified_by = "user"`, read from the paths
  `Ledger.current()` gives. `reclassify --apply` does not teach: it applies the rules' own output, so learning from it
  would reinforce the rules' guesses.
- **Where it lives:** a `learned_hints` list on a library-file entry, after and apart from the user's `hints`; matched like
  hints at the hint confidence, on word boundaries. The user's hints, rules and entry order are never touched.
- **Guardrails:** a minimum number of user decisions per category, a cap on hints learned per category per run, common and
  very short words never learned, and a word is not learned if it also appears in documents filed under another category
  of the same group. The numbers are chosen on a held-out split of the calibration corpus (simulated review decisions)
  and recorded in `calibration.md`; the minimum word length starts at 4.
- **Deleting a learned hint sticks.** Each learning pass appends a `hint_learned` event to the ledger. A hint that event
  names and that is no longer in the library file is rejected: it is not learned again. No new file and no extra field.
  The cost of the alternative (no memory) is that a deleted hint returns after the next review commit into that category
  while its evidence stands.
- **Rollback does not undo learning.** It stays about files. The review summary and the log name each hint added, and a
  hint is one deletion away.
- **Reporting:** the `review` summary lists each hint added and its category; the diagnostic log records it; `sort`
  prints how many documents were filed by a learned hint. No document text beyond the hint words is written anywhere.
- **Failure:** the write is atomic (as in `library_sync`), under the run lock the commit already holds. A failed write
  is a warning, never a failed commit.

## Alternatives considered

- Always on, as the PRD reads: the first `review` commit would rewrite the user's file unasked.
- A `rejected_hints` field the user fills in: visible, but plain deletion would not stick and the user must know to use it.
- A separate state-folder record of learned hints: the ledger already exists and is append-only.
- Learning from `reclassify`: the rules teaching themselves.

## Consequences

- The ledger gains an event type (`hint_learned`), documented in `data-model.md`; `Ledger.current()` is unaffected.
- The library file model gains `learned_hints` and the JSON Schema is regenerated.
- A new `[learning]` config section to document: packaged defaults, example config, how-to-use, README.
