# Plan: empty-group filing

1. `Taxonomy.is_leaf`; `file_in_empty_groups` setting; `attachments` default (tests first).
2. `Classifier` leaf handling and AI skip; `from_library` passes the setting.
3. `ReviewSession` place rule and prompt; run summaries count the leaf filings.
4. `reclassify` test; docs, example config, sample library; `make check`/`make test`; PR.
