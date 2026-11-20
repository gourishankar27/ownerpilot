import asyncio
import io
import json
from uuid import uuid4

import httpx
import openpyxl
import pytest
from pydantic import ValidationError

from api.rfq.contracts import FieldValue, Proposal
from api.rfq.extraction import chunks, deterministic, verify_proposal
from api.rfq.parsers import parse_document, validate_upload
from api.rfq.provider import OllamaProvider, PROMPT, ProviderError
from api.rfq.storage import DocumentError, LocalStorage, fingerprint, safe_name
from api.rfq.validation import approval_issues, mark_duplicates, normalize

CSV = b"Manufacturer,MPN,Description,Qty,UOM\nNimvora,001-AB.2,Laptop,12,EA\n"


@pytest.mark.parametrize(
    "name,mime,content",
    [
        ("x.exe", "application/octet-stream", b"binary"),
        ("x.pdf", "application/pdf", b"notpdf"),
        ("x.txt", "text/plain", b"\x00bad"),
        ("x.csv", "application/pdf", CSV),
        ("x.xlsx", None, b"PKbad"),
        ("x.txt", None, b"<html>fake</html>"),
    ],
)
def test_reject_upload(name, mime, content):
    with pytest.raises(DocumentError):
        validate_upload(name, mime, content)


def test_safe_storage(tmp_path, monkeypatch):
    from api.rfq.config import settings

    monkeypatch.setenv("RFQ_STORAGE_ROOT", str(tmp_path))
    settings.cache_clear()
    storage = LocalStorage()
    workspace = str(uuid4())
    identifier = str(uuid4())
    storage.put(workspace, identifier, CSV)
    assert storage.read(workspace, identifier) == CSV
    assert len(fingerprint(CSV)) == 64 and fingerprint(CSV) == fingerprint(bytes(CSV))
    assert safe_name("../../private\\file.csv") == "file.csv"
    with pytest.raises(ValueError):
        storage.read("../escape", identifier)
    settings.cache_clear()


def test_csv_evidence_and_part_number():
    doc = parse_document("x.csv", CSV, "source")
    result = deterministic(doc)
    item = result.items[0]
    assert item.fields["mpn"].value == "001-AB.2"
    assert item.fields["quantity"].value == "12"
    assert item.fields["mpn"].evidence[0].location.column == "B"
    assert item.fields["mpn"].evidence[0].location.row == 2
    assert item.fields["mpn"].evidence[0].verified


def test_csv_semicolon_preamble():
    content = b"RFQ number: SYN-123\nCustomer: Fictional\nDescription;Qty;MPN;UOM\nLaptop;3;000-XY;EA\n"
    result = deterministic(parse_document("x.csv", content, "source"))
    assert result.items[0].fields["mpn"].value == "000-XY"
    assert result.header["external_rfq_number"].value == "SYN-123"


def test_pdf_digital_encrypted_and_ocr_unavailable(monkeypatch):
    from reportlab.pdfgen.canvas import Canvas
    from pypdf import PdfReader, PdfWriter

    stream = io.BytesIO()
    canvas = Canvas(stream)
    canvas.drawString(40, 750, "Description | Qty | MPN | UOM")
    canvas.drawString(40, 725, "Laptop | 3 | 000-XY | EA")
    canvas.save()
    native = stream.getvalue()
    doc = parse_document("x.pdf", native, "source")
    assert len(deterministic(doc).items) == 1 and not doc.ocr_pages
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(native)))
    writer.encrypt("synthetic-password")
    encrypted = io.BytesIO()
    writer.write(encrypted)
    with pytest.raises(DocumentError, match="Encrypted"):
        validate_upload("x.pdf", None, encrypted.getvalue())
    monkeypatch.setattr("api.rfq.parsers.shutil.which", lambda command: None)
    writer = PdfWriter()
    writer.add_blank_page(width=600, height=800)
    blank = io.BytesIO()
    writer.write(blank)
    with pytest.raises(DocumentError, match="OCR runtime unavailable"):
        parse_document("x.pdf", blank.getvalue(), "source")


def test_size_and_decompression_limits(monkeypatch):
    import zipfile
    from api.rfq.config import settings

    monkeypatch.setenv("RFQ_MAX_FILE_BYTES", "1024")
    settings.cache_clear()
    with pytest.raises(DocumentError):
        validate_upload("x.txt", None, b"a" * 1025)
    settings.cache_clear()
    monkeypatch.delenv("RFQ_MAX_FILE_BYTES")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("xl/workbook.xml", b"x" * 100000)
        package.writestr("[Content_Types].xml", b"x")
    with pytest.raises(DocumentError, match="compression"):
        validate_upload("x.xlsx", None, archive.getvalue())
    settings.cache_clear()


def test_excel_multiple_sheets_and_formula():
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "First"
    sheet.append(["Description", "Qty", "MPN", "UOM"])
    sheet.append(["Cable", 2, "0002-X", "EA"])
    second = book.create_sheet("Second")
    second.append(["Description", "Qty", "MPN", "UOM"])
    second.append(["Server", "=2+2", "0003-X", "EA"])
    output = io.BytesIO()
    book.save(output)
    doc = parse_document("x.xlsx", output.getvalue(), "source")
    items = deterministic(doc).items
    assert len(items) == 2
    assert items[1].fields["quantity"].value is None
    assert (
        doc.warnings and items[1].fields["mpn"].evidence[0].location.sheet == "Second"
    )


