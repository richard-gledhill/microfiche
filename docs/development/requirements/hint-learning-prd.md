# Learn keyword hints from review choices

Status: Draft

- **Id:** `hint-learning` ([capability map](post-mvp-capability-map.md), #3)
- **Depends on:** `matching-precision` (learned hints are matched on word boundaries, and a learned hint that clashes
  with another category is held by the ambiguity margin rather than misfiling)

## Why

The review queue is where the user's time goes. Today a document filed by hand in `review` teaches microfiche nothing,
so the same kinds of document come back to the queue every run. Hints are the cheapest way to improve the rules, but
users have to know which words to add and remember to add them. The ledger already records what the user decided, so
microfiche can learn the hints itself, without asking.

## User stories

- As a user who works the review queue, I want microfiche to learn from what I filed, so fewer documents need me next
  time, without extra steps.
- As a user, I want to see what it learned, tell learned hints apart from mine, and remove one that goes wrong.

## Requirements

**Must**
- After a `review` commit, update `microfiche-library.json` automatically, with no prompt: for each category the user
  filed into, add words that are frequent in the documents the user filed there and rare in the library's other
  categories, and that are not already hints or the category's name.
- Learn only from documents recorded with `classified_by = "user"`.
- Guardrails, so one unusual document cannot teach a bad hint:
  - a minimum number of user decisions for a category before anything is learned for it;
  - a word is not learned if it also appears in documents filed under another category of the same group;
  - a cap on how many hints a category can learn in one run;
  - common words (a stop list) and very short words are never learned.
- Learned hints are kept apart from the user's own (for example a `learned_hints` list on the entry), so they are never
  mixed with, reordered among or overwrite what the user wrote. They match like hints, at the hint confidence.
- Say what was learned: the `review` summary lists each hint added and its category, and the diagnostic log records
  it. No document text beyond the hint words is written anywhere.
- Learned hints can be removed by deleting them from the library file, and a removed hint is not learned again (it is
  remembered as rejected).
- Writes go through the same atomic write as `library_sync`, under the run lock already held by the commit. A failed
  write is a warning, never a failed commit.
- The library file's JSON Schema is regenerated (`make library-schema`) for the new field.

**Should**
- Learn from `reclassify --apply` choices as well, when those come from the user.
- Report, in the `sort` summary, how many documents were filed by a learned hint, so the user can see whether learning
  is paying off.

**Optional, parked**
- Prompting before a learned hint is added (an opt-in setting such as `[learning] confirm = true`). Parked until the
  automatic behaviour has been used on a real library.
- A command to list or reset learned hints.

**Won't (this time)**
- Training a classifier on the ledger ([mvp-roadmap.md](mvp-roadmap.md#deferred-beyond-mvp)). This is term frequency,
  not a model.
- Learning group names or new categories. Folders stay the only source of the taxonomy.

## Acceptance criteria

- On a library where the user filed five invoices into `Bills` through `review`, a distinctive word common to them is
  added to `Bills`' learned hints after the commit, with no prompt, and the summary says so.
- A word that also appears in a sibling category's filed documents is not learned.
- Below the minimum number of decisions, nothing is learned.
- The next `sort --dry-run` files a matching document under `Bills` at hint confidence.
- The user's own hints, rules and entry order are byte-identical after learning.
- A learned hint the user deleted is not added again.
- The calibration report is unchanged (the corpus has no review decisions), and a new calibration case shows the effect
  of learning on a held-out set.
- `make check` and `make test` pass; `docs/how-to-use.md` and the README describe learning and how to undo a hint.

## Technical outline

Guidance for the spec, not binding.

- Reuse `library/category_suggester.py`'s term-frequency logic, scoped to filed documents per category instead of the
  inbox, and scored contrastively (the category against its siblings).
- Read the documents through `read_documents`, from the paths `Ledger.current()` gives, filtered by `classified_by`.
- Run it at the end of `ReviewSession.commit`, after `file_batch` succeeds. Rejected hints can be stored in the state
  folder (not the library file) so the library file stays clean.
- The new library file field needs `library_file.py`'s model, `hints_for` (to include learned hints after the user's),
  and the schema test.

## Related

- [mvp-roadmap.md](mvp-roadmap.md#review-stage-5): "it does not learn from choices".
- [mvp-followups-prd.md](mvp-followups-prd.md) D21 (learning hints from `review` choices).

## Open questions

- The thresholds: minimum decisions, cap per run, minimum word length. Choose them on a held-out split of the
  calibration corpus.
- Should learned hints be undone by `rollback` of the review job that taught them? Rollback today only moves files.
