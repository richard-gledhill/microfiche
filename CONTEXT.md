# microfiche

Files loose documents into a library of group and category folders, deciding where each belongs and
recording every move so it can be undone.

## Language

### The library

**Library**:
The folder microfiche manages: an inbox plus one or two levels of folders, group then category (or group alone, in a flat library).
_Avoid_: Vault, repository, archive

**Inbox**:
The single library-wide folder where new documents are dropped to be sorted; it is `_sorting` unless the library names another.
_Avoid_: Queue, drop folder, staging area

**Group**:
A top-level folder of the library — what a document belongs to, such as a project, client or course.
_Avoid_: Project (a project is only one thing a group can be), folder, bucket

**Category**:
A folder inside a group, where a document actually lands — such as a document type or a stage of work. A flat library has none: its documents land in the group.
_Avoid_: Subfolder, tag, label

**State folder**:
The hidden folder inside a library where microfiche keeps its config and its own records.
_Avoid_: Data directory, config folder, logs folder

**Library file**:
The file in the state folder (`microfiche-library.json`) that describes the library's folders with the hints and filing rules that help match them. It describes folders; it never decides which exist. A sync creates it from the folders and adds an entry for each new folder; it never changes an entry the user wrote.
_Avoid_: Library config, taxonomy file, template

**Taxonomy**:
The library's groups and, within each, its categories, read from the folders that already exist. It also records the library's depth.

**Flat library**:
A library with one level of folders (`depth = 1`): groups only, with documents filed straight into a group.
_Avoid_: Single-level library, groups-only library
_Avoid_: Schema, category list

**Unit**:
What gets filed as one piece: a single document, or a whole folder of documents kept together.
_Avoid_: Item, entry

### Deciding where things go

**Classification**:
The decision for a unit: which group, which category, how confident, and why.
_Avoid_: Prediction, label

**Resolver**:
Something that proposes a group, or a category within a group, for a document.
_Avoid_: Classifier (the classifier combines resolvers), matcher

**Hint**:
A keyword whose appearance in a document suggests a category.
_Avoid_: Tag, keyword list

**Filing rule**:
A filename pattern that sends a matching file to a category before hints are tried.
_Avoid_: Naming rule (that one renames files), route

**Unreadable document**:
A supported file that can't be opened — corrupt, say — so it can't be classified; it is left for review and never stops the rest of a run.
_Avoid_: Failed file, bad file

**Collision**:
A unit's destination name is already taken by a different file, so the unit is left in the inbox for review with the reason; nothing is renamed or overwritten.
_Avoid_: Conflict (that is `reclassify`'s name for the same clash), clash

**Duplicate**:
An inbox file whose content is identical to a file already in the library, or to another inbox file being filed in the same run. It is classified like any other, then left in the inbox with a note of where the copy is and, if the classifier would file it elsewhere, where. Only new files are checked: copies already inside the library are normal and never reported.
_Avoid_: Copy, clone, collision (a collision is a clash of names, not of content)

**Confidence**:
How sure a classification is, from 0 to 1; a classification is only as confident as its weaker stage.
_Avoid_: Score, probability

**Confidence threshold**:
The confidence a classification must reach before microfiche files a unit on its own.
_Avoid_: Cutoff, minimum score

**Review**:
Where a unit goes when it can't be filed confidently — it stays in the inbox for a person to decide.
_Avoid_: Quarantine, rejected

**Reclassify**:
Re-deciding where documents already in the library belong, and optionally moving them.
_Avoid_: Resort, reorganise

### Keeping a record

**Dry run**:
A `sort` that classifies and checks everything as usual but moves and records nothing, so you can see what a real run would do first. The output is labelled a preview.
_Avoid_: Simulation, test run

**Run lock**:
The `lock` file in the state folder that a run holds while it changes the library, so a second run refuses to start; a lock left by a process that has gone is cleared, with a warning.
_Avoid_: Mutex, semaphore

**Job**:
One run of filing — every move it made, kept so the whole run can be undone together.
_Avoid_: Batch, transaction, run

**Rollback**:
Undoing a job by moving everything it moved back to where it was.
_Avoid_: Revert, undo (in code)

**Ledger**:
The permanent record of what was filed where and why, which outlives any single job.
_Avoid_: Metadata, sidecar, index

**Audit log**:
The readable, line-per-move history of everything microfiche has done.
_Avoid_: Changelog, history

**Log**:
The diagnostic record in `.microfiche/microfiche.log` that explains what a run did and why, for the person troubleshooting it. It never holds document text, and nothing reads it back, unlike the ledger and the audit log, which `rollback` and `audit` rely on.
_Avoid_: Debug file, trace
