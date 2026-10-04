"""Print the confidence-threshold calibration report.

    uv run python tests/calibration/report.py [CORPUS_DIR]

CORPUS_DIR defaults to the bundled corpus; point it at a folder of already-correctly-filed libraries
(each with its own .microfiche config) to calibrate against your own documents.
"""

from __future__ import annotations

import sys
from pathlib import Path

from core.rules.confidence import DEFAULT_CONFIDENCE_THRESHOLD
from harness import CORPUS_ROOT, format_report, load_corpus


def main(argv: list[str]) -> None:
    corpus_root = Path(argv[1]) if len(argv) > 1 else CORPUS_ROOT
    print(format_report(load_corpus(corpus_root), DEFAULT_CONFIDENCE_THRESHOLD))


if __name__ == "__main__":
    main(sys.argv)
