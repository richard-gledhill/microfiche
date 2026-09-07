"""Interactive review-queue workflow: accept / modify / create new group-or-category / skip.

Not yet implemented - `cli.commands.review` currently exits with a message pointing here.
The interaction should follow the review UX from docs/prd/20260707_microfiche_prd.md (section 5,
User Flow 3), extended to let the user pick a group as well as a category per the two-stage
classifier in docs/prd/20260907_microfiche_architecture_v2.md.
"""

from __future__ import annotations
