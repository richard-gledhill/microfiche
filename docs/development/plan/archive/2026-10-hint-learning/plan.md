# Plan: hint learning

1. Config section, library-file field, ledger event (tests pinned by the existing config and schema checks).
2. `learning.py` with the guardrails, test first.
3. Wire into `ReviewSession.commit`; learned-hint marker in the rules; `sort` and `review` messages.
4. Held-out simulation; docs; `make check`/`make test`; PR.
