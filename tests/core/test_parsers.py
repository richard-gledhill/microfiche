"""Tests for the document parsers: dispatch, each format, and what happens when a file can't be read."""

from pathlib import Path

import docx
import pymupdf
import pytest
from core.parsers import (
    SUPPORTED_EXTENSIONS,
    UnreadableDocumentError,
    UnsupportedFormatError,
    is_supported,
    parse_document,
    read_documents,
)
from core.parsers.base import document_from

# region Test helpers


_EML = (
    b"From: Ada <ada@example.com>\r\n"
    b"To: Grace <grace@example.com>\r\n"
    b"Subject: Quarterly plan\r\n"
    b"Date: Mon, 05 Oct 2026 09:00:00 +0000\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"Please review the plan.\r\n"
)


def _write(path: Path, data: bytes | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_bytes(data)
    return path


def _make_docx(path: Path, *paragraphs: str) -> Path:
    document = docx.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(str(path))
    return path


def _make_pdf(path: Path, text: str) -> Path:
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), text)
    pdf.save(str(path))
    pdf.close()
    return path


# endregion


# region Which formats are supported


def test_supported_extensions() -> None:
    assert {".pdf", ".docx", ".txt", ".md", ".markdown", ".msg", ".eml"} == SUPPORTED_EXTENSIONS


@pytest.mark.parametrize("name", ["a.pdf", "a.DOCX", "a.Txt", "a.md", "a.markdown", "a.msg", "a.EML"])
def test_is_supported_ignores_case(name: str) -> None:
    assert is_supported(Path(name)) is True


@pytest.mark.parametrize("name", ["photo.png", "sheet.xlsx", "noextension", "archive.tar.gz", ".md.bak"])
def test_is_supported_other_files_false(name: str) -> None:
    assert is_supported(Path(name)) is False


def test_parse_document_unsupported_file_raises(tmp_path: Path) -> None:
    path = _write(tmp_path / "photo.png", b"\x89PNG")

    with pytest.raises(UnsupportedFormatError) as excinfo:
        parse_document(path)

    assert excinfo.value.path == path
    assert ".png" in str(excinfo.value)


# endregion


# region Each format


def test_parse_document_text_file_reads_header_fields(tmp_path: Path) -> None:
    path = _write(tmp_path / "NOTES.TXT", "Hello world")

    document = parse_document(path)

    assert document.content == "Hello world"
    assert document.file_path == path
    assert document.file_name == "NOTES.TXT"
    assert document.extension == ".txt"  # lowercased
    assert document.metadata == {}


@pytest.mark.parametrize("name", ["a.md", "a.markdown"])
def test_parse_document_markdown_read_as_text(tmp_path: Path, name: str) -> None:
    document = parse_document(_write(tmp_path / name, "# Title\n\nBody"))

    assert document.content == "# Title\n\nBody"
    assert document.extension == Path(name).suffix


def test_parse_document_undecodable_bytes_replaced(tmp_path: Path) -> None:
    path = _write(tmp_path / "latin1.txt", b"caf\xe9 society")

    document = parse_document(path)

    assert document.content.startswith("caf")
    assert "society" in document.content


def test_parse_document_eml_gives_body_and_headers(tmp_path: Path) -> None:
    document = parse_document(_write(tmp_path / "plan.eml", _EML))

    assert document.content.strip() == "Please review the plan."
    assert document.metadata == {
        "sender": "Ada <ada@example.com>",
        "to": "Grace <grace@example.com>",
        "subject": "Quarterly plan",
        "date": "Mon, 05 Oct 2026 09:00:00 +0000",
    }


def test_parse_document_empty_eml_readable_without_content(tmp_path: Path) -> None:
    document = parse_document(_write(tmp_path / "empty.eml", b""))

    assert document.content == ""
    assert document.metadata["subject"] == ""


def test_parse_document_docx_gives_paragraphs(tmp_path: Path) -> None:
    document = parse_document(_make_docx(tmp_path / "spec.docx", "First paragraph", "Second paragraph"))

    assert document.content == "First paragraph\nSecond paragraph"
    assert document.extension == ".docx"


def test_parse_document_pdf_gives_text_and_metadata(tmp_path: Path) -> None:
    document = parse_document(_make_pdf(tmp_path / "report.pdf", "Quarterly report"))

    assert "Quarterly report" in document.content
    assert document.metadata.get("format", "").startswith("PDF")


def test_parse_document_pdf_without_text_layer_empty(tmp_path: Path) -> None:
    """Scanned (image-only) PDFs aren't OCRed, so they read as empty text and end up in review."""

    path = tmp_path / "scanned.pdf"
    pdf = pymupdf.open()
    pdf.new_page()
    pdf.save(str(path))
    pdf.close()

    assert parse_document(path).content == ""


def test_parse_document_password_protected_pdf_unreadable(tmp_path: Path) -> None:
    path = tmp_path / "locked.pdf"
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "secret")
    pdf.save(str(path), encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="user", owner_pw="owner")
    pdf.close()

    with pytest.raises(UnreadableDocumentError) as excinfo:
        parse_document(path)

    assert excinfo.value.path == path


