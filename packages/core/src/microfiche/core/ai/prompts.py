"""Prompt templates for the AI fallback: one question per level (the group, then the category)."""

from __future__ import annotations

GROUP_RESOLUTION_PROMPT = """You are filing a document into one of these existing groups: {group_names}.
(A group is a top-level folder in the library, such as a project, client or course.)

Document text (truncated):
---
{document_text}
---

Reply with exactly one group name from the list above, or the single word NONE if it fits none of them."""

CATEGORY_RESOLUTION_PROMPT = """You are filing a document into the group "{group_name}", \
which has these categories: {category_names}.

Document text (truncated):
---
{document_text}
---

Reply with exactly one category name from the list above, or the single word NONE if it fits none of them."""
