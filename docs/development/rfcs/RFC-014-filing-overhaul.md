# RFC-014: Automatic filing overhaul

Status: Draft

**Background:** raised from manual use of a real library, where automatic filing files little or the wrong things. It was
first written together with two smaller requests, now split out: [RFC-015](RFC-015-init-prune-library-file.md) (`init`
pruning stale library-file entries) and [RFC-016](RFC-016-multi-level-filing.md) (multi-level filing). The three touch the
same pipeline but can ship independently.
Related: [RFC-004](RFC-004-filing-target-mode.md) (filing target mode), [RFC-005](RFC-005-decision-model-classifier.md)
(decision-model classifier), [RFC-006](RFC-006-subcategories-depth-3.md) (depth 3),
[RFC-013](RFC-013-manual-review-findings.md) (manual review findings, incl. depth-2 group filing and ambiguity).

## Automatic filing needs an overhaul

**Symptom.** Automatic filing is not working well enough to rely on: too many documents go to `review`, or are filed
under the wrong group or category.

### a. First, rule out a parsing fault

Before changing strategy, check that the folder names reach the matchers intact. This is a bug hunt, not a design
choice, and it is cheap:

- Does `Library.taxonomy()` return the names as the folders are written (numeric prefixes like `01 Requirements`,
  `&`, `-`/`_`, camelCase, trailing spaces, Unicode)? [RFC-010](archive/RFC-010-folder-name-matching.md) added
  `normalise_names`; confirm it applies on both the folder side and the text side, in `match_group`, `match_category`
  and the hints.
- Are `[exclusions]` or `init` leaving stale or wrong entries in `microfiche-library.json` that shadow the real folders
  (see [RFC-015](RFC-015-init-prune-library-file.md))?
- Does `sort --dry-run` on the real library show a reason string per unit that names the folder it matched? Record a
  handful of misses and misfiles as the evidence for b.
- Extend `tests/calibration/` with documents from the real library (anonymised) so the numbers below are measured, not
  guessed.

**Deliverable of (a):** either a bug fix or a short finding saying names are parsed correctly, so the problem is the
strategy.

### b. Strategies to evaluate

Each is judged on the calibration harness: auto-filed share against misfile rate at the default threshold, and cost
(dependencies, speed, explainability, offline use).

| Strategy | Idea | Notes |
|---|---|---|
| **Prioritise filename and document title** | Score the filename and the extracted title (first heading, PDF/DOCX title metadata, email subject) separately and weight them above body text. | Today the text is lumped, so a long body full of incidental words drowns a clear title. Cheap, explainable, no new dependency. Likely the first thing to try. |
| **Per-field scoring** | Generalise the above: filename, title, headings, body and metadata each give a score; the combined confidence is a weighted sum with weights in config. | Keeps `combine_confidence` (min across stages) between stages; changes only how one stage scores. |
| **Keyword association attached to categories and groups** | Learn or curate weighted terms per group and category (from the documents already filed, via the ledger), beyond the hand-written `hints`. | Extends `microfiche-library.json`; could be proposed by `propose-categories`-style term frequency. Needs a review step so the user owns the terms. |
| **Light machine learning** | TF-IDF plus a linear classifier (or nearest-centroid / embeddings) trained per library on already-filed documents. | Uses the user's own filing as labels, so it adapts to the library. Needs enough filed examples per category, a retrain trigger, and a dependency (e.g. scikit-learn) behind an extra. Weak on small or new categories. |
| **Multi-level sorting** | Decide the group, then the category within it, each with its own evidence and threshold, rather than one combined score (see [RFC-016](RFC-016-multi-level-filing.md)). | Largely how the classifier already works; the gap is per-level thresholds and stopping at the deepest confident level. |
| **Path and sibling context** | Use where related documents already live: same sender, same project number, near-duplicate content, files dropped together in one folder unit. | The ledger already records filings; "files like this one" is strong evidence for a library with history. |
| **Entity and identifier extraction** | Pull project codes, client names, invoice or reference numbers, dates and match them to folder names. | High precision for business documents; needs patterns per library, probably config. |
| **Better use of the AI fallback** | Give the LLM the taxonomy plus filed examples per category (few-shot) and the title/filename as separate fields; ask it to explain. | Overlaps RFC-005. Costs calls and privacy considerations; keep it a fallback. |
| **Active learning from `review`** | Treat each `review` decision as a training example (it is already recorded with `classified_by = "user"`), so the same mistake is not repeated. | Ties the strategies together: whatever scores, `review` feeds it. |
| **Confidence calibration** | Recalibrate thresholds per strategy and per level from measurements, instead of one global 0.75. | Prerequisite for mixing strategies fairly. |

