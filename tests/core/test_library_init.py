"""Tests for setting up, checking and editing a library's configuration (``microfiche init``)."""

import json
import tomllib
from pathlib import Path

import pytest
from microfiche.core.config import CONFIG_FILENAME, ConfigProblem, load_config, packaged_defaults_text
from microfiche.core.library.library import Library
from microfiche.core.library.library_file import LIBRARY_FILENAME
from microfiche.core.library_init import (
    COMMON_SETTINGS,
    BackupExistsError,
    ConfigChangedError,
    ConfigEditor,
    InstallState,
    InvalidSettingValueError,
    NotTomlError,
    SettingChange,
    create_inbox,
    inspect_install,
    install_defaults,
    rebuild_library_file,
)

# region Test helpers


_CUSTOM = """\
# My library's settings.
[classification]
# Stricter than the default.
confidence_threshold = 0.8  # chosen after a bad week

[sorting]
keep_folders = false
"""


def _state_dir(tmp_path: Path, text: str | None = _CUSTOM) -> Path:
    """A library's state folder holding ``text`` as its config, or no config when ``text`` is ``None``."""

    state_dir = tmp_path / ".microfiche"
    state_dir.mkdir()
    if text is not None:
        (state_dir / CONFIG_FILENAME).write_bytes(text.encode("utf-8"))
    return state_dir


def _config_bytes(state_dir: Path) -> bytes:
    return (state_dir / CONFIG_FILENAME).read_bytes()


def _invalid(state_dir: Path) -> tuple[ConfigProblem, ...]:
    check = inspect_install(state_dir)
    assert check.state is InstallState.INVALID
    return check.problems


# endregion


# region Public API


# region inspect_install


def test_inspect_install_no_config_missing(tmp_path: Path) -> None:
    assert inspect_install(tmp_path / ".microfiche").state is InstallState.MISSING


def test_inspect_install_valid_config_valid(tmp_path: Path) -> None:
    check = inspect_install(_state_dir(tmp_path))

    assert check.state is InstallState.VALID
    assert check.problems == ()


def test_inspect_install_invalid_config_lists_problems(tmp_path: Path) -> None:
    check = inspect_install(_state_dir(tmp_path, "[classification]\nconfidence_threshold = 2\n"))

    assert check.state is InstallState.INVALID
    assert [problem.place for problem in check.problems] == ["classification.confidence_threshold"]
    assert check.error is not None
    assert "confidence_threshold" in str(check.error)


def test_inspect_install_not_toml_invalid_without_problems(tmp_path: Path) -> None:
    check = inspect_install(_state_dir(tmp_path, "[classification\n"))

    assert check.state is InstallState.INVALID
    assert check.problems == ()


# endregion


# region install_defaults


def test_install_defaults_writes_packaged_defaults(tmp_path: Path) -> None:
    state_dir = tmp_path / ".microfiche"

    path = install_defaults(state_dir)

    assert path == state_dir / CONFIG_FILENAME
    assert path.read_text(encoding="utf-8") == packaged_defaults_text()
    load_config(state_dir)


def test_install_defaults_existing_config_refused(tmp_path: Path) -> None:
    state_dir = _state_dir(tmp_path)

    with pytest.raises(FileExistsError):
        install_defaults(state_dir)

    assert _config_bytes(state_dir) == _CUSTOM.encode()


# endregion


# region create_inbox


def test_create_inbox_missing_created(tmp_path: Path) -> None:
    created = create_inbox(Library(tmp_path))

    assert created == tmp_path / "_sorting"
    assert created.is_dir()


def test_create_inbox_existing_left_alone(tmp_path: Path) -> None:
    (tmp_path / "_sorting").mkdir()

    assert create_inbox(Library(tmp_path)) is None


# endregion


# region rebuild_library_file


def test_rebuild_library_file_moves_old_aside_and_lists_folders(tmp_path: Path) -> None:
    state_dir = _state_dir(tmp_path)
    (state_dir / LIBRARY_FILENAME).write_text("{not json", encoding="utf-8")
    (tmp_path / "Project" / "Notes").mkdir(parents=True)

    backup, sync = rebuild_library_file(Library(tmp_path))

    assert backup.read_text(encoding="utf-8") == "{not json"
    assert sync.added == ["Project", "Project/Notes"]
    assert json.loads((state_dir / LIBRARY_FILENAME).read_text(encoding="utf-8"))["groups"][0]["name"] == "Project"


