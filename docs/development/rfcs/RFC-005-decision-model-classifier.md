# RFC-005: Decision-model classifier

Status: Draft

**Background:** under review. It was Stage 4.5 of the [MVP build plan](../plan/archive/2026-10-mvp/plan.md); it was moved to the feature backlog on 2026-10-13
and the number is not reused. Nothing was built.

**Why it is under review.** It was gated on a measurement and has not been started, and the gate cannot be run from the
repository alone: the candidates (Jev, Clef, Nimble) came from an unverified web search, a model has to be run somewhere
to be measured (a GPU model locally, or a hosted account), and a hosted one sends document text off the machine. The
AI fallback is only asked where the rules are unsure, and the calibration already shows it adds little as built
([calibration.md](../testing/calibration.md)), so the expected gain for the first release is small. The research, with its sources
and the rules for adopting a model, is in [ai-classifier-options.md](../architecture/ai-classifier-options.md).

**The proposal.** `sort --use-ai` could use either a chat model (as today) or a **decision model**, a classifier that
takes text and a fixed list of options and returns one option with a probability. Both would sit behind `Classifier` as
resolvers. The model's own probability would become the confidence instead of a flat `0.70`, and the calibration report
would show on the same corpus how each performs, so the choice is a measurement. It also shortens a path to ranked
suggestions for [`review`](../plan/archive/2026-10-mvp/plan.md#stage-5--review-workflow), which today offers only the classifier's best guess.

## The design to keep

- **A separate seam.** A `ChoiceModel` protocol, `choose(text, question, options) -> Choice`, with the chosen option or
  none, its probability and the ranked alternatives. It is separate from `AIProvider` because the two vary: one returns
  free text to be parsed, the other returns a bounded choice with a score.
- **A second resolver.** `ChoiceClassifier` beside `LLMClassifier`, with the taxonomy's names plus "none" as the options.
  `Classifier` still checks the answer against the taxonomy and applies the threshold. `run_sort`, the CLI's
  `_build_ai_classifier` and `SortReport.ai_unavailable` are typed to `LLMClassifier` today and would be generalised, and
  the "stop asking after the first failure" logic in `LLMClassifier._ask` would be shared, not copied.
- **A mapping from probability to confidence** (direct, or scaled and clamped) as a setting, since a model's
  probabilities are not automatically calibrated.
- **Config.** `[ai] kind = "chat" | "choice"` alongside `provider`, `model` and `endpoint`. One kind at a time.
- **Privacy.** A hosted model is treated like `OpenAIProvider`: chosen explicitly, the run says so, any key comes from an
  environment variable.
- **The adoption gate.** Adopt a decision model only if, on the calibration corpus, it is no less precise than the chat
  model at the same coverage and its probabilities separate right answers from wrong ones. If none passes, record that and
  stop.
- **Where it lives.** `ai/choice_classifier.py`, one backend (the best verified candidate) behind `build_provider`, with any
  new dependency in the `ai` extra, and saved decision-model answers in `tests/calibration/` as for the chat model's.

## Questions to settle before building it

- Can any candidate be run on a Windows machine without a GPU, and is it licensed for this use? Check each against its own
  documentation or model card (the summaries in `ai-classifier-options.md` are unverified).
- Is the gain worth a new dependency and a second AI setting, given how rarely the AI is asked?
- Tests it would need: a fake `ChoiceModel` (an option chosen, "none" chosen, an option outside the taxonomy treated as
  unresolved, a probability below the threshold going to review), the probability mapping and its bounds, a backend test
  against a mocked response (the suite uses no network and no model), and the calibration report with both kinds.
- Deferred with it: training a small classifier on the library's own ledger, chaining models, and downloading or managing
  model files for the user.
