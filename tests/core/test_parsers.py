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


def test_the_supported_formats() -> None:
    assert {".pdf", ".docx", ".txt", ".md", ".markdown", ".msg", ".eml"} == SUPPORTED_EXTENSIONS


@pytest.mark.parametrize("name", ["a.pdf", "a.DOCX", "a.Txt", "a.md", "a.markdown", "a.msg", "a.EML"])
def test_supported_files_are_recognised_whatever_the_case(name: str) -> None:
    assert is_supported(Path(name)) is True


@pytest.mark.parametrize("name", ["photo.png", "sheet.xlsx", "noextension", "archive.tar.gz", ".md.bak"])
def test_other_files_are_not_supported(name: str) -> None:
    assert is_supported(Path(name)) is False


def test_parsing_an_unsupported_file_raises_unsupported_format(tmp_path: Path) -> None:
    path = _write(tmp_path / "photo.png", b"\x89PNG")

    with pytest.raises(UnsupportedFormatError) as excinfo:
        parse_document(path)

    assert excinfo.value.path == path
    assert ".png" in str(excinfo.value)


# endregion


# region Each format


def test_a_text_file_is_read_with_its_header_fields(tmp_path: Path) -> None:
    path = _write(tmp_path / "NOTES.TXT", "Hello world")

    document = parse_document(path)

    assert document.content == "Hello world"
    assert document.file_path == path
    assert document.file_name == "NOTES.TXT"
    assert document.extension == ".txt"  # lowercased
    assert document.metadata == {}


@pytest.mark.parametrize("name", ["a.md", "a.markdown"])
def test_markdown_is_read_as_text(tmp_path: Path, name: str) -> None:
    document = parse_document(_write(tmp_path / name, "# Title\n\nBody"))

    assert document.content == "# Title\n\nBody"
    assert document.extension == Path(name).suffix


def test_undecodable_bytes_in_a_text_file_are_replaced_not_fatal(tmp_path: Path) -> None:
    path = _write(tmp_path / "latin1.txt", b"caf\xe9 society")

    document = parse_document(path)

    assert document.content.startswith("caf")
    assert "society" in document.content


def test_an_eml_file_gives_its_body_and_headers(tmp_path: Path) -> None:
    document = parse_document(_write(tmp_path / "plan.eml", _EML))

    assert document.content.strip() == "Please review the plan."
    assert document.metadata == {
        "sender": "Ada <ada@example.com>",
        "to": "Grace <grace@example.com>",
        "subject": "Quarterly plan",
        "date": "Mon, 05 Oct 2026 09:00:00 +0000",
    }


def test_an_empty_eml_file_has_no_content_but_is_still_readable(tmp_path: Path) -> None:
    document = parse_document(_write(tmp_path / "empty.eml", b""))

    assert document.content == ""
    assert document.metadata["subject"] == ""


def test_a_docx_file_gives_its_paragraphs(tmp_path: Path) -> None:
    document = parse_document(_make_docx(tmp_path / "spec.docx", "First paragraph", "Second paragraph"))

    assert document.content == "First paragraph\nSecond paragraph"
    assert document.extension == ".docx"


def test_a_pdf_file_gives_its_text_and_metadata(tmp_path: Path) -> None:
    document = parse_document(_make_pdf(tmp_path / "report.pdf", "Quarterly report"))

    assert "Quarterly report" in document.content
    assert document.metadata.get("format", "").startswith("PDF")


def test_a_pdf_with_no_text_layer_reads_as_empty_text(tmp_path: Path) -> None:
    """Scanned (image-only) PDFs aren't OCRed, so they read as empty text and end up in review."""

    path = tmp_path / "scanned.pdf"
    pdf = pymupdf.open()
    pdf.new_page()
    pdf.save(str(path))
    pdf.close()

    assert parse_document(path).content == ""


def test_a_password_protected_pdf_is_unreadable(tmp_path: Path) -> None:
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
def test_a_corrupt_file_raises_unreadable_document_with_the_original_as_its_cause(
    tmp_path: Path, name: str, data: bytes
) -> None:
    path = _write(tmp_path / name, data)

    with pytest.raises(UnreadableDocumentError) as excinfo:
        parse_document(path)

    assert excinfo.value.path == path
    assert excinfo.value.reason
    assert name in str(excinfo.value)
    assert excinfo.value.__cause__ is not None
    assert type(excinfo.value.__cause__).__name__ in excinfo.value.reason


def test_the_reason_is_one_short_line(tmp_path: Path) -> None:
    path = _write(tmp_path / "bad.docx", b"junk")

    with pytest.raises(UnreadableDocumentError) as excinfo:
        parse_document(path)

    assert "\n" not in excinfo.value.reason
    assert len(excinfo.value.reason) <= 200


def test_a_missing_file_is_unreadable_not_a_raw_os_error(tmp_path: Path) -> None:
    with pytest.raises(UnreadableDocumentError):
        parse_document(tmp_path / "gone.txt")


# endregion


# region Reading a batch


def test_read_documents_reads_supported_files_in_the_order_given(tmp_path: Path) -> None:
    b = _write(tmp_path / "b.txt", "bee")
    a = _write(tmp_path / "a.md", "ay")

    result = read_documents([b, a])

    assert [document.file_name for document in result.documents] == ["b.txt", "a.md"]
    assert result.unreadable == []


def test_read_documents_skips_unsupported_files_silently(tmp_path: Path) -> None:
    result = read_documents([_write(tmp_path / "photo.png", b"x"), _write(tmp_path / "note.txt", "hi")])

    assert [document.file_name for document in result.documents] == ["note.txt"]
    assert result.unreadable == []


def test_read_documents_carries_on_past_an_unreadable_file(tmp_path: Path) -> None:
    good_before = _write(tmp_path / "a.txt", "first")
    bad = _write(tmp_path / "bad.docx", b"junk")
    good_after = _write(tmp_path / "z.txt", "last")

    result = read_documents([good_before, bad, good_after])

    assert [document.file_name for document in result.documents] == ["a.txt", "z.txt"]
    (unreadable,) = result.unreadable
    assert unreadable.file_path == bad
    assert "PackageNotFoundError" in unreadable.reason


def test_read_documents_of_nothing_is_empty() -> None:
    result = read_documents([])

    assert result.documents == []
    assert result.unreadable == []


def test_read_documents_accepts_a_generator(tmp_path: Path) -> None:
    paths = (_write(tmp_path / f"{name}.txt", name) for name in ("one", "two"))

    assert [d.content for d in read_documents(paths).documents] == ["one", "two"]


# endregion


# region The shared header


def test_document_from_fills_in_the_header_every_parser_shares() -> None:
    document = document_from(Path("dir/Report.PDF"), "text", {"k": "v"})

    assert document.file_path == Path("dir/Report.PDF")
    assert document.file_name == "Report.PDF"
    assert document.extension == ".pdf"
    assert document.content == "text"
    assert document.metadata == {"k": "v"}


def test_document_from_without_metadata_gives_an_empty_dict() -> None:
    assert document_from(Path("a.txt"), "x").metadata == {}


# endregion
