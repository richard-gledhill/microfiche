# AI classifier options

Microfiche's AI fallback today asks a chat model (Ollama, or OpenAI in code) to pick a group or category as
free text, then checks the answer against the taxonomy. A second kind of model, a **decision model** (a
classifier that takes text and a fixed list of options and returns one option with a probability), could do
the same job more cheaply and with a real score. This page records why, which models are candidates, and what
has to be checked before any is adopted. It feeds
[decision-model classifier](../rfcs/RFC-005-decision-model-classifier.md) in the feature backlog (formerly Stage 4.5),
which is under review. Nothing here is built.

## Why a second kind of model

| | Chat model (today) | Decision model |
|---|---|---|
| Output | Free text, parsed and matched against the taxonomy | One of the supplied options, or none, with a probability per option |
| Confidence | A flat `0.70` for any answer from any model (`_AI_CONFIDENCE`) | The model's own probability, so a sure answer can pass the threshold and an unsure one can't |
| Can it invent a folder? | It can name one; `Classifier` rejects it afterwards | No: the output is bounded to the options |
| Cost and speed | One Ollama call took about 5 s on the model measured ([calibration.md](../testing/calibration.md)) | Described as faster and cheaper than a general chat model |
| Fit with the design | `LLMClassifier`, a `Resolver` | A second `Resolver` beside it; `Classifier` does not change |

It also helps two items already on the roadmap: "always scores 0.70 whatever model is behind it" and "use the AI
where the rules are ambiguous". Ranked probabilities could also give the Stage 5 `review` prompt a short list
of suggestions to accept.

## Candidates

These came from a web search and have **not** been checked against their model cards or documentation. Check
each one before relying on any claim below, as the backlog entry says.

| Model | Maker | What the search results say | To verify |
|---|---|---|---|
| Jev | TypeSafe | A text classifier that answers from a fixed list and returns labels with option probabilities; up to 64k tokens of input; used to classify pages of tax documents. One independent benchmark found trained local classifiers more accurate on sets that weren't document classification. | Local or hosted, licence, size, whether per-option probabilities are exposed, Windows support |
| Clef and Clef-flash | Cloudflare | "Decision models" for bounded structured outputs, hosted on Workers AI. Cloudflare's own scores were self-reported. | Hosted means document text leaves the machine; account and key needed; whether the weights are downloadable |
| Nimble | Bespoke Labs | An open-source model of about 9B parameters that makes typed decisions without generating tokens. The claim that it beats a 27B model at classification comes from a news summary and is unconfirmed. | Primary source (paper or model card), hardware needed, licence |

A model of this size also needs a GPU or plenty of memory. That is no heavier than the 8B chat model the Ollama
provider already assumes, but it is a real cost for a document organiser.

## Rules for adopting one

- **Privacy:** a hosted model sends document text off the machine, like `OpenAIProvider`. It must be chosen
  explicitly in `[ai]`, the run must say so, and any key comes from an environment variable.
- **A measurement decides, not a name:** the calibration harness in `tests/calibration/` already replays saved
  AI answers. Save the decision model's answers for the same corpus, and adopt it only if it is no less precise
  than the chat model at the same coverage and its probabilities separate right answers from wrong ones.
- **Probabilities are not automatically calibrated.** A mapping from probability to confidence (direct, or
  scaled) is a setting, checked against the corpus.
- **No network in the test suite:** tests use a fake model, as they do for the chat provider.

## Deferred

- Training a small classifier on the library's own ledger. The ledger is a record of filings that were accepted,
  so it is labelled data; a SetFit-style model trained on it would need no outside service.
- Chaining models (decision model first, chat model for what it can't decide).
- Downloading and managing model files for the user.

## Sources

- [Models Built to Do One Thing Well](https://www.deeplearning.ai/the-batch/models-built-to-do-one-thing-well) (Jev)
- [Jev vs classic classifiers benchmark](https://www.mindstudio.ai/blog/jev-vs-classic-classifiers-benchmark/)
- [Introducing Clef: our open-source decision models](https://blog.cloudflare.com/clef-decision-models/) (Cloudflare)
- [Bespoke Labs' Nimble beats a 27B model at classification using just 9B](https://hermes-ai.net/news/bespoke-labs-nimble-beats-a-27b-model-at-classification-using-just-9b/) (secondary source)
