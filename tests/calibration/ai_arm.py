"""Measure the AI fallback's own accuracy on the calibration corpus. Needs a local Ollama server.

    uv run python tests/calibration/ai_arm.py MODEL [--report-only]

For every corpus document it asks the model for the group, then (if it named one) the category within
that group - exactly the questions ``LLMClassifier`` asks - and compares the pair with where the
document actually sits. Raw model answers are saved to ``results/ai-<model>.json`` so a run can be
resumed, audited, and re-reported without the model.

The model is called through Ollama's HTTP API with its default settings (no ``think`` override), which is
how ``OllamaProvider`` calls it. Results depend on the model: re-run with yours.
"""

from __future__ import annotations

import http.client
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from core.ai.llm_classifier import _AI_CONFIDENCE, LLMClassifier  # the score the pipeline gives any AI answer
from core.library.library import Library
from core.models.category import Taxonomy
from core.models.classification import CategoryMatch, GroupMatch
from core.models.document import Document
from core.parsers import read_documents
from harness import ADVERSARIAL_KINDS, CORPUS_ROOT, UNFILED, evaluate, load_corpus

RESULTS_DIR = Path(__file__).parent / "results"


class OllamaHttpProvider:
    """An ``AIProvider`` that talks to Ollama's HTTP API directly and remembers the last raw answer."""

    def __init__(self, model: str, host: str = "localhost", port: int = 11434) -> None:
        self.model = model
        self._host = host
        self._port = port
        self.last_answer = ""

    def complete(self, prompt: str) -> str:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0},
        }
        connection = http.client.HTTPConnection(self._host, self._port, timeout=900)
        try:
            connection.request("POST", "/api/chat", json.dumps(body), {"Content-Type": "application/json"})
            self.last_answer = str(json.loads(connection.getresponse().read())["message"]["content"])
        finally:
            connection.close()
        return self.last_answer


@dataclass(frozen=True)
class AiResult:
    """What the model answered for one document, next to the truth."""

    taxonomy: str
    path: str
    kind: str
    truth: tuple[str, str] | None
    group: str | None
    group_raw: str
    category: str | None
    category_raw: str

    @property
    def answered(self) -> bool:
        return self.group is not None and self.category is not None

    @property
    def correct(self) -> bool:
        return self.truth is not None and (self.group, self.category) == self.truth


class RecordedAnswers:
    """Replays saved AI answers as a ``Resolver``, so the fallback can be evaluated without the model.

    The model was asked for a category under *its own* group. If the pipeline asks about a different
    group (because the rules chose another one), there is no recorded answer and it counts as "none";
    ``unavailable`` counts how often that happened.
    """

    name = "ai_fallback"

    def __init__(self, results: list[AiResult]) -> None:
        self._by_path = {f"{r.taxonomy}/{r.path}": r for r in results}
        self.unavailable = 0

    def _recorded(self, document: Document) -> AiResult:
        return self._by_path[document.file_path.relative_to(CORPUS_ROOT).as_posix()]

    def resolve_group(self, document: Document, taxonomy: Taxonomy) -> GroupMatch:
        name = self._recorded(document).group
        if name is None:
            return GroupMatch(name=None, confidence=0.0, reason="AI found no matching group")
        return GroupMatch(name=name, confidence=_AI_CONFIDENCE, reason="Resolved by AI fallback")

    def resolve_category(self, document: Document, group: str, taxonomy: Taxonomy) -> CategoryMatch:
        recorded = self._recorded(document)
        if recorded.group != group:
            self.unavailable += 1
            return CategoryMatch(name=None, confidence=0.0, reason="No recorded AI answer for that group")
        if recorded.category is None:
            return CategoryMatch(name=None, confidence=0.0, reason="AI found no matching category")
        return CategoryMatch(name=recorded.category, confidence=_AI_CONFIDENCE, reason="Resolved by AI fallback")


def run(model: str) -> list[AiResult]:
    """Ask ``model`` about every corpus document, resuming from any saved results."""

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"ai-{_slug(model)}.json"
    done: dict[str, dict[str, object]] = {}
    if out.exists():
        done = {f"{r['taxonomy']}/{r['path']}": r for r in json.loads(out.read_text(encoding="utf-8"))}

    provider = OllamaHttpProvider(model)
    resolver = LLMClassifier(provider)
    started = time.time()
    for library_dir in sorted(p for p in CORPUS_ROOT.iterdir() if p.is_dir()):
        taxonomy = Library(library_dir).taxonomy()
        kinds = json.loads((library_dir / "kinds.json").read_text(encoding="utf-8"))
        for path in sorted(p for p in library_dir.rglob("*") if p.is_file()):
            relative = path.relative_to(library_dir)
            if relative.parts[0].startswith(".") or relative.name == "kinds.json":
                continue
            key = f"{library_dir.name}/{relative.as_posix()}"
            if key in done:
                continue
            truth = None if relative.parts[0] == UNFILED else [relative.parts[0], relative.parts[1]]
            (document,) = read_documents([path]).documents
            group = resolver.resolve_group(document, taxonomy)
            group_raw = provider.last_answer
            category_name, category_raw = None, ""
            if group.name is not None:
                category = resolver.resolve_category(document, group.name, taxonomy)
                category_name, category_raw = category.name, provider.last_answer
            done[key] = {
                "taxonomy": library_dir.name,
                "path": relative.as_posix(),
                "kind": kinds.get(relative.as_posix(), "untagged"),
                "truth": truth,
                "group": group.name,
                "group_raw": group_raw,
                "category": category_name,
                "category_raw": category_raw,
            }
            out.write_text(json.dumps(list(done.values()), indent=2), encoding="utf-8")
            print(f"[{len(done):3}] {time.time() - started:6.0f}s {key} -> {group.name} / {category_name}", flush=True)
    return load(out)


