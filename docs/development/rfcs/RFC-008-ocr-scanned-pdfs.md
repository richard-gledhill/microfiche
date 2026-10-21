# RFC-008: OCR for scanned PDFs

Status: Draft

**Background:** future feature update (2026-10-19). Drafted as a post-MVP requirement, then moved to the feature backlog to be built after the
[post-MVP features](../requirements/post-mvp-capability-map.md).

**Why.** Scanned letters, receipts and statements are a large share of the loose documents in a household library. A
scanned PDF has no text layer, so it reads as empty text, matches nothing, and always goes to review.

**Why later.** It is independent of everything else, so it can be picked up at any point, and should move earlier if
scanned documents turn out to be common in real libraries.

## The design to keep

- When a PDF yields no text (or too little per page), OCR its pages and classify the recognised text.
- Off by default (`[parsing] ocr = false`), as an optional extra (`ocr`, like `ai`), so a plain install is unchanged.
  A run says how many documents were OCR'd.
- Local only: no page image or text leaves the machine.
- A page and time cap; a document over it goes to review with the reason. An OCR failure makes the document unreadable
  for review, as any parser failure does, and never aborts a run.
- Files are never modified (no text layer written back).
- The fallback lives in `parsers/pdf_parser.py`, which uses `pymupdf` to render pages.

## Questions to settle before building it

- Which engine? PyMuPDF's OCR needs Tesseract installed separately; RapidOCR on ONNX Runtime installs with pip alone.
  Compare accuracy, install size and Windows support, and record the choice as an ADR.
- Cache OCR'd text by content hash, so `reclassify` does not OCR the same scan again?
- Images (`.png`, `.jpg`, `.tiff`) as a supported format once OCR exists?
- Tests it would need: a fake engine at the parser seam (no OCR engine in the suite), one test skipped when the extra is
  missing, the cap, and a clear error when `ocr = true` without the extra.
