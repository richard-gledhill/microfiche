"""Tests for the library file: the folder tree of hints and filename rules, and how it is looked up."""

import json
from pathlib import Path
from typing import Any

import pytest
from core.library.library_file import (
    DuplicateFolderError,
    FilingRule,
    FolderNode,
    LibraryFile,
    WildcardWithDataError,
    json_schema,
)
from pydantic import ValidationError

# region Test helpers


_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_DIR = _REPO_ROOT / "microfiche"

_CATEGORIES = ["01 Requirements", "02 Architecture", "03 Research"]


def _file(*groups: dict[str, Any]) -> LibraryFile:
    return LibraryFile.model_validate({"groups": list(groups)})


def _node(name: str, **fields: Any) -> dict[str, Any]:
    return {"name": name, **fields}


def _shared_and_phoenix() -> LibraryFile:
    """Hints for every group via ``*``, plus a Project Phoenix entry that adds to them."""

    return _file(
        _node(
            "*",
            children=[
                _node(
                    "01 Requirements",
                    hints=["requirement", "user story"],
                    rules=[{"pattern": "requirements*.docx"}],
                ),
                _node(
                    "02 Architecture",
                    hints=["architecture", "system diagram"],
                    rules=[{"pattern": "architecture*.pdf"}],
                ),
            ],
        ),
        _node(
            "Project Phoenix",
            children=[
                _node("02 Architecture", hints=["adr", "system diagram"], rules=[{"pattern": "adr-*"}]),
            ],
        ),
    )


# endregion


# region Constants and types


# region FilingRule


def test_filing_rule_blank_pattern_rejected() -> None:
    with pytest.raises(ValidationError, match="pattern"):
        FilingRule(pattern="   ")


def test_filing_rule_pattern_whitespace_trimmed() -> None:
    assert FilingRule(pattern="  requirements*.docx ").pattern == "requirements*.docx"


def test_filing_rule_unsupported_option_rejected() -> None:
    # Only a case-insensitive glob on the file name is supported; regex or path rules are not accepted silently.
    with pytest.raises(ValidationError) as exc_info:
        FilingRule.model_validate({"pattern": "a*", "type": "regex"})

    [error] = exc_info.value.errors()
    assert (error["type"], error["loc"]) == ("extra_forbidden", ("type",))


# endregion


# region FolderNode


@pytest.mark.parametrize("name", ["a/b", "a\\b"])
def test_folder_node_name_with_path_separator_rejected(name: str) -> None:
    with pytest.raises(ValidationError, match="name"):
        FolderNode(name=name)


def test_folder_node_blank_name_rejected() -> None:
    with pytest.raises(ValidationError, match="name"):
        FolderNode(name="  ")


def test_folder_node_missing_name_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        FolderNode.model_validate({"hints": ["x"]})

    assert exc_info.value.errors()[0]["type"] == "missing"


def test_folder_node_name_whitespace_trimmed() -> None:
    assert FolderNode(name=" 01 Requirements ").name == "01 Requirements"


def test_folder_node_blank_hint_rejected() -> None:
    # An empty hint would match every document.
    with pytest.raises(ValidationError, match="hints"):
        FolderNode(name="A", hints=["ok", " "])


def test_folder_node_hint_whitespace_trimmed() -> None:
    assert FolderNode(name="A", hints=[" user story "]).hints == ["user story"]


def test_folder_node_misspelt_key_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        FolderNode.model_validate({"name": "A", "hint": ["x"]})

    [error] = exc_info.value.errors()
    assert (error["type"], error["loc"]) == ("extra_forbidden", ("hint",))


def test_folder_node_defaults_are_empty() -> None:
    node = FolderNode(name="A")

    assert (node.hints, node.rules, node.children, node.description) == ([], [], [], None)


def test_folder_node_description_kept() -> None:
    assert FolderNode(name="A", description="Specs and user stories.").description == "Specs and user stories."


