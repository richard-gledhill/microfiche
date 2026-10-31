# RFC-013: Manual review findings, and a test on a real library

Status: Draft

**Background:** raised on 2026-10-31 from a manual review of `init`, `propose-categories` and `sort` on a real library.
Eight findings. Each was checked by reading the code (not yet run); the real-library test below is what confirms or
refutes them. Nothing built.

## Findings

### 1. `init` does not re-check folders against changed `[exclusions]`

Reported: after `[exclusions]` in `microfiche-config.toml` is edited by hand, `init` leaves the entries for the
newly excluded folders in `microfiche-library.json`.

Read from `library/library_sync.py`: confirmed by design, not by accident. `sync_library_file` is additive only. It
appends an entry for each folder with no entry, never changes or removes one, and an entry whose folder still exists
is not reported missing, with the comment "an excluded folder is still there". So a stale entry for an excluded folder
stays and is never mentioned. The reverse also happens: removing a pattern from `exclude` adds the folder as a new
category with no hint that the exclusion change caused it.

What is not known: whether a stale entry has any effect. `Library.taxonomy()` is built from the folders, so probably
none on filing; it may still carry hints into matching, and it misleads anyone reading the file.

Options: (a) report entries whose folder is now excluded, as `missing` does, and change nothing; (b) offer to remove
them; (c) leave as is and document. (a) matches "never changes an entry the user wrote". Also settle whether `init`
should print what an exclusion change added or orphaned.

### 2. `propose-categories` proposes common words

Reported: `through`, `which`, `how`, `can`, `time`, `also`, `then`.

Read from `library/category_suggester.py`: the stopword list is 24 words (articles, `is`, `with`...). It has no
pronouns, modals, question words or adverbs, so any ordinary English word that appears in many documents wins. Scoring
is document frequency, so the most common word in English prose ranks first. Words are also single tokens, so a
category such as `Home Insurance` can never be proposed.

Options: a fuller stopword list; weight by how rare the word is across the library (tf-idf, so a word every document
has scores low); keep only nouns (needs a part-of-speech tagger, a new dependency, against the lean install);
propose from capitalised or repeated phrases and filenames. The measurable fix is tf-idf against the library's own
filed documents plus a larger stopword list, checked on the calibration corpus.

### 3. Does it scan the files already in Groups and Categories?

No. `propose_categories` takes the units from `scan_sorting_inbox` only, and `suggest_categories` receives just those
documents. It builds no keyword list from filed documents, and does not look at existing category names, so it can
propose a name that already exists. This is the "scoping to an existing library folder isn't implemented" gap in
`mvp-roadmap.md`.

Decision needed: should the filed documents be the *background* (so a term is distinctive if the inbox has it and the
library does not), the *scope* (propose subfolders for one crowded category), or both? And it should drop any proposal
that matches an existing folder under `normalise_for_matching`.

### 4. No `--use-ai` on `propose-categories`

Confirmed: the command has `--library`, `--verbose` and `--quiet` only. `overview.md` §6 designs an AI variant that is
not built. It needs the pre-run AI check and failure tips from
[ADR-004](../adr/ADR-004-ai-provider-setup.md), and the same fall-back rule as `sort`: AI unavailable means the
deterministic list, with a notice.

### 5. The output is not meaningful

Confirmed: it prints `Word (score=7) — e.g. a.md, b.md`. The score is the number of documents containing the word,
which the output does not say, and with no total the number cannot be judged (7 of 8 or 7 of 400?). Change to
`Word: in 7 of 12 documents`, show the group it would go in, and say what to do next (create the folder, run `sort`).
The `score` field could then be a count and a total.

### 6. `sort` at depth 2 and a group with no suitable category

Reported: a document that fits a group but no category is not filed into the group. A proposed category name should
accompany it.

Partly built. [RFC-011](RFC-011-groups-without-categories.md) / [ADR-007](../adr/ADR-007-leaf-groups.md) added
`[sorting] file_in_empty_groups` (default **off**), which files into a group that has **no** category folders at all.
So a reviewer on defaults sees the old behaviour. Two cases are open:

- A group with **no** categories and the setting off. Question: turn the default on? ADR-007 said "measure first", and
  the calibration corpus has no empty group yet.
- A group **with** categories, none of them matching. This is [RFC-004](RFC-004-filing-target-mode.md)
  (`file_at = best_level`), still Draft, and its concern about a repeated category name (`01 Requirements`) applies.

New in this RFC: attach a category proposal (finding 2) to the review entry, so `review` can offer "file in the group,
or create folder X". This needs a threshold below which the group match alone is not enough to file.

### 7. HTML files with asset folders

Not handled, and not reported. There is no HTML parser (`parsers/` has docx, eml, msg, pdf, md, txt). In the scanner:

- A loose `page.html` is unsupported, so `scan_sorting_inbox` drops it with no message. It sits in the inbox and is
  never in `needs_review`, so the user cannot see why it was skipped.
- A browser "Save page as" makes `page.html` plus `page_files/`. With `keep_folders` on, the folder is one unit if it
  holds any supported file (a `.txt` or `.pdf` asset), is dropped silently if it holds none, and the `.html` is never
  filed with it. With `keep_folders` off, the supported assets are filed alone and the page is left behind.

