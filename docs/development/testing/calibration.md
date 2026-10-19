# Calibrating the confidence threshold

How `DEFAULT_CONFIDENCE_THRESHOLD` (`core/rules/confidence.py`) was chosen, what the measurements
showed, and how to repeat them on your own documents. The harness, the labelled corpus and the saved
AI results are in [`tests/calibration/`](../../../tests/calibration/).

## Summary

The default is **0.75**. It was 0.8 until this was measured.

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
- **Safer filing needs better matching, not a higher cut-off.** A prototype check, "hold a document
  when more than one group is named or more than one category has evidence", cut misfires from 24 to 8
  on this corpus at the cost of 2 correct filings. It is not implemented (see
  [Follow-ups](#follow-ups)).
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
| `hintcollision` | 3 | hints of two categories both appear; the earlier category wins |
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
| ≤ 0.75 | rules, names, hints | 113 filed: 89 right, 24 wrong | 88 filed: 87 right, 1 wrong | 25 filed: 2 right, 23 wrong |
| 0.8 – 0.85 | rules, names | 49 filed: 38 right, 11 wrong | 38 filed: 38 right, 0 wrong | 11 filed: 0 right, 11 wrong |
| 0.95 | filename rules only | 6 filed: 6 right | 6 filed: 6 right | none filed |

(At 0.9 one fuzzy lookalike drops out: 48 filed, 10 wrong. Below 0.75 nothing changes for the rules alone, because their lowest score is 0.75.)

How reliable each kind of evidence was:

| How the answer was found | Score | Ordinary: right / answered | Tricky: right / answered |
|---|---|---|---|
| filename rule | 0.95 | 6 / 6 | — |
| category name | 0.90 | 32 / 32 | 0 / 11 |
| keyword hint | 0.75 | 49 / 50 | 2 / 14 |

(The one ordinary failure is a *fuzzy* group match: a machine-learning lecture that mentions "a
database" was filed under the `Databases` course.)

**Sensitivity to how many documents are tricky.** The corpus is 20% tricky on purpose; a real library
will differ. Blending the ordinary and tricky outcomes at other shares, per 100 documents:

| Tricky documents | 0.75: right / wrong | 0.8: right / wrong | Break-even for 0.8 |
|---|---|---|---|
| 0% | 79.8 / 0.9 | 34.9 / 0.0 | 49 reviews per misfile |
| 5% | 76.2 / 5.1 | 33.1 / 2.0 | 14 |
| 10% | 72.6 / 9.3 | 31.4 / 4.1 | 8 |
| 20% | 65.3 / 17.8 | 27.9 / 8.1 | 4 |
| 30% | 58.1 / 26.2 | 24.4 / 12.2 | 2.4 |

"Break-even" is how many needless reviews one avoided misfile must be worth for 0.8 to beat 0.75. Only
if misfiles are many times worse than reviews *and* tricky documents are common does 0.8 pay off —
and a held document waits in the inbox for `review` (or for filing by hand).

## Why 0.75

- On ordinary documents every kind of evidence is accurate (the single failure is a fuzzy group), so
  holding hint matches back buys nothing there and costs more than half the correct filings (87 down to 38).
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

## Follow-ups

Recorded on the [roadmap](../mvp-roadmap.md); none is implemented.

1. **Ambiguity check.** Hold a document when more than one group is named in its text, or more than one
   category has evidence (a filename rule counts as unambiguous). On this corpus: at 0.75, misfires
   24 → 8 with correct filings 89 → 87; at 0.8, 11 → 3 and 38 → 37. Caveats: it was devised after
   seeing the misfires, and these documents are short; long real documents will mention more than one
   category far more often, so the cost in correct filings is unmeasured.
2. **Match group names on word boundaries.** `Car` matches `carrier` and `card`, `Home` matches
   `homework`. Short or common group names are filed with full confidence on a substring (`shortname`:
   0 of 2 right).
3. **Use the AI where the rules are ambiguous or only hint-level**, not just where they're silent, and
   let a library set the score its AI answers get.
4. **Calibrate on real, longer documents.** Add them to the corpus (below) or run the harness on a
   library you already trust, and re-check the default.

## Flat libraries (depth 1)

A flat library has groups only, so a group's name, a filename rule on the group and the group's hints are all there
is to match on. A second, small corpus covers it: `tests/calibration/corpus_flat/` holds one library, `household-flat`
(groups `Car`, `Garden`, `Health` and `Home`), 22 documents, 3 of which belong to no group and 5 of which are
adversarial. Run it with `uv run python tests/calibration/report.py tests/calibration/corpus_flat`.

| At the default (0.75) | Documents | Filed | Right | Wrong |
|---|---|---|---|---|
| Ordinary, belonging to a group | 15 | 15 | 15 | 0 |
| Adversarial | 5 | 4 | 0 | 4 |

By how the group was found, for the ordinary documents: an exact name (1.00) 4 of 4 right, a filename rule (0.95) 2 of
2, a keyword hint (0.75) 9 of 9. Among the adversarial documents an exact name was wrong 4 of 4 times. Raising the threshold to 0.8 files only the 6 name and rule matches, so it files 9
fewer correct documents and is no safer: the finding for two levels holds at depth 1. The default does not change.

What goes wrong is the same weakness, and it bites harder: with group names the only name signal, `Car` is found inside
`care` ("lawn care") and `scarf` at 1.00, a passing mention (`car park`) beats the real group, and of two groups named
in one document the first one wins. Matching group names on word boundaries (see [Follow-ups](#follow-ups)) would
remove the first two.

The fifth adversarial document is a hint collision: `dentist` (a `Health` hint) and `MOT` (a `Car` hint) in one
sentence. A first version of the flat matcher took the first group with a hint and filed it under `Car` at 0.75; found in
review, it now leaves a document to review when hints of more than one group appear. That is stricter than the
two-level matcher, which still lets the earlier category win (`hintcollision` in the table above): with a group as the
only thing to match on, a wrong guess has no second stage to correct it.

This is 22 short, synthetic documents in one library, so its absolute rates say little. The AI arm, and its saved
answers, cover the two-level corpus only and were not re-run for depth 1.

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

- [mvp-roadmap.md](../mvp-roadmap.md) — the follow-ups above, and the rest of what's open.
- [architecture/overview.md](../architecture/overview.md) — where the confidence threshold sits in the classification flow.
- The user-facing guidance: [How sure microfiche has to be](../../how-to-use.md#how-sure-microfiche-has-to-be).
