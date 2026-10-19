# Request for Change

A request for change (RFC) is a design question discussed before it is built: what to change, the options, and the
questions to settle.

**Tracker: TBC.** A GitHub Project for microfiche is not set up yet. Until it is, RFCs are stored here as local files:

- One file per RFC, named `RFC-NNN-title.md` (for example `RFC-001-plugin-architecture.md`), numbered in sequence.
- Start each file with a status line: `Status: Draft`, `Discussion`, `Accepted`, `Rejected` or `Superseded`.
- When an RFC is decided, record the outcome as an ADR in [`../adr/`](../adr/README.md), link the ADR and the RFC to
  each other, and set the RFC's status. Never delete an RFC; a rejected one keeps its reasoning.

When a GitHub Project is set up, the tracker becomes the single source of truth: new RFCs are GitHub issues labelled
`rfc` (the label doesn't exist yet), local files are no longer added, and each open local RFC is moved to an issue and
linked from here.

| File | What it is |
|---|---|
| [feature-backlog.md](feature-backlog.md) | Features outside the MVP that still need deciding, and code removed from the MVP with where to restore it from. Each entry is in effect a draft RFC, with its open questions; one becomes an `RFC-NNN` file when it is taken up. |