# endregion


# region ConfigEditor: settings


def test_config_editor_settings_every_packaged_setting_in_order(tmp_path: Path) -> None:
    settings = ConfigEditor(_state_dir(tmp_path)).settings()

    assert settings[0].key == "library_structure.library_inbox"
    assert {setting.section for setting in settings} == {
        "library_structure",
        "classification",
        "ai",
        "sorting",
        "parsing",
        "logging",
        "exclusions",
        "naming_rules",
    }


def test_config_editor_setting_current_default_and_help(tmp_path: Path) -> None:
    setting = ConfigEditor(_state_dir(tmp_path)).setting("classification", "confidence_threshold")

    assert setting.value == 0.8
    assert setting.default == 0.75
    assert setting.help.startswith("A document files without asking")


def test_config_editor_setting_unset_shows_default(tmp_path: Path) -> None:
    setting = ConfigEditor(_state_dir(tmp_path)).setting("ai", "provider")

    assert setting.value == setting.default == "ollama"


def test_config_editor_naming_rules_not_editable(tmp_path: Path) -> None:
    editor = ConfigEditor(_state_dir(tmp_path))

    assert not editor.setting("naming_rules", "rules").editable
    assert editor.setting("sorting", "ignore").editable


def test_common_settings_all_exist(tmp_path: Path) -> None:
    editor = ConfigEditor(_state_dir(tmp_path))

    assert [editor.setting(*key).key for key in COMMON_SETTINGS] == [
        "classification.confidence_threshold",
        "library_structure.depth",
        "library_structure.library_inbox",
        "sorting.keep_folders",
        "ai.provider",
        "ai.model",
    ]


# endregion


# region ConfigEditor: parse


@pytest.mark.parametrize(
    ("key", "raw", "expected"),
    [
        (("sorting", "keep_folders"), "y", True),
        (("sorting", "keep_folders"), "No", False),
        (("library_structure", "depth"), "1", 1),
        (("classification", "confidence_threshold"), "0.9", 0.9),
        (("classification", "confidence_threshold"), "1", 1),
        (("ai", "model"), "llama3", "llama3"),
        (("ai", "model"), "-", ""),
        (("sorting", "ignore"), "*.bak, ~$*", ["*.bak", "~$*"]),
        (("sorting", "ignore"), "-", []),
    ],
)
def test_config_editor_parse_typed_by_default(tmp_path: Path, key: tuple[str, str], raw: str, expected: object) -> None:
    editor = ConfigEditor(_state_dir(tmp_path))

    assert editor.parse(editor.setting(*key), raw) == expected


@pytest.mark.parametrize(
    ("key", "raw"),
    [
        (("sorting", "keep_folders"), "maybe"),
        (("library_structure", "depth"), "two"),
        (("parsing", "max_file_mb"), "x"),
    ],
)
def test_config_editor_parse_wrong_type_rejected(tmp_path: Path, key: tuple[str, str], raw: str) -> None:
    editor = ConfigEditor(_state_dir(tmp_path))

    with pytest.raises(InvalidSettingValueError):
        editor.parse(editor.setting(*key), raw)


# endregion


# region ConfigEditor: set and changes


def test_config_editor_nothing_set_unchanged(tmp_path: Path) -> None:
    editor = ConfigEditor(_state_dir(tmp_path))

    assert not editor.changed
    assert editor.changes() == []


def test_config_editor_same_value_unchanged(tmp_path: Path) -> None:
    editor = ConfigEditor(_state_dir(tmp_path))

    editor.set("classification", "confidence_threshold", 0.8)
    editor.set("ai", "provider", "ollama")  # unset, and set to its default: still no change

    assert not editor.changed


def test_config_editor_set_rewrites_only_that_value(tmp_path: Path) -> None:
    editor = ConfigEditor(_state_dir(tmp_path))

    editor.set("classification", "confidence_threshold", 0.9)

    assert editor.text == _CUSTOM.replace("0.8  #", "0.9  #")
    assert editor.changes() == [SettingChange("classification.confidence_threshold", "0.8", "0.9")]