@pytest.mark.parametrize(
    "raw,expected,status",
    [
        ("1,200", "1200", "validated"),
        ("1,5", "1,5", "ambiguous"),
        ("0", "0", "ambiguous"),
        ("5-10", "5-10", "ambiguous"),
        ("-2", "-2", "ambiguous"),
        ("2.5", "2.5", "validated"),
    ],
)
def test_quantity(raw, expected, status):
    field = normalize("quantity", raw, corrected=True)
    assert field.value == expected and field.status == status


def test_normalization():
    assert normalize("mpn", " 000-A.B/2 ", corrected=True).value == "000-A.B/2"
    assert normalize("unit", "pcs", corrected=True).value == "EA"
    assert normalize("currency", "usd", corrected=True).value == "USD"
    assert normalize("currency", "$", corrected=True).status == "requires_review"
    assert normalize("request_date", "01/02/2026", corrected=True).status == "ambiguous"
    assert normalize("contact_email", "bad", corrected=True).issues


def test_unqualified_part_number_requires_identifier_review():
    doc = parse_document(
        "x.csv",
        b"Description,Qty,Part number,UOM,SKU\nLaptop,2,000-X,EA,DIST-99\n",
        "source",
    )
    item = deterministic(doc).items[0]
    assert item.fields["mpn"].status == "ambiguous"
    assert item.fields["requested_sku"].value == "DIST-99"
    assert item.fields["mpn"].value == "000-X"


def test_missing_headers_and_duplicates():
    doc = parse_document("x.csv", b"A,B\nLaptop,10\n", "source")
    assert not deterministic(doc).items
    item = deterministic(parse_document("x.csv", CSV, "source")).items[0]
    other = item.model_copy(deep=True)
    other.id = str(uuid4())
    mark_duplicates([item, other])
    assert item.warnings and other.warnings
    other.fields["quantity"].value = "13"
    item.warnings = []
    other.warnings = []
    mark_duplicates([item, other])
    assert not other.warnings


def test_closed_output_and_evidence():
    with pytest.raises(ValidationError):
        Proposal.model_validate({"header": {}, "items": [], "tool": "execute"})
    doc = parse_document("x.csv", CSV, "source")
    proposal = Proposal.model_validate(
        {
            "header": {},
            "items": [
                {
                    "mpn": {
                        "value": "INVENTED",
                        "block_id": "row:2",
                        "excerpt": "INVENTED",
                    }
                }
            ],
        }
    )
    result = verify_proposal(doc, doc.blocks, proposal, "fixture-explicit-test")
    assert result.items[0].fields["mpn"].value is None
    assert result.items[0].fields["mpn"].status == "unverified"
    assert approval_issues({}, result.items)
    assert "UNTRUSTED DATA" in PROMPT and "No tools" in PROMPT


def test_approval_requires_review():
    item = deterministic(parse_document("x.csv", CSV, "source")).items[0]
    assert approval_issues({}, [item])
    item.review_status = "reviewed"
    assert not approval_issues({}, [item])
    item.fields["mpn"] = FieldValue(raw="fake", status="unverified")
    assert approval_issues({}, [item])


@pytest.mark.parametrize("behavior", ["invalid", "timeout", "extra", "valid"])
def test_provider_responses(behavior, monkeypatch):
    from api.rfq.config import settings

    monkeypatch.setenv("RFQ_OLLAMA_MODEL", "fixture-local-test")
    monkeypatch.setenv("RFQ_MODEL_RETRIES", "0")
    settings.cache_clear()

    def respond(request):
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "fixture-local-test", "digest": "test"}]}
            )
        if behavior == "timeout":
            raise httpx.ReadTimeout("simulated")
        proposal = {"header": {}, "items": []}
        if behavior == "extra":
            proposal["command"] = "bad"
        return httpx.Response(
            200,
            json={
                "model": "fixture-local-test",
                "done": True,
                "message": {
                    "content": "invalid"
                    if behavior == "invalid"
                    else json.dumps(proposal)
                },
            },
        )

    provider = OllamaProvider(transport=httpx.MockTransport(respond))
    if behavior == "valid":
        proposal, meta = asyncio.run(provider.extract([]))
        assert not proposal.items
    else:
        with pytest.raises(ProviderError):
            asyncio.run(provider.extract([]))
    settings.cache_clear()


def test_chunk_limits(monkeypatch):
    from api.rfq.config import settings

    monkeypatch.setenv("RFQ_MODEL_INPUT_CHARS", "500")
    settings.cache_clear()
    doc = parse_document("x.txt", ("x" * 501).encode(), "source")
    with pytest.raises(ProviderError):
        chunks(doc)
    settings.cache_clear()


def test_one_to_one_evaluation():
    from api.rfq.evaluation.run import match_items

    item = deterministic(parse_document("x.csv", CSV, "source")).items[0]
    assert (
        len(match_items([{"mpn": "001-AB.2", "description": "Laptop"}], [item, item]))
        == 1
    )


@pytest.mark.ollama
def test_real_ollama():
    from api.rfq.config import settings

    if not settings().ollama_model:
        pytest.skip("RFQ_OLLAMA_MODEL not configured; no real inference claimed.")
    doc = parse_document(
        "x.txt",
        b"Please supply 3 EA Laptop. Manufacturer Nimvora; MPN 000-XY-1.",
        "source",
    )
    provider = OllamaProvider()
    proposal, meta = asyncio.run(provider.extract(doc.blocks))
    assert proposal.items and meta["provider"] == "ollama"