def load(path: Path) -> list[AiResult]:
    return [
        AiResult(
            taxonomy=r["taxonomy"],
            path=r["path"],
            kind=r["kind"],
            truth=tuple(r["truth"]) if r["truth"] else None,
            group=r["group"],
            group_raw=r["group_raw"],
            category=r["category"],
            category_raw=r["category_raw"],
        )
        for r in json.loads(path.read_text(encoding="utf-8"))
    ]


def format_report(results: list[AiResult], model: str) -> str:
    """Precision of the model's answers: of the documents it named a group AND category for, how many were right."""

    def line(label: str, subset: list[AiResult]) -> str:
        answered = [r for r in subset if r.answered]
        right = sum(r.correct for r in answered)
        precision = f"{100 * right / len(answered):5.1f}" if answered else "  n/a"
        return f"{label:<28} {len(subset):>5} {len(answered):>9} {right:>6} {len(answered) - right:>6} {precision:>11}"

    belonging = [r for r in results if r.truth is not None]
    unfiled = [r for r in results if r.truth is None]
    ordinary = [r for r in results if r.kind not in ADVERSARIAL_KINDS]
    adversarial = [r for r in results if r.kind in ADVERSARIAL_KINDS]
    group_right = sum(r.group == r.truth[0] for r in belonging if r.truth)
    group_none_ok = sum(r.group is None for r in unfiled)
    unparsed = [r for r in results if r.group is None and r.group_raw.strip().upper() != "NONE"]
    lines = [
        f"AI arm - model {model}, {len(results)} documents",
        f"{'':<28} {'docs':>5} {'answered':>9} {'right':>6} {'wrong':>6} {'precision%':>11}",
        line("all documents", results),
        line("ordinary documents", ordinary),
        line("adversarial documents", adversarial),
        "",
        f"Group named correctly: {group_right} of {len(belonging)} documents that belong to a group",
        f"Said NONE for a document that belongs nowhere: {group_none_ok} of {len(unfiled)}",
        f"Answers LLMClassifier discarded because they weren't an exact group name (and not NONE): {len(unparsed)}",
    ]
    for result in unparsed[:5]:
        lines.append(f"    {result.taxonomy}/{result.path}: {result.group_raw.strip()[:70]!r}")
    return "\n".join(lines)


def format_pipeline_report(results: list[AiResult], model: str) -> str:
    """Rules alone against rules plus the AI fallback, at each threshold, on the same corpus.

    The fallback is only asked about a stage the rules couldn't answer confidently, and its answers
    score 0.70, so they file automatically only when the threshold is 0.70 or lower.
    """

    rows = [
        f"Pipeline with the AI fallback replayed from {model} (AI answers score {_AI_CONFIDENCE})",
        f"{'':>9} | {'rules only':^20} | {'rules + AI':^20}",
        f"{'threshold':>9} | {'filed':>5} {'right':>5} {'wrong':>5}  | {'filed':>5} {'right':>5} {'wrong':>5}",
    ]
    recorded = RecordedAnswers(results)
    for threshold in (0.6, 0.7, 0.75, 0.8, 0.9):
        alone = evaluate(load_corpus(threshold=threshold), threshold)
        combined = evaluate(load_corpus(fallback=recorded, threshold=threshold), threshold)
        rows.append(
            f"{threshold:>9.2f} | {alone.filed:>5} {alone.filed_correct:>5} {alone.filed_wrong:>5}  "
            f"| {combined.filed:>5} {combined.filed_correct:>5} {combined.filed_wrong:>5}"
        )
    rows.append(f"(category lookups with no recorded answer, treated as none: {recorded.unavailable})")
    return "\n".join(rows)


def _slug(model: str) -> str:
    return "".join(c if c.isalnum() or c in ".-" else "_" for c in model)


def main(argv: list[str]) -> None:
    model = argv[1]
    results = load(RESULTS_DIR / f"ai-{_slug(model)}.json") if "--report-only" in argv else run(model)
    print(format_report(results, model))
    print()
    print(format_pipeline_report(results, model))


if __name__ == "__main__":
    main(sys.argv)
