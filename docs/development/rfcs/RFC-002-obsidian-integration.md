# RFC-002: Obsidian integration

Status: Draft

**Background:** removed from the MVP on 2026-10-12. It was implemented and unit-tested but never wired into `sort`, so no
user-visible behaviour was lost. It was Stage 5 of the [MVP build plan](../plan/archive/2026-10-mvp/plan.md) together with `review`;
`review` stayed in the MVP and this half moved to the feature backlog.
**Future feature update** (2026-10-19): to be built as the first plugin, on the
[plugin architecture](RFC-001-plugin-architecture.md) below.

**Why deferred.** It widened the MVP past "classify, file, undo, and work the review queue". It is also one of what
should be several integrations with other software, so it is better designed on top of the
[plugin architecture](RFC-001-plugin-architecture.md) than bolted onto `core`. Nothing in the sort loop depends on it.

## What was removed, and where to get it back

The last commit that contains all of it is `551eec9` on `main`. Merges there are plain merge commits, so the commit
stays reachable.

| What | Where it was |
|---|---|
| `index.md` writer | `packages/core/src/core/obsidian/index_writer.py` |
| `TagIndex.md` parser and writer | `packages/core/src/core/obsidian/tag_index.py` |
| Tag matcher | `packages/core/src/core/obsidian/tag_mapper.py` (and the package `__init__.py`) |
| Tests | `tests/core/test_index_writer.py`, `tests/core/test_tag_governance.py` |
| `[obsidian]` config section | `ObsidianConfig` and the `MicroficheConfig.obsidian` field in `core/config.py`; the section in `core/defaults/microfiche-config.toml`, in the template `microfiche/microfiche-config.toml`, and in the two test libraries' configs |
| `index` command | `commands.index` and its registration in `cli/app.py` (a stub that always exited 1) |
| Diagram entry | the `core/obsidian` line in `scripts/module_diagram.py`'s `SUBGRAPHS` |

To read or restore a file:

```bash
git show 551eec9:packages/core/src/core/obsidian/tag_mapper.py
git checkout 551eec9 -- packages/core/src/core/obsidian  # the path at that commit, before the move to microfiche/core tests/core/test_index_writer.py tests/core/test_tag_governance.py
```

Restoring the files does not restore the config section or the command; those need the design questions below
answered first.

## What it did

**`index.md` folder notes** (`index_writer.write_index(folder, entries)`). Writes `<folder>/index.md`, regenerated in
full each time, from a list of `IndexEntry(file_name, tags, confidence, filed_on)`. The title is the folder's name;
entries are sorted case-insensitively by file name. A Markdown file is linked as a wikilink and any other file as a
relative link, so the notes read normally in Obsidian:

```markdown
# 01 Requirements

- [[architecture_review]] — #requirements #phoenix (filed 2026-09-07, confidence 0.91)
- [spec](../spec.pdf) — #architecture (filed 2026-09-07, confidence 0.80)
```

The intent was to regenerate it for every folder touched by a sort, a reclassify or a rollback, so it always matches
what is there. That call was never written.

**`TagIndex.md` vocabulary** (`tag_index.TagIndex`). Reads the library's root `TagIndex.md`: a `# Tag Index` heading,
then one `- #tag` line per canonical tag. Tags under a `## Proposed` heading are proposals awaiting a human, kept apart
from the canonical list. `load` returns an empty index if the file is missing; `add_proposed` ignores a tag that is
already canonical; `save` rewrites the file with canonical tags first and the proposed ones after.

**Suggest-only tag governance** (`tag_mapper.map_tags(candidates, tag_index, mode)`). The decision, first recorded in
[architecture/overview.md §6](../architecture/overview.md#obsidian-integration): a tag with no close canonical match is still applied to
the document and is added to `## Proposed`, never merged into the reviewed list. Three modes:

| Mode | A close canonical match | No close match |
|---|---|---|
| `off` | candidates returned unchanged; the index is not read or written | |
| `suggest` (default) | replaced by the canonical tag | kept, and proposed |
| `strict` | replaced by the canonical tag | dropped |

Matching used RapidFuzz `WRatio` with `utils.default_process` (lowercases and strips punctuation on both sides,
keeps accents), `score_cutoff=89`, and a rounded score of at least 90 to count. So `Python` maps to `python` and
`Machine_Learning` to `machine-learning`, `Café` maps to `café`, but `munchen` does not match `münchen` and `ber` does
not match `über`. Whether to fold accents is still undecided.

**Config** (all removed):

```toml
[obsidian]
enabled = false
tag_index_path = "TagIndex.md"
tag_mode = "suggest"   # suggest | strict | off
```

`enabled` was never read, so it did nothing; `tag_mode` and `tag_index_path` were only read by tests.

**Tests that existed.** `index.md` links Markdown as a wikilink and other files as relative links; the tag index
round-trips through save and load; `suggest` normalises a near match and proposes a new tag; `strict` drops an
unmatched tag; matching ignores case, punctuation (`Machine_Learning`) and keeps accents (`Café`, and `ber` against
`über` does not match).

## The old Stage 5 plan for it

Kept from the build plan so the intent is not lost:

- Define the suggest-only tag governance contract: what happens to a tag with no canonical match.
- Design the `index.md` folder-note format (wikilinks for `.md` files, relative links for other formats).
- Design the `TagIndex.md` parser and the `## Proposed` section convention for ungoverned tags.
- Decide how tags with accents match (see above, and [ADR-002](../adr/ADR-002-switch-to-rapidfuzz.md)).
- Regenerate a touched folder's `index.md` after every sort, reclassify and rollback.
- Fuzzy-match extracted keywords against `TagIndex.md` and append unmatched ones to `## Proposed`.
- Add an `[obsidian]` settings section (enable switch, tag mode, tag index path, a tag match threshold).
- Wire a `microfiche index [--scope PATH]` command that force-regenerates the notes.
- Tests: `index.md` generation for a folder of mixed Markdown and other files; tag governance for a canonical match, a
  fuzzy match and a fully novel tag.

## Questions to settle before building it again

- **Where do tags come from?** The modules only mapped tags handed to them. Nothing in microfiche extracts keywords
  from a document, and the ledger has no `tags` field ([data-model.md](../architecture/data-model.md)). Both are needed first, and
  tag extraction may be useful beyond Obsidian.
- **Generated files inside the library.** An `index.md` is a file microfiche writes among the user's documents, the
  thing the ledger was introduced to avoid ([architecture/overview.md §7](../architecture/overview.md#7-classification-ledger-replaces-per-file-sidecars)).
  If it comes back, then `reclassify` (which walks every file under the library) and `DuplicateIndex` (which hashes
  same-size library files) would both see it, so it must be recognised and skipped, and `rollback` must either record
  its writes or regenerate it. The same applies to `TagIndex.md` at the library root.
- **When it runs.** After `file_batch`, after `rollback_job`, and after `reclassify --apply`: a hook on a finished
  job, receiving the job and the folders it touched. That is the first extension point of the plugin architecture.
- **Failure.** A failed note write must not fail or undo a sort.
- **Config name.** Probably under the plugin's own namespace rather than a top-level `[obsidian]`; decide with the
  plugin architecture, not before.
- **Accent folding** for tag matching (above).
