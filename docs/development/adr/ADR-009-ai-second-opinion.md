# ADR-009: Let the AI check low-confidence rules answers

- **Status:** Accepted
- **Date:** 2026-10-30
- **Decision:** With `--use-ai` and `[ai] verify_below` above 0, a rules answer whose confidence is below it is checked by
  the AI. Agreement files the unit as the rules would have; disagreement or "none" sends it to review with both answers.
  See [Decisions](#decisions).
- **Source:** [ai-second-opinion-prd.md](../requirements/ai-second-opinion-prd.md)

## Context

The AI fallback is accurate (98% on the calibration corpus) but is asked only when the rules are unsure, and its 0.70
answers never file at the default threshold of 0.75. Keyword hints, which do file, were right 2 times in 14 on the tricky
documents. Asking the AI about those answers puts its accuracy where the rules are weakest.

## Decisions

- **`[ai] verify_below`, a confidence, 0 means off (the default).** Scores are fixed per kind of evidence (hint 0.75, category
  name 0.90, fuzzy group 0.85 to 0.99, exact group 1.0, filename rule 0.95), so 0.8 checks hints only and 0.95 would reach
  names and fuzzy groups. A value above 0 does nothing without `--use-ai`. The value to suggest is chosen by replaying
  the saved AI answers on the calibration corpus.
- **Per stage.** The group and the category answers are each checked if they score below `verify_below`. The AI is asked the
  same per-stage question as the fallback.
- **The AI never moves a unit somewhere the rules did not propose.** Agreement means the same name. A different name or
  "none" holds the unit for review, and the reason carries both answers.
- **A confirmed answer keeps the rules' score.** Agreement lets the unit file at the confidence it already had; it does not
  raise it, so the threshold keeps its meaning.
- **`Classifier` owns the decision**; `LLMClassifier` only answers. An unavailable AI leaves rules-only behaviour and the
  existing single warning (`ai_unavailable`).
- **Reporting:** the match reason says an answer was verified, and the `sort` summary counts answers checked, confirmed and
  overruled.
- **`OllamaProvider` turns off the model's "thinking"** where the client supports it, so each call is as fast as it can be.
- **`reclassify --use-ai` is a second PR** that reuses the same verification; this one covers `sort` and `review`.

## Alternatives considered

- A boolean `verify_hints`: simpler, but cannot extend to names or fuzzy groups without a second setting.
- Raising a confirmed answer's confidence: blurs what a score means.
- Letting the AI override with its own answer: moves a unit somewhere the rules did not propose, which the AI's 0.70 score
  does not justify.
- Asking the AI about name and filename-rule matches: the PRD's Won't, and `verify_below` leaves the door open.

## Consequences

- One extra call per checked document (about 2 to 5 seconds on a local model) for users who opt in.
- More units reach review when the AI disagrees with a hint; fewer wrong ones file.
- A new `[ai]` setting to document in the defaults, example config, how-to-use, README and the `init` walk-through.
