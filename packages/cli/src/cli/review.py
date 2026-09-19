"""Interactive review-queue workflow: accept / modify / create new group-or-category / skip.

Not yet implemented - `cli.commands.review` currently exits with a message pointing here.
The interaction should follow the review UX from docs/development/archive/20260707_microfiche_prd.md
(section 5, User Flow 3), extended to let the user pick a group as well as a category per the
two-stage classifier in docs/development/architecture.md.
"""

from __future__ import annotations