def test_config_editor_set_unset_setting_added_to_its_section(tmp_path: Path) -> None:
    editor = ConfigEditor(_state_dir(tmp_path))

    editor.set("sorting", "ignore", ["*.bak"])
    editor.set("ai", "model", "llama3")

    assert 'keep_folders = false\nignore = ["*.bak"]\n' in editor.text
    assert editor.text.endswith('[ai]\nmodel = "llama3"\n')
    assert editor.changes() == [
        SettingChange("sorting.ignore", "(not set)", '["*.bak"]'),
        SettingChange("ai.model", "(not set)", '"llama3"'),
    ]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        (("classification", "confidence_threshold"), 1.5),
        (("library_structure", "depth"), 3),
        (("library_structure", "library_inbox"), "a/b"),
        (("logging", "level"), "LOUD"),
    ],
)
def test_config_editor_set_invalid_value_rejected(tmp_path: Path, key: tuple[str, str], value: object) -> None:
    editor = ConfigEditor(_state_dir(tmp_path))

    with pytest.raises(InvalidSettingValueError, match=key[1]):
        editor.set(*key, value)

    assert not editor.changed


def test_config_editor_set_breaks_section_rule_rejected(tmp_path: Path) -> None:
    editor = ConfigEditor(_state_dir(tmp_path, '[ai]\nhost = "http://box:11434"\n'))

    with pytest.raises(InvalidSettingValueError, match="host is only used by the ollama provider"):
        editor.set("ai", "provider", "openai")


def test_config_editor_set_sees_earlier_changes(tmp_path: Path) -> None:
    editor = ConfigEditor(_state_dir(tmp_path, '[ai]\nhost = "http://box:11434"\n'))

    editor.set("ai", "host", "")
    editor.set("ai", "provider", "openai")

    assert tomllib.loads(editor.text)["ai"]["provider"] == "openai"


# endregion


# region ConfigEditor: revert


def test_config_editor_revert_invalid_keeps_valid_custom_settings(tmp_path: Path) -> None:
    state_dir = _state_dir(
        tmp_path,
        "# Mine.\n[classification]\nconfidence_threshold = 0.8\nfuzzy_group_threshold = 500\n\n"
        "[classifcation]\nx = 1\n\n[sorting]\nkeep_folders = false\nkeep_foldrs = true\n",
    )
    editor = ConfigEditor(state_dir)

    editor.revert_invalid(_invalid(state_dir))

    assert editor.problems() == ()
    assert editor.text == (
        "# Mine.\n[classification]\nconfidence_threshold = 0.8\nfuzzy_group_threshold = 85\n\n"
        "[sorting]\nkeep_folders = false\n"
    )


def test_config_editor_revert_invalid_list_item(tmp_path: Path) -> None:
    state_dir = _state_dir(tmp_path, '[exclusions]\nexclude = ["a", 1]\n')
    editor = ConfigEditor(state_dir)

    editor.revert_invalid(_invalid(state_dir))

    assert editor.text == '[exclusions]\nexclude = ["sorting*", "_sorting*", ".*", "_*", "attachments"]\n'


def test_config_editor_revert_invalid_section_not_table_removed(tmp_path: Path) -> None:
    state_dir = _state_dir(tmp_path, "classification = 5\n\n[sorting]\nkeep_folders = false\n")
    editor = ConfigEditor(state_dir)

    editor.revert_invalid(_invalid(state_dir))

    assert editor.problems() == ()
    assert editor.text == "\n[sorting]\nkeep_folders = false\n"


def test_config_editor_revert_invalid_host_rule_resets_host(tmp_path: Path) -> None:
    state_dir = _state_dir(tmp_path, '[ai]\nprovider = "openai"\nhost = "x"\n')
    editor = ConfigEditor(state_dir)

    editor.revert_invalid(_invalid(state_dir))

    assert editor.text == '[ai]\nprovider = "openai"\nhost = ""\n'


def test_config_editor_revert_all_packaged_defaults(tmp_path: Path) -> None:
    editor = ConfigEditor(_state_dir(tmp_path, "[classification\n"))

    assert not editor.parsed
    editor.revert_all()

    assert editor.parsed
    assert editor.text == packaged_defaults_text()
    assert editor.changed


def test_config_editor_not_toml_only_revert_all(tmp_path: Path) -> None:
    editor = ConfigEditor(_state_dir(tmp_path, "[classification\n"))

    assert editor.text == "[classification\n"
    assert editor.changes() == []
    with pytest.raises(NotTomlError):
        editor.set("ai", "model", "x")
    with pytest.raises(NotTomlError):
        editor.problems()


