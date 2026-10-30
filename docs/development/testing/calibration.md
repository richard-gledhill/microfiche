# Calibrating the confidence threshold

How `DEFAULT_CONFIDENCE_THRESHOLD` (`core/rules/confidence.py`) was chosen, what the measurements
showed, and how to repeat them on your own documents. The harness, the labelled corpus and the saved
AI results are in [`tests/calibration/`](../../../tests/calibration/).

## Summary

The default is **0.75**. It was 0.8 until this was measured.

The bullets below are the findings as first measured. The tables further down are current, after word-boundary
matching and the ambiguity margin.

- **The threshold only chooses between kinds of evidence.** The classifier's scores are fixed per kind
  of match, not per document, so there are only a handful of meaningful thresholds: ≤ 0.75 files
  keyword-hint matches, names and filename rules; 0.76–0.9 files names and filename rules; 0.91–0.95
  files only filename rules.
- **Raising it files less; it does not file more accurately.** With 5% tricky documents the share of
  auto-filed documents that are wrong is about 6% at 0.75 and about 6% at 0.8, and about 21% against
  23% at 20% tricky. The old default of 0.8 held back about 43 correct filings per 100 documents to
  avoid about 3 misfiles.
- **The scores measure the *kind* of evidence, not how reliable it is.** On ordinary documents a
  filename rule was right 6 times out of 6, a category name 32 out of 32, and a keyword hint 49 out of
  50. On deliberately tricky documents a category name (0.90) was wrong 11 times out of 11, and a hint
  (0.75) 12 times out of 14. No threshold can separate those, because the confident mistakes score
  *higher* than the cautious right answers.