### c. Proposed approach (to be agreed)

1. Do a and record the finding.
2. Do the research step in e.
3. Prototype title/filename priority and per-field scoring first (cheapest, no dependency); measure on the calibration
   corpus plus real-library samples.
4. Only if that is not enough, prototype learned keyword weights from the ledger, then the ML option behind an optional
   extra. Keep the rules-first, explainable shape: every filing still records a reason.
4. Whatever is chosen keeps the invariants: nothing is filed into an invented folder, nothing is deleted, every move is
   in the ledger and rollback-able, and a confident rules answer is not overridden without cause.

### d. Open questions

- What is the target: auto-filed share at what misfile rate? (The gate for any strategy.)
- Is training on the user's filed documents acceptable (local only, stored where, how it is reset)?
- Is a new dependency (scikit-learn, or an embedding model) allowed in `core`, or only behind an extra like `ai`?
- Should the strategy be selectable (`[classification] strategy = ...`) or one best pipeline?
- What else belongs here? Candidates not yet covered: OCR text quality (RFC-008), language handling, stop-word and
  boilerplate stripping (letterheads, footers, disclaimers that appear in every document).

### e. Research step: similar products, approaches and NLP libraries

A time-boxed, high-level survey before any strategy is built, so this RFC is chosen from what already works rather
than invented. It produces a short findings note (see the deliverable below), not code. Everything named here is a
starting point to verify at the time, not a claim about what the products or libraries do.

**Products to review** (how they decide where a document goes, and how much the user must teach them):

| Product | Why it is on the list |
|---|---|
| TechHit SimplyFile | Email filing that learns from the user's own filing: the closest model to "train on what is already filed". |
| Paperless-ngx | Document management with automatic matching of tags, correspondents and document types, including a learned (classifier) mode. |
| Docspell | Document organiser with its own text analysis and suggestions for correspondents and tags. |
| Papra | Newer document archive; check whether it files or tags automatically at all. |
| File Juggler (filejuggler.com) | Rule-based filing of loose files; a reference for what rules users write and how they are expressed. |

Add others found along the way (for example other inbox-filing tools, email clients' learned filters, and
enterprise "auto-classification" features), but stop at the time box.

**Questions to answer for each product:**
- What signals does it use: filename, title, body, metadata, sender, folder history?
- Rules, learned model, or both; if learned, what algorithm, what training data, and how many examples before it is useful?
- What happens on low confidence: ask, suggest, or file anyway? (Compare with `review`.)
- How does the user correct it, and does the correction feed back?
- Where does it run (offline, local, cloud), and what does it need installed?
- Is it explainable: can the user see why a document was filed there?
- What does it get wrong, as reported by its users?

**NLP and machine learning libraries to assess:** spaCy, gensim, Pattern, polyglot, scikit-learn, NLTK, Stanza.
Judge each on the same sheet:

| Criterion | What to record |
|---|---|
| Fit | Which job it does for us: text cleaning and tokenising, keyword extraction, similarity, classification, or entity extraction. Several of these are toolkits, not classifiers. |
| Size and install | Wheel and model size, Python 3.11 to 3.14 support, Windows and Linux wheels, native or GPU dependencies. |
| Offline and licence | Works with no network after install; licence compatible with the project; model licences too. |
| Languages | English only, or multilingual; matters for a library with mixed-language documents. |
| Maintenance | Release activity and open-issue health, and whether it supports current Python. |
| Fit with the layout | Can it sit behind an optional extra like `ai`, keeping `core`'s base install small and `core` free of heavy imports? |
| Small-data behaviour | Does it work with a few examples per category, as a new library will have? |