# endregion


# region Files that can't be read


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("bad.docx", b"this is not a zip file"),
        ("bad.pdf", b"%PDF-garbage"),
        ("bad.msg", b"not an OLE2 structured storage file"),
    ],
)
def test_parse_document_corrupt_raises_unreadable_with_cause(tmp_path: Path, name: str, data: bytes) -> None:
    path = _write(tmp_path / name, data)

    with pytest.raises(UnreadableDocumentError) as excinfo:
        parse_document(path)

    assert excinfo.value.path == path
    assert excinfo.value.reason
    assert name in str(excinfo.value)
    assert excinfo.value.__cause__ is not None
    assert type(excinfo.value.__cause__).__name__ in excinfo.value.reason


def test_parse_document_unreadable_reason_one_line(tmp_path: Path) -> None:
    path = _write(tmp_path / "bad.docx", b"junk")

    with pytest.raises(UnreadableDocumentError) as excinfo:
        parse_document(path)

    assert "\n" not in excinfo.value.reason
    assert len(excinfo.value.reason) <= 200


def test_parse_document_missing_file_unreadable(tmp_path: Path) -> None:
    with pytest.raises(UnreadableDocumentError):
        parse_document(tmp_path / "gone.txt")


# endregion


# region Files that are too big


def test_parse_document_over_max_bytes_unreadable_without_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    big = tmp_path / "big.txt"
    big.write_bytes(b"x" * 3 * 1024 * 1024)
    monkeypatch.setattr("core.parsers.registry._PARSERS", {".txt": _must_not_run})

    with pytest.raises(UnreadableDocumentError) as raised:
        parse_document(big, max_bytes=2 * 1024 * 1024)

    assert raised.value.reason == "it is 3.0 MB, over the 2 MB limit ([parsing] max_file_mb)"


def _must_not_run(path: Path) -> object:
    pytest.fail(f"{path} should not have been opened")


def test_parse_document_exactly_max_bytes_is_read(tmp_path: Path) -> None:
    file = tmp_path / "exact.txt"
    file.write_text("x" * 100, encoding="utf-8")

    assert parse_document(file, max_bytes=100).content == "x" * 100


def test_parse_document_no_limit_by_default(tmp_path: Path) -> None:
    file = tmp_path / "any.txt"
    file.write_bytes(b"x" * 2 * 1024 * 1024)

    assert len(parse_document(file).content) == 2 * 1024 * 1024


def test_read_documents_over_limit_collected_rest_read(tmp_path: Path) -> None:
    small = tmp_path / "small.txt"
    small.write_text("fine", encoding="utf-8")
    big = tmp_path / "big.txt"
    big.write_bytes(b"x" * 1000)

    result = read_documents([big, small], max_bytes=500)

    assert [document.file_name for document in result.documents] == ["small.txt"]
    ((unreadable),) = result.unreadable
    assert unreadable.file_path == big
    assert "over the" in unreadable.reason


# endregion


# region Reading a batch


def test_read_documents_keeps_given_order(tmp_path: Path) -> None:
    b = _write(tmp_path / "b.txt", "bee")
    a = _write(tmp_path / "a.md", "ay")

    result = read_documents([b, a])

    assert [document.file_name for document in result.documents] == ["b.txt", "a.md"]
    assert result.unreadable == []


def test_read_documents_skips_unsupported_silently(tmp_path: Path) -> None:
    result = read_documents([_write(tmp_path / "photo.png", b"x"), _write(tmp_path / "note.txt", "hi")])

    assert [document.file_name for document in result.documents] == ["note.txt"]
    assert result.unreadable == []


def test_read_documents_continues_past_unreadable(tmp_path: Path) -> None:
    good_before = _write(tmp_path / "a.txt", "first")
    bad = _write(tmp_path / "bad.docx", b"junk")
    good_after = _write(tmp_path / "z.txt", "last")

    result = read_documents([good_before, bad, good_after])

    assert [document.file_name for document in result.documents] == ["a.txt", "z.txt"]
    (unreadable,) = result.unreadable
    assert unreadable.file_path == bad
    assert "PackageNotFoundError" in unreadable.reason


def test_read_documents_nothing_empty() -> None:
    result = read_documents([])

    assert result.documents == []
    assert result.unreadable == []


def test_read_documents_accepts_generator(tmp_path: Path) -> None:
    paths = (_write(tmp_path / f"{name}.txt", name) for name in ("one", "two"))

    assert [d.content for d in read_documents(paths).documents] == ["one", "two"]


# endregion


# region The shared header


def test_document_from_fills_shared_header() -> None:
    document = document_from(Path("dir/Report.PDF"), "text", {"k": "v"})

    assert document.file_path == Path("dir/Report.PDF")
    assert document.file_name == "Report.PDF"
    assert document.extension == ".pdf"
    assert document.content == "text"
    assert document.metadata == {"k": "v"}


def test_document_from_no_metadata_empty_dict() -> None:
    assert document_from(Path("a.txt"), "x").metadata == {}


# endregion