- **Safer filing needs better matching, not a higher cut-off.** Holding a document when the evidence for
  two groups or categories is within a margin (`ambiguity_margin`) cut misfiles from 24 to 6 on this corpus,
  together with word-boundary matching, for no net loss of correct filings (89 either way; see
  [Ambiguity margin](#ambiguity-margin)).
- **The AI fallback is far more accurate than its score of 0.70** (98% on the one model measured),
  but as built it adds almost nothing: it is only asked when the rules are unsure, never about their
  confident mistakes, and at 0.75 or above its answers never file.

Read these as *relative* findings. The corpus is synthetic, its documents are short, and it was
written by someone who knew how the rules work (see [Limitations](#limitations)). The absolute error
rates say nothing about any real library.

## What the threshold controls

A classification's confidence is the weaker of its group score and its category score. The scores
today:

| Match | Score |
|---|---|
| Group name appears in the text | 1.00 |
| Filename matches a filing rule (category) | 0.95 |
| Category name appears in the text | 0.90 |
| Group fuzzy match (≥ 85 on RapidFuzz's partial ratio) | 0.85–0.99 |
| Category keyword hint appears in the text | 0.75 |
| Answer from the AI fallback (either stage) | 0.70 |

A document is filed automatically when both stages resolved and the confidence reaches the threshold;
otherwise it is left in the inbox for review.

## Method

**Corpus.** 136 documents in five small libraries, each with the `.microfiche` config a user of that
taxonomy would write. A document's truth is where it sits: `<group>/<category>/<file>`, or
`_unfiled/<file>` for a document that belongs to none of the library's groups.

| Library | Taxonomy | Config |
|---|---|---|
| `software-projects` | project › document type | the shipped default config, unchanged |
| `project-stages` | project › stage | the hints the user guide recommends |
| `client-work` | client › document type | user-style hints and a filename rule |
| `study` | course › kind of material | user-style hints |
| `household` | area › topic | short everyday group names (`Car`, `Home`, `Health`) |

Each file is tagged in `kinds.json` with why it was written:

| Kind | Count | What it tests |
|---|---|---|
| `clear` | 31 | names the group, and the category's name appears naturally |
| `hint` | 48 | group named; the category is recognisable only through a configured hint |
| `rule` | 6 | the file name matches a filing rule |
| `fuzzy` | 3 | group name misspelled or reordered |
| `shortform` | 6 | only a short form of the group name is used, so the rules can't see it |
| `nogroup` | 15 | belongs to no existing group |
| `incidental` | 5 | another category's *name* appears in passing |
| `incidental-hint` | 4 | another category's *hint* appears in passing |
| `hintcollision` | 3 | hints of two categories both appear; held for review by the ambiguity margin |
| `crossref` | 9 | another group is mentioned in passing |
| `shortname` | 2 | a short group name appears inside another word (`Car` in `carrier`) |
| `lookalike` | 4 | belongs to no group but resembles one (`Project Atlantic`, `Project Phoenix Rising`) |

The last six kinds (27 documents, 20%) are *adversarial*: they were written to make a name or hint
match the wrong answer. Everything else is *ordinary*, including documents where the right outcome is
to hold the document for review.

**Harness.** `tests/calibration/harness.py` classifies every document with the real pipeline —
`Library`, `read_documents` and `Classifier` with no AI fallback, exactly as `reclassify` does — and
records the answer and its confidence. Rules-only confidence doesn't depend on the threshold, so the
corpus is classified once and any threshold is evaluated against the same results. For each threshold a
document is one of: filed correctly, **misfiled** (filed in the wrong place, including filing a
document that belongs nowhere), held although the suggestion was right, or held with nothing right on
offer.

**AI arm.** `tests/calibration/ai_arm.py` asks a local model the questions `LLMClassifier` asks (group,
then category within that group) for every document, and saves the raw answers to `results/`. The model
was `gemma4:26b` through Ollama with its default settings (it "thinks" before answering, as
`OllamaProvider` allows it to); a call took about 5–10 seconds. The saved answers are replayed through
the real `Classifier` as the fallback so the whole pipeline can be evaluated without the model.

## Results: rules only

At the thresholds that matter (identical results between them):

| Threshold | What files | All 136 | Ordinary 109 | Tricky 27 |
|---|---|---|---|---|
| ≤ 0.75 | rules, names, hints | 95 filed: 89 right, 6 wrong | 87 filed: 86 right, 1 wrong | 8 filed: 3 right, 5 wrong |
| 0.8 – 0.9 | rules, names | 41 filed: 39 right, 2 wrong | 38 filed: 38 right, 0 wrong | 3 filed: 1 right, 2 wrong |
| 0.95 | filename rules only | 6 filed: 6 right | 6 filed: 6 right | none filed |

(Below 0.75 nothing changes for the rules alone, because their lowest score is 0.75. Figures are after word-boundary matching and the ambiguity margin; see [Word boundaries](#word-boundaries) and
[Ambiguity margin](#ambiguity-margin).)

How reliable each kind of evidence was:

| How the answer was found | Score | Ordinary: right / answered | Tricky: right / answered |
|---|---|---|---|
| filename rule | 0.95 | 6 / 6 | — |
| category name | 0.90 | 32 / 32 | 1 / 3 |
| keyword hint | 0.75 | 48 / 49 | 2 / 5 |

(The one ordinary failure is a *fuzzy* group match: a machine-learning lecture that mentions "a database" was
filed under the `Databases` course. "Database" is a whole word, so word boundaries do not stop it.)

**Sensitivity to how many documents are tricky.** The corpus is 20% tricky on purpose; a real library
will differ. Blending the ordinary and tricky outcomes at other shares, per 100 documents:

| Tricky documents | 0.75: right / wrong | 0.8: right / wrong | Break-even for 0.8 |
|---|---|---|---|
| 0% | 78.9 / 0.9 | 34.9 / 0.0 | 48 reviews per misfile |
| 5% | 75.5 / 1.8 | 33.3 / 0.4 | 29.6 |
| 10% | 72.1 / 2.7 | 31.7 / 0.7 | 20.8 |
| 20% | 65.3 / 4.4 | 28.6 / 1.5 | 12.4 |
| 30% | 58.6 / 6.2 | 25.5 / 2.2 | 8.3 |

"Break-even" is how many needless reviews one avoided misfile must be worth for 0.8 to beat 0.75. Only
if misfiles are many times worse than reviews *and* tricky documents are common does 0.8 pay off —
and a held document waits in the inbox for `review` (or for filing by hand).

## Why 0.75

- On ordinary documents every kind of evidence is accurate (the single failure is a fuzzy group), so holding hint matches back buys nothing there and costs more than half the correct filings (86 down to 38).
- On tricky documents the dangerous matches are the *high-scoring* ones: category names (0.90) and
  group names (1.00) that appear incidentally. Raising the threshold to 0.8 removes the hint-driven
  misfires but keeps every name-driven one.
- At 0.8 the shipped `category_hints` feature is effectively off: no hint-only document auto-files.
- Setting it *at* the hint score is deliberate. `0.75` is the lowest value that files hints, so
  libraries that want them reviewed first can raise it to `0.8`.

The earlier default of 0.8 was chosen by reasoning about the scores ("filing is the risky action, so
make it high"), before there was anything to measure.

## The AI fallback

On all 136 documents, asking `gemma4:26b` for the group and then the category:

| | Answered | Right | Wrong | Precision |
|---|---|---|---|---|
| All documents | 117 | 115 | 2 | 98.3% |
| Ordinary | 93 | 93 | 0 | 100% |
| Tricky | 24 | 22 | 2 | 91.7% |

It said "none" for 18 of the 19 documents that belong to no group. Both wrong answers are genuinely
ambiguous: a document about a *Health* insurance certificate kept with *Home* papers, and "Project
Phoenix **Rising**", a different project that shares a prefix. None of its answers were discarded for
not being an exact name.

But as a fallback it adds little. Replaying its saved answers through the pipeline:

| Threshold | Rules only | Rules + AI |
|---|---|---|
| 0.7 | 113 filed, 89 right, 24 wrong | 119 filed, 94 right, 25 wrong |
| 0.75 | 113 filed, 89 right, 24 wrong | identical — AI answers score 0.70 and never file |
| 0.8 | 49 filed, 38 right, 11 wrong | identical |

It only fills gaps (documents the rules couldn't place); it is never consulted about the rules'
confident mistakes, which is where the misfires are. And a fixed 0.70 cannot suit every model: this one
is far better than that, a weaker one might not be. **This is one model on short synthetic documents**;
measure yours with `ai_arm.py`.

## AI second opinion

`[ai] verify_below` ([ADR-009](../adr/ADR-009-ai-second-opinion.md)) has the AI check rules answers that would file but
score below it; the unit files only if the AI picks the same folder. Replaying the saved `gemma4:26b` answers through the
pipeline at the default threshold, with word boundaries and the ambiguity margin in place:

| `verify_below` | Checks | Filed | Right | Wrong | Ordinary wrong | Tricky wrong | AI calls |
|---|---|---|---|---|---|---|---|
| 0 (off) | nothing | 95 | 89 | 6 | 1 | 5 | 41 |
| 0.8 | keyword hints | 91 | 89 | 2 | 0 | 2 | 105 |
| 0.95 | hints, names, fuzzy groups | 89 | 89 | 0 | 0 | 0 | 147 |

(AI calls include the 41 the fallback makes anyway for documents the rules could not place; 136 documents.) Checking
hints alone removes four of the six remaining misfiles, checking names too removes all six, and no correct filing is lost,
because the model agreed with every correct rules answer. The cost is calls: about 0.5 extra per document at 0.8 and 0.8
at 0.95. This is one model (98% accurate on this corpus), short synthetic documents, and a corpus in which the remaining
misfiles are the kind a second reader catches; a weaker model would overrule more correct answers. Measure yours with
`ai_arm.py` before turning it on. The suggested value is `0.8` for a cheap start and `0.95` for the most protection.

## Follow-ups

Recorded on the [roadmap](../requirements/mvp-roadmap.md); none is implemented. Word-boundary matching and
the ambiguity check, formerly the first two, are built: see [Word boundaries](#word-boundaries) and
[Ambiguity margin](#ambiguity-margin).

1. **Let a library set the score its AI answers get.** Using the AI where the rules are only hint-level is built: see
   [AI second opinion](#ai-second-opinion).
2. **Calibrate on real, longer documents.** Add them to the corpus (below) or run the harness on a
   library you already trust, and re-check the default.

## Word boundaries

A group name, category name or keyword hint now matches only as whole words (with `normalise_names` on, the default),
and a fuzzy group match must start and end on a word edge. Before, `Car` matched inside `carrier`, `care` and `scarf`,
and `Home` inside `homework`. Measured on the main corpus at the default threshold:

| Measure | Before | After |
|---|---|---|
| Filed automatically | 113 | 110 |
| Filed correctly | 89 | 90 |
| Misfiled | 24 | 20 |
| Ordinary documents misfiled | 1 | 1 |
| Ordinary documents filed correctly | 87 | 86 |

Four misfiles went to review or to the right folder (two `shortname` documents now file correctly, two fuzzy lookalikes are held); one correct filing was lost. The lost one is a legitimate near-miss:
`Acme Limited` against the folder `Acme Ltd` is a fuzzy match whose best alignment ends inside `Limited`, so the span is
not on a word edge. The rest are the short-name and fuzzy-lookalike documents the change was for. The `shortname` documents
now file correctly or go to review; the flat corpus's adversarial documents file 3, 1 right, where it filed 4, none right.
What remains is the ambiguity-margin work (`matching-precision`, slice B): the misfiles above are documents that name two
groups or categories, which word boundaries cannot tell apart.

## Ambiguity margin

If the runner-up group (or category) is within `[classification] ambiguity_margin` of the best, the stage is not
chosen: the document goes to review with the candidates named. An exactly named group settles the group stage, so a
sibling that only looks like it (`Project X`, `Project Y`) never holds a document; two exact names do. A name inside
a longer matched name (`Home` in `Home Insurance`) is dropped first. Swept on the main and flat corpora at the default
threshold:

| Margin | Filed | Right | Wrong | Misfile % | What changes |
|---|---|---|---|---|---|
| none (before) | 110 | 90 | 20 | 18.2 | |
| 0 | 95 | 89 | 6 | 6.3 | holds only exact ties: two groups both named exactly, two categories both hint-matched |
| 0.05 | 95 | 89 | 6 | 6.3 | same |
| **0.10 (default)** | 95 | 89 | 6 | 6.3 | same |
| 0.15 | 94 | 88 | 6 | 6.4 | also holds a category named by its name (0.90) beside another's hint (0.75): one more correct filing held, no misfile removed |
| 0.20 | 94 | 88 | 6 | 6.4 | same |

Misfiles fall from 20 to 6 for one correct filing (a tricky document that happened to be right). Of the 15 documents
held, 14 would have been misfiled. They are cases of two groups named exactly (`crossref`, `lookalike`) or two categories hint-matched (`hintcollision`,
`incidental-hint`) named exactly; ordinary documents are untouched. The default is **0.10**: the widest margin that costs nothing on
this corpus, with room above the typical fuzzy-versus-exact gap. 0.15 is the first value that holds a name beside a
hint, which is the line the setting should not cross by default, since a name is stronger evidence than a hint.
Margins from 0 to 0.10 gave identical results here because the corpus's scores sit on a few fixed values; a real
library with more fuzzy matches may separate them.

What remains are the `incidental` documents, where another category's *name* appears in passing and is the only
evidence, and the fuzzy `Databases` lecture. The ambiguity check cannot tell those from a correct filing.

On the flat corpus the adversarial documents file 1 (right), where 3 were filed (1 right) after word boundaries: the
hint collision, the `car park` mention and the `shed-cover` cross-reference are held. Ordinary documents are unchanged (15 of 15).

## Flat libraries (depth 1)

A flat library has groups only, so a group's name, a filename rule on the group and the group's hints are all there
is to match on. A second, small corpus covers it: `tests/calibration/corpus_flat/` holds one library, `household-flat`
(groups `Car`, `Garden`, `Health` and `Home`), 22 documents, 3 of which belong to no group and 5 of which are
adversarial. Run it with `uv run python tests/calibration/report.py tests/calibration/corpus_flat`.

| At the default (0.75) | Documents | Filed | Right | Wrong |
|---|---|---|---|---|
| Ordinary, belonging to a group | 15 | 15 | 15 | 0 |
| Adversarial | 5 | 1 | 1 | 0 |

By how the group was found, for the ordinary documents: an exact name (1.00) 4 of 4 right, a filename rule (0.95) 2 of
2, a keyword hint (0.75) 9 of 9. Among the adversarial documents an exact name was wrong 4 of 4 times before word boundaries, 2 of 3 after, and none now: the one still filed is right. Raising the threshold to 0.8 files only the 6 name and rule matches, so it files 9
fewer correct documents and is no safer: the finding for two levels holds at depth 1. The default does not change.

What goes wrong is the same weakness, and it bites harder: with group names the only name signal, a passing mention
(`car park`) used to beat the real group, and of two groups named in one document the first one won. Word boundaries
(see [Word boundaries](#word-boundaries)) removed `Car` inside `care` ("lawn care") and `scarf`, and the
[ambiguity margin](#ambiguity-margin) holds a document that names two groups.

The fifth adversarial document is a hint collision: `dentist` (a `Health` hint) and `MOT` (a `Car` hint) in one
sentence. A first version of the flat matcher took the first group with a hint and filed it under `Car` at 0.75; found in
review, it now leaves a document to review when hints of more than one group appear. The two-level matcher now does
the same for categories through the ambiguity margin (`hintcollision` in the table above).

This is 22 short, synthetic documents in one library, so its absolute rates say little. The AI arm, and its saved
answers, cover the two-level corpus only and were not re-run for depth 1.

## Learning from review choices

`[learning] enabled` ([ADR-008](../adr/ADR-008-hint-learning.md)) adds hints from the documents a person filed in `review`.
The corpus has no review decisions and is small (at most six documents in a category), so the thresholds could not be
tuned on it. `tests/calibration/learning_sim.py` simulates it anyway: in every category with more than `min_decisions`
documents, the first `min_decisions` count as the person's choices, the rest are held out, hints are learned, and each
held-out document is classified with and without them.

| Minimum decisions | Cap per run | Hints learned | Held-out documents | Changed | Newly right | Newly wrong |
|---|---|---|---|---|---|---|
| 2 | 2 | 14 | 28 | 1 | 0 | 0 |
| 3 (default) | 3 (default) | 8 | 12 | 1 | 0 | 0 |
| 5 | 3 | 1 | 1 | 0 | 0 | 0 |
| 3 | 5 | 9 | 12 | 1 | 0 | 0 |

Learning changed one held-out document at most and made none wrong: the guardrails (a word must be in most of the
person's documents and in none under a sibling category) did their job, but there is too little text for a benefit to
show. The defaults of 3, 3 and a minimum word length of 4 are a cautious starting point, not a measurement; the
real test is a library with real review history.

## Folder-name styles

Folder names written with separators, case styles, order prefixes or `&` used to match nothing (RFC-010,
[ADR-005](../adr/ADR-005-folder-name-matching.md)). A third small corpus, `tests/calibration/corpus_styles/`, holds one
library, `team-notes`: groups `project-alpha`, `ProjectBeta` and `R&D`; categories `01-meeting-notes`, `status_reports`,
`TermsAndConditions` and `Budget & Forecast`; 10 documents, 2 of which belong to no group. Every document names its group
and category in plain words ("Project Alpha meeting notes", "R and D budget and forecast"). It is kept apart from the main
corpus so the saved AI answers, which cover the main corpus exactly, stay valid. Run it with
`uv run python tests/calibration/report.py tests/calibration/corpus_styles`.

| At the default (0.75) | Documents | Filed | Right | Wrong |
|---|---|---|---|---|
| `normalise_names = true` (default) | 8 | 8 | 8 | 0 |
| `normalise_names = false` | 8 | 0 | 0 | 0 |

With normalisation each filing is a category name match, 0.90, the same score a plain spelling gets: a normalised match is
not discounted. Without it, 8 of 8 go to review, 6 of them with a group found but no category and 2 with no group at all.
This shows the effect, not a rate: the documents were written to name their folders. It does not measure
over-matching (`Notes` inside `Meeting Notes`), which is for the ambiguity margin in
[matching-precision](../requirements/matching-precision-prd.md).

## Limitations

- **Synthetic and authored with knowledge of the rules.** Adversarial documents were written to trip
  them; the ordinary ones are tidy. Real documents will be messier in ways neither set captures.
- **Short documents.** About 30–60 words each. Incidental words become likelier as documents get
  longer, so real accuracy is probably worse. As an illustration (not a measurement): appending two
  unrelated paragraphs, one of which happened to contain the word "invoices", flipped 8 correct
  answers in `client-work` (7 hint matches and a fuzzy one) to the wrong category, because a
  category-name match outranks hints.
- **The 20% tricky share is arbitrary.** The sensitivity table exists because the real share is
  unknown.
- **Labels are judgement calls** in a few documents, and the numbers per signal are small.
- **One AI model, one run, temperature 0, English only.**
- **No long-run effects**: nothing here measures how users correct misfiles, or how fast reviews go.

## Reproducing and extending

```bash
uv run python tests/calibration/report.py                       # the rules-only report above
uv run python tests/calibration/report.py tests/calibration/corpus_flat   # the flat-library corpus
uv run python tests/calibration/ai_arm.py gemma4:26b            # needs a local Ollama server; resumable
uv run python tests/calibration/ai_arm.py gemma4:26b --report-only
```

**Add documents.** Drop a file into a library under `tests/calibration/corpus/` at
`<group>/<category>/<file>` (or `_unfiled/<file>`) and add its kind to that library's `kinds.json`.
`test_calibration.py` checks that every document sits where its truth says and is tagged.

**Use your own library.** `report.py` accepts a folder whose *subfolders are libraries* (each with its
own `.microfiche` config). Point it at a library whose documents are already filed correctly: the
inbox, excluded folders and loose files are skipped, and files nested below a category count as
belonging to it. Untagged files report as kind `untagged` (all counted as ordinary).

```bash
uv run python tests/calibration/report.py ~/Documents/libraries   # contains my-library/ with .microfiche/
```

A quicker check with no harness: run `microfiche reclassify` (a dry run) on an already-filed library
and look at the table. A document marked **move** is one the classifier would have misfiled had it
arrived in the inbox; **keep** is agreement. Re-run with a different `confidence_threshold` to see the
trade-off on your own documents.

The pinned findings are tests in `tests/calibration/test_calibration.py`. If a change to the rules or
the default makes one fail, re-run the report, re-read this page, and update both together.

## See also

- [mvp-roadmap.md](../requirements/mvp-roadmap.md) — the follow-ups above, and the rest of what's open.
- [architecture/overview.md](../architecture/overview.md) — where the confidence threshold sits in the classification flow.
- The user-facing guidance: [How sure microfiche has to be](../../how-to-use.md#how-sure-microfiche-has-to-be).
