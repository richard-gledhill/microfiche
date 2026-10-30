# SPEC: AI second opinion (`ai-second-opinion`)

Source: [ai-second-opinion-prd.md](../../../requirements/ai-second-opinion-prd.md), decided in
[ADR-009](../../../adr/ADR-009-ai-second-opinion.md). Built in two PRs.

## Scope

- `[ai] verify_below` (0 = off). `Classifier._resolve` has the fallback check a primary answer that would file but scores
  below it, per stage: the same folder confirms (reason ends "confirmed by the AI"), another or none holds the unit
  (`ClassificationResult.ai_overruled`, an overruled document casts no folder vote), an unavailable AI leaves the answer.
  `Classifier.verification` counts checked, confirmed and overruled; `sort` prints them.
- `OllamaProvider` sends `think=False`, retrying without it if refused.
- Second PR: `reclassify --use-ai` (`run_reclassify(ai_classifier=...)`), the same pre-run check before the lock, and the
  same summary line derived from the proposals.
- Replay in `tests/calibration/` with the saved answers (`load_corpus(verify_below=...)`).

## Not in scope

Asking the AI about name and filename-rule matches beyond what `verify_below` reaches; a decision-model classifier.
