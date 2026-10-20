# Ask the AI about hint-level matches

Status: Draft

- **Id:** `ai-second-opinion` ([capability map](post-mvp-capability-map.md), #4)
- **Depends on:** `matching-precision` (measured against the corrected rules)

## Why

The AI fallback was 98% accurate on the calibration corpus but changes almost nothing as built: it is asked only when
the rules are unsure, never about their confident mistakes, and its answers score 0.70, below the default threshold of
0.75, so they never file ([calibration.md](../testing/calibration.md#summary)). Meanwhile keyword hints, which file at
0.75, were right only 2 times in 14 on the tricky documents. Asking the AI to check hint-level answers puts its accuracy
where the rules are weakest, for users who already turned it on.

## User stories

- As a user running `sort --use-ai`, I want the AI to double-check matches that rest only on a keyword hint, so a
  wrong hint sends the document to review instead of the wrong folder.
- As a user on a slow machine, I want AI calls to be as fast as they can be, and to know at the start if the model is
  missing.

## Requirements

**Must**
- A setting (`[ai] verify_below`, name to confirm) gives the confidence below which a rules answer is checked by the AI.
  Off by default; the shipped value when on is chosen by calibration.
- When the AI agrees with a checked answer, the unit files as it would have. When it disagrees, or answers "none", the
  unit goes to review with both answers in the reason. The AI never moves a unit somewhere the rules did not propose.
- `reclassify` gains `--use-ai`, with the same fallback and verification as `sort`.
- `OllamaProvider` turns off the model's "thinking" where the model supports it.
- Before the first document, check the configured model is available, and say so once if it is not (the run continues
  rules-only, as today when the provider fails).
- Nothing changes without `--use-ai`. The privacy notice for OpenAI still applies.

**Should**
- Record in the ledger's reasons when an answer was verified.
- Report how many answers the AI checked, confirmed and overruled in the `sort` summary.

**Won't (this time)**
- A decision-model classifier ([backlog](../rfcs/feature-backlog.md#decision-model-classifier)).
- Asking the AI about name and filename-rule matches.

## Acceptance criteria

- With fake providers: an agreeing AI files a hint-level unit; a disagreeing one sends it to review with both answers;
  an unavailable one leaves rules-only behaviour and one warning.
- On the calibration corpus with the saved AI answers, verification lowers misfiles at the default threshold. The
  numbers, and the chosen `verify_below`, are recorded in `calibration.md`.
- `reclassify --use-ai` proposes the same actions as `sort --use-ai` would for the same documents.
- `make check` and `make test` pass with no network or Ollama in the suite.

## Technical outline

Guidance for the spec, not binding.

- `Classifier` owns the decision (it already owns threshold and fallback); `LLMClassifier` gains nothing new beyond
  answering the same per-stage question.
- Replay the saved answers in `tests/calibration/` to measure without a model.
- Ollama: pass the chat option that disables thinking (check the `ollama` client version's API before relying on a
  parameter name), and use `client.list()` or `show()` for the availability check.

## Related

- [mvp-roadmap.md](mvp-roadmap.md#future-work): "Use the AI where the rules are ambiguous or hint-level" (with the
  thinking and default-model notes), which this absorbs.
- [mvp-roadmap.md](mvp-roadmap.md#cli-command-status): "No AI fallback in `reclassify` yet".

## Open questions

- Should a confirmed answer's confidence rise (to the threshold, or above), or stay as the rules scored it?
- Is the cost acceptable: one extra call per hint-level document, about 2 to 5 seconds each on a local model?