def test_folder_node_blank_description_rejected() -> None:
    with pytest.raises(ValidationError, match="description"):
        FolderNode(name="A", description=" ")


def test_folder_node_duplicate_children_rejected_ignoring_case() -> None:
    with pytest.raises(ValidationError, match="more than once"):
        FolderNode.model_validate({"name": "A", "children": [{"name": "Notes"}, {"name": "notes"}]})


@pytest.mark.parametrize("data", [{"hints": ["x"]}, {"rules": [{"pattern": "a*"}]}])
def test_folder_node_wildcard_with_hints_or_rules_rejected(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="'\\*'"):
        FolderNode.model_validate({"name": "*", **data})


def test_folder_node_wildcard_with_children_and_description_accepted() -> None:
    node = FolderNode.model_validate({"name": "*", "description": "Every group", "children": [{"name": "A"}]})

    assert node.children[0].name == "A"


def test_folder_node_height_counts_levels_below() -> None:
    node = FolderNode.model_validate({"name": "A", "children": [{"name": "B", "children": [{"name": "C"}]}]})

    assert (FolderNode(name="A").height(), node.height()) == (1, 3)


# endregion


# region LibraryFile


def test_library_file_empty_object_has_no_groups() -> None:
    library_file = LibraryFile.model_validate({})

    assert library_file.groups == []


def test_library_file_schema_key_accepted() -> None:
    library_file = LibraryFile.model_validate({"$schema": "./microfiche-library.schema.json"})

    assert library_file.schema_ref == "./microfiche-library.schema.json"


def test_library_file_misspelt_root_key_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        LibraryFile.model_validate({"group": []})

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"


def test_library_file_version_key_rejected_as_unknown() -> None:
    with pytest.raises(ValidationError) as exc_info:
        LibraryFile.model_validate({"version": 1})

    [error] = exc_info.value.errors()
    assert (error["type"], error["loc"]) == ("extra_forbidden", ("version",))


def test_library_file_duplicate_groups_rejected_ignoring_case() -> None:
    with pytest.raises(ValidationError, match="more than once"):
        _file(_node("Project Phoenix"), _node("project phoenix"))


def test_library_file_height_empty_is_zero() -> None:
    assert _file().height() == 0


def test_library_file_height_spans_deepest_branch() -> None:
    library_file = _file(_node("A"), _node("B", children=[_node("C")]))

    assert library_file.height() == 2


# region LibraryFile.hints_for


def test_hints_for_named_entry_returns_its_hints() -> None:
    library_file = _file(_node("A", children=[_node("Notes", hints=["note", "memo"])]))

    assert library_file.hints_for("A", "Notes") == ["note", "memo"]


def test_hints_for_wildcard_group_applies_to_every_group() -> None:
    library_file = _shared_and_phoenix()

    assert library_file.hints_for("Project Atlas", "01 Requirements") == ["requirement", "user story"]
    assert library_file.hints_for("Project Phoenix", "01 Requirements") == ["requirement", "user story"]


def test_hints_for_group_entry_comes_before_wildcard_and_repeats_dropped() -> None:
    # Project Phoenix's own hints first, then the shared ones; "system diagram" is in both and appears once.
    hints = _shared_and_phoenix().hints_for("Project Phoenix", "02 Architecture")

    assert hints == ["adr", "system diagram", "architecture"]


def test_hints_for_ignores_case_of_group_and_category() -> None:
    assert _shared_and_phoenix().hints_for("project phoenix", "02 ARCHITECTURE")[0] == "adr"


def test_hints_for_unknown_group_or_category_returns_nothing() -> None:
    library_file = _file(_node("A", children=[_node("Notes", hints=["note"])]))

    assert library_file.hints_for("B", "Notes") == []
    assert library_file.hints_for("A", "Other") == []


def test_hints_for_empty_file_returns_nothing() -> None:
    assert _file().hints_for("A", "Notes") == []