def test_config_editor_problems_of_edited_document(tmp_path: Path) -> None:
    editor = ConfigEditor(_state_dir(tmp_path, "[classification]\nconfidence_threshold = 2\n"))

    assert [problem.place for problem in editor.problems()] == ["classification.confidence_threshold"]


def test_config_editor_revert_invalid_unknown_section_reported_as_removed(tmp_path: Path) -> None:
    state_dir = _state_dir(tmp_path, "[classifcation]\nx = 1\n")
    editor = ConfigEditor(state_dir)
    problems = _invalid(state_dir)

    editor.revert_invalid(problems)
    editor.revert_invalid(problems)  # what is already gone is skipped

    assert editor.text == ""
    assert editor.changes() == [SettingChange("classifcation.x", "1", "(removed)")]


def test_config_editor_set_valid_despite_problem_elsewhere(tmp_path: Path) -> None:
    # Only a problem at the setting being changed rejects it.
    editor = ConfigEditor(_state_dir(tmp_path, "[classification]\nconfidence_threshold = 2\n"))

    editor.set("ai", "model", "llama3")

    assert 'model = "llama3"' in editor.text


def test_config_editor_unknown_setting_key_error(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        ConfigEditor(_state_dir(tmp_path)).setting("ai", "colour")


# endregion


# region ConfigEditor: save


def test_config_editor_save_unchanged_writes_nothing(tmp_path: Path) -> None:
    state_dir = _state_dir(tmp_path)

    assert ConfigEditor(state_dir).save() is None

    assert _config_bytes(state_dir) == _CUSTOM.encode()
    assert not (state_dir / f"{CONFIG_FILENAME}.bak").exists()


def test_config_editor_save_writes_and_keeps_backup(tmp_path: Path) -> None:
    state_dir = _state_dir(tmp_path)
    editor = ConfigEditor(state_dir)
    editor.set("sorting", "keep_folders", True)

    backup = editor.save()

    assert backup == state_dir / f"{CONFIG_FILENAME}.bak"
    assert backup.read_bytes() == _CUSTOM.encode()
    assert load_config(state_dir).sorting.keep_folders is True
    assert not list(state_dir.glob("*.tmp"))


def test_config_editor_save_existing_backup_refused_unless_replaced(tmp_path: Path) -> None:
    state_dir = _state_dir(tmp_path)
    (state_dir / f"{CONFIG_FILENAME}.bak").write_text("older", encoding="utf-8")
    editor = ConfigEditor(state_dir)
    editor.set("sorting", "keep_folders", True)

    with pytest.raises(BackupExistsError):
        editor.save()
    assert _config_bytes(state_dir) == _CUSTOM.encode()

    editor.save(replace_backup=True)
    assert (state_dir / f"{CONFIG_FILENAME}.bak").read_bytes() == _CUSTOM.encode()


def test_config_editor_save_without_backup_leaves_existing_one(tmp_path: Path) -> None:
    # A second write in the same init run keeps the backup of the original file.
    state_dir = _state_dir(tmp_path)
    (state_dir / f"{CONFIG_FILENAME}.bak").write_bytes(b"original")
    editor = ConfigEditor(state_dir)
    editor.set("sorting", "keep_folders", True)

    assert editor.save(backup=False) is None

    assert load_config(state_dir).sorting.keep_folders is True
    assert (state_dir / f"{CONFIG_FILENAME}.bak").read_bytes() == b"original"


def test_config_editor_save_file_changed_meanwhile_refused(tmp_path: Path) -> None:
    state_dir = _state_dir(tmp_path)
    editor = ConfigEditor(state_dir)
    editor.set("sorting", "keep_folders", True)
    (state_dir / CONFIG_FILENAME).write_bytes(b"# edited by hand\n")

    with pytest.raises(ConfigChangedError):
        editor.save()

    assert _config_bytes(state_dir) == b"# edited by hand\n"


def test_config_editor_save_crlf_file_stays_crlf(tmp_path: Path) -> None:
    state_dir = _state_dir(tmp_path, _CUSTOM.replace("\n", "\r\n"))
    editor = ConfigEditor(state_dir)
    editor.set("ai", "model", "llama3")

    editor.save()

    written = _config_bytes(state_dir)
    assert written.count(b"\n") == written.count(b"\r\n")
    assert b'model = "llama3"' in written


# endregion


# endregion