Options: (a) report unsupported files as skipped, with the reason, so nothing is silent (cheap, and wanted whichever
other option is chosen); (b) an HTML parser that extracts visible text, and treat `name.html` + `name_files/` (also
`name.htm`, `name_fichiers`...) as one unit; (c) leave HTML out and document it. (a) is the minimum.

### 8. Too many "Several groups match about equally well"

Read from `rules/group_rules.py` and `rules/ambiguity.py`: any two candidates within `ambiguity_margin` (0.1) of the
best hold the document. Exact names settle it (1.0), but fuzzy matches score 0.85 to 0.99, so a document naming
nothing exactly and fuzzily matching two similarly named groups (`Project Alpha`, `Project Albert`) is held. The 0.1
margin was measured on the calibration corpus ("misfires 24 → 6"), which is small and tidy; `mvp-roadmap.md` notes it
is "still unmeasured on long documents". Long documents contain many words, so more fuzzy hits and more near-ties.

Hypotheses to test on the real library: long documents; groups with shared words in their names; a fuzzy threshold
(85) that is too low; ties among candidates that all matched the same sentence.

Options: a smaller margin, a margin that scales with the candidates' confidence, match on the title/first page before
the body, or break ties with the AI fallback when `--use-ai` is on. Do not choose without numbers.

## Real-library test

**Confidentiality.** The user's library may be confidential. The test is run only locally, by the user or by an agent
the user has given access to a folder. No library information goes into the repository or its docs: no folder, group,
category or file names, no document text or excerpts, no paths, and no counts that identify it. Findings are recorded in
the repo only in general terms ("long documents produced more near-ties"), and anything specific stays in the user's own
notes or in `.temp/` (gitignored), which is not committed. Results that need a regression test are reproduced with
synthetic documents (see the next section), never copied from the library.

**Where it runs.** The user defines the folder and gives access to it for the session; this RFC does not name one. Work
on a copy, never the original: the project never deletes, but `sort` moves files.

1. **Copy** the library to a scratch folder; `init` and `sort` run only there. Use `sort --dry-run` first (no job, no
   ledger, no lock).
2. **Baseline** counts for `sort --dry-run`: units, filed, `needs_review`, duplicates, and the reasons grouped (how many
   are "Several groups match", "No ... matched", collisions, unreadable).
3. **Finding 8:** for every ambiguous result, record the candidates, their confidences, the document length, and whether
   a human would pick one. Then re-run at margins 0.0, 0.05, 0.1 and a higher fuzzy threshold and compare.
4. **Finding 1:** edit `[exclusions]` in the copy, run `init`, diff `microfiche-library.json`.
5. **Findings 2 to 5:** run `propose-categories`, list the proposals and mark each a real category or not; repeat after a
   candidate fix.
6. **Finding 6:** put documents for a group with no folders and for a group with unsuitable categories in the inbox;
   record what `sort --dry-run` and `review` do, with `file_in_empty_groups` on and off.
7. **Finding 7:** put a saved web page (`.html` + folder), a loose `.html` and a folder of only images in the inbox;
   record what `sort --dry-run` says about each.
8. **Rollback:** a real `sort` on the copy, then `rollback`, and check the tree is identical to the copy.
9. Keep the results local. Only general conclusions and decisions come back to the repo.

## Optional: a synthetic test library

A library built from a public subject domain, so the tests can be repeated without using the confidential one. It is
also local only: it is built and kept outside the repo or in `.temp/` (gitignored), and neither the library, its
documents, its manifest nor any download script is committed. Proposal, not decided:

- Pick one domain with natural groups and categories at depth 2 (for example, a software project, a household, or a
  public-sector topic), including a group with no categories, a group whose categories are all unsuitable for some
  documents, similarly named groups (to provoke finding 8), and a tool-made folder such as `attachments`.
- Fill it with documents downloaded from the web in the supported formats (`.pdf`, `.md`, `.txt`, `.docx`, `.eml`), plus
  a saved web page with its asset folder for finding 7. Include a few long documents.
- Keep a local manifest of each source URL and licence, and use only public-domain or openly licensed material.
- Questions to settle: size, and whether any of it is later rebuilt as small hand-written fixtures for
  `tests/` (those would be written fresh, not copied from the downloads).
- Downloading is a step the user approves, with the sources and sizes listed first.

## Order of work, if accepted

1. Finding 7(a) and finding 1(a): small, report-only, no design risk.
2. Finding 5 and 2 (wording and stopwords, then tf-idf), with the real-library list as the measure.
3. Finding 8, only after step 3 of the test gives numbers.
4. Findings 3, 4 and 6 need decisions first and are probably separate RFCs or ADRs once the questions are answered.

## Docs it would need

`how-to-use.md` (both tabs, Current limitations), `README.md` usage, `cli-reference.md` (`make docs-cli`),
`mvp-roadmap.md`, `calibration.md` if the margin or threshold changes, and `overview.md` §6 for the suggester.