# endregion


# region LibraryFile.rules_for


def test_rules_for_returns_pattern_and_category_pairs() -> None:
    rules = _shared_and_phoenix().rules_for("Project Atlas", _CATEGORIES)

    assert rules == [
        {"pattern": "requirements*.docx", "category": "01 Requirements"},
        {"pattern": "architecture*.pdf", "category": "02 Architecture"},
    ]


def test_rules_for_group_entry_comes_before_wildcard() -> None:
    rules = _shared_and_phoenix().rules_for("Project Phoenix", _CATEGORIES)

    assert [rule["pattern"] for rule in rules] == ["adr-*", "requirements*.docx", "architecture*.pdf"]


def test_rules_for_other_groups_do_not_get_a_groups_own_rules() -> None:
    rules = _shared_and_phoenix().rules_for("Project Atlas", _CATEGORIES)

    assert "adr-*" not in [rule["pattern"] for rule in rules]


def test_rules_for_same_specificity_keeps_file_order_not_folder_order() -> None:
    # The old global rules list was checked in file order; "zeta" is listed first and must stay first.
    library_file = _file(
        _node(
            "*",
            children=[
                _node("Zeta", rules=[{"pattern": "report*"}]),
                _node("Alpha", rules=[{"pattern": "report*"}]),
            ],
        )
    )

    rules = library_file.rules_for("A", ["Alpha", "Zeta"])

    assert [rule["category"] for rule in rules] == ["Zeta", "Alpha"]


def test_rules_for_only_categories_given_are_considered() -> None:
    rules = _shared_and_phoenix().rules_for("Project Atlas", ["01 Requirements"])

    assert [rule["category"] for rule in rules] == ["01 Requirements"]


def test_rules_for_keeps_a_nodes_rules_in_order() -> None:
    library_file = _file(
        _node("A", children=[_node("Notes", rules=[{"pattern": "first*"}, {"pattern": "second*"}])]),
    )

    assert [rule["pattern"] for rule in library_file.rules_for("A", ["Notes"])] == ["first*", "second*"]


# endregion


# endregion


# endregion


# region Errors


def test_errors_name_what_is_wrong() -> None:
    assert "'Notes'" in str(DuplicateFolderError("Notes"))
    assert "hints or rules" in str(WildcardWithDataError())


# endregion


# region Public API


# region json_schema


def test_json_schema_matches_committed_schema_file() -> None:
    """Regenerate ``microfiche/microfiche-library.schema.json`` from ``json_schema()`` if the model changes."""

    committed = json.loads((_TEMPLATE_DIR / "microfiche-library.schema.json").read_text(encoding="utf-8"))

    assert json_schema() == committed


def test_json_schema_rejects_unknown_keys_and_requires_name() -> None:
    schema = json_schema()

    assert schema["additionalProperties"] is False
    assert schema["$defs"]["FolderNode"]["additionalProperties"] is False
    assert schema["$defs"]["FolderNode"]["required"] == ["name"]


# endregion


# region Template file


def test_template_library_file_is_valid_and_matches_the_old_template_config() -> None:
    template = LibraryFile.model_validate_json((_TEMPLATE_DIR / "microfiche-library.json").read_text(encoding="utf-8"))
    categories = ["01 Requirements", "02 Architecture", "03 Research", "04 Meeting Notes", "05 Correspondence"]

    assert template.hints_for("Any Group", "01 Requirements") == ["requirement", "user story", "acceptance criteria"]
    assert template.hints_for("Any Group", "05 Correspondence") == ["email", "correspondence"]
    assert template.rules_for("Any Group", categories) == [
        {"pattern": "requirements*.docx", "category": "01 Requirements"},
        {"pattern": "architecture*.pdf", "category": "02 Architecture"},
        {"pattern": "meeting-notes*", "category": "04 Meeting Notes"},
    ]
    assert template.height() <= 2


# endregion


# endregion