Worth checking early, because they may remove options: a library that is unmaintained or lacks current Python or
Windows wheels, and whether scikit-learn (TF-IDF plus a linear model or nearest-centroid) already covers the need
without a heavier toolkit. Also consider approaches outside the list, such as plain TF-IDF with no library, BM25 and
embedding models, noting any that need a model download.

**Deliverable:** a findings note (an appendix here or `docs/development/architecture/` once it is more than a page)
with one row per product and per library, a shortlist of at most two approaches, and a recommendation on whether
machine learning is worth its dependency and complexity for the first release. Every external claim carries its source
and the date it was read.

**Gate:** the shortlist is only prototyped under c if the research finds an approach that works offline, runs behind
an optional extra, and is plausible with the amount of filed data a typical library has.

**Comparative analysis against the current microfiche algorithm.** The research ends by setting what it found against
what microfiche does today, so the recommendation is a measured difference, not a preference. The baseline, from the
code and [AGENTS.md](../../../AGENTS.md):

- Two stages, group then category within the group, each proposed by resolvers: rules first, then an optional AI
  fallback only when the rules' answer is missing or below the threshold.
- Group: whole-word and fuzzy match (`rapidfuzz`) of the group name against the document text. Category: filename-glob
  rules first, then the category's name and keyword hints from `microfiche-library.json`, scoped to the resolved
  group's existing folders.
- Fixed confidences per kind of match (name 0.9, filename rule 0.95, hint 0.75), combined by the minimum across stages,
  with an ambiguity margin that sends near-ties to review and one global threshold (0.75).
- Text is matched as one lump; there is no weighting of filename or title over body, and nothing is learned from past
  filings or `review` decisions. The taxonomy is the folder tree, and hints are written by hand.
- Every result carries a reason, nothing is filed into an invented folder, and every move is in the ledger.

Compare each shortlisted approach, and the best of the products reviewed, with that baseline on:

| Dimension | Baseline (today) | What to record for each alternative |
|---|---|---|
| Accuracy | Auto-filed share and misfile rate on the calibration corpus and real-library samples at 0.75 | The same two numbers on the same documents, at the same misfile rate |
| Cold start | Works on a new library with no filed documents (names and hints only) | Examples needed per category before it beats the baseline |
| Adaptation | Manual: the user edits hints | Learns from the ledger and `review` decisions, and how fast |
| Explainability | A reason string naming the match | Can it say why, in a form a user can act on |
| Failure mode | Sends unsure documents to review | Does it file confidently and wrongly, and how is that caught |
| Cost | No dependency beyond `rapidfuzz`; fast, offline | Install size, speed per document, training time, memory |
| Privacy and offline | Local; AI fallback is the only external call, and optional | Anything that leaves the machine or needs a download |
| Fit with the design | The folder tree is the taxonomy; resolvers propose, the classifier decides | Can it be one more resolver behind the seam, or does it change the model |
| Maintenance | Rules and hints are easy to read and change | Retraining, model files and versioning, and what a user does when it is wrong |

The comparison should also say which baseline weaknesses each alternative addresses (lumped text, hand-written hints,
no learning, a single global threshold) and which it leaves alone, and whether a hybrid is better than a replacement:
keep the rules for exact and filename matches, and add the new signal only where the rules are unsure. State plainly
if the finding is that the current algorithm is good enough once filename and title are weighted (b), in which case
the machine learning work is deferred to [feature-backlog.md](feature-backlog.md).

## Next steps

1. Run the parsing check (a) on the real library and report.
2. Do the research step (e) in parallel, time-boxed, and record the findings.
3. Agree the measurement gate, then prototype in the order in (c).
4. Record the decisions as ADRs and link them to this RFC.
