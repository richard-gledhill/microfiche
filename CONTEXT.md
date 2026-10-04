# microfiche

Files loose documents into a library of group and category folders, deciding where each belongs and
recording every move so it can be undone.

## Language

### The library

**Library**:
The folder microfiche manages: an inbox plus two levels of folders, group then category.
_Avoid_: Vault, repository, archive

**Inbox**:
The single library-wide folder where new documents are dropped to be sorted; it is `_sorting` unless the library names another.
_Avoid_: Queue, drop folder, staging area

**Group**:
A top-level folder of the library — what a document belongs to, such as a project, client or course.
_Avoid_: Project (a project is only one thing a group can be), folder, bucket

**Category**:
A folder inside a group, where a document actually lands — such as a document type or a stage of work.
_Avoid_: Subfolder, tag, label

**State folder**:
The hidden folder inside a library where microfiche keeps its config and its own records.
_Avoid_: Data directory, config folder, logs folder

**Taxonomy**:
The library's groups and, within each, its categories, read from the folders that already exist.
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

**Unreadable document**:
A supported file that can't be opened — corrupt, say — so it can't be classified; it is left for review and never stops the rest of a run.
_Avoid_: Failed file, bad file

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
