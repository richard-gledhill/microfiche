"""Prompt templates for the AI fallback classification and category-proposal passes."""

from __future__ import annotations

GROUP_RESOLUTION_PROMPT = """You are filing a document into one of these existing projects: {group_names}.

Document text (truncated):
---
{document_text}
---

Reply with exactly one project name from the list above, or the single word NONE if it fits none of them."""

CATEGORY_RESOLUTION_PROMPT = """You are filing a document into project "{group_name}", \
which has these categories: {category_names}.

Document text (truncated):
---
{document_text}
---

Reply with exactly one category name from the list above, or the single word NONE if it fits none of them."""

CATEGORY_PROPOSAL_PROMPT = """These documents don't fit any existing category. Suggest up to {top_n} short,
title-case category folder names that would group them sensibly.

Document excerpts:
---
{document_excerpts}
---

Reply with one category name per line."""
