from __future__ import annotations

import csv
import io
import shutil
import time
import zipfile
from pathlib import Path
from typing import Protocol

import openpyxl
from pypdf import PdfReader

from .config import settings
from .contracts import Block, Location, ParsedDocument
from .storage import DocumentError, fingerprint

PARSER_VERSION = "ownerpilot-parser/1.1"
MIMES = {
    ".pdf": {"application/pdf"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".csv": {"text/csv", "application/csv", "application/vnd.ms-excel", "text/plain"},
    ".txt": {"text/plain"},
}


def decode(content: bytes) -> str:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentError("Text files must use UTF-8 encoding.") from exc
    if "\x00" in text or any(ord(c) < 9 for c in text):
        raise DocumentError("Binary content is not a supported text document.")
    if text.lstrip().lower().startswith(("<!doctype html", "<html", "%pdf", "<?xml")):
        raise DocumentError("File content does not match its text extension.")
    return text


def validate_upload(name: str, mime: str | None, content: bytes) -> str:
    cfg = settings()
    extension = Path(name).suffix.lower()
    if extension not in MIMES:
        raise DocumentError("Supported formats: PDF, CSV, XLSX and UTF-8 TXT.")
    if mime and mime.split(";")[0].lower() not in MIMES[extension] | {
        "application/octet-stream"
    }:
        raise DocumentError("Declared content type does not match the extension.")
    if not content or len(content) > cfg.max_file_bytes:
        raise DocumentError("File is empty or exceeds the configured upload limit.")
    try:
        if extension == ".pdf":
            if not content.startswith(b"%PDF-"):
                raise DocumentError("Invalid PDF signature.")
            reader = PdfReader(io.BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise DocumentError(
                    "Encrypted PDFs are not supported. Upload an unencrypted copy."
                )
            if not 0 < len(reader.pages) <= cfg.max_pages:
                raise DocumentError("PDF exceeds the page limit or contains no pages.")
        elif extension == ".xlsx":
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                entries = archive.infolist()
                if (
                    len(entries) > 2000
                    or sum(e.file_size for e in entries) > cfg.max_uncompressed_bytes
                ):
                    raise DocumentError("Workbook decompression limit exceeded.")
                names = {e.filename for e in entries}
                if "xl/workbook.xml" not in names or "[Content_Types].xml" not in names:
                    raise DocumentError("Not an XLSX workbook.")
                if any(
                    "vbaproject" in n.lower() or "externallinks/" in n.lower()
                    for n in names
                ):
                    raise DocumentError(
                        "Macros and external workbook links are not supported."
                    )
                if any(
                    e.flag_bits & 1 or e.file_size / max(e.compress_size, 1) > 200
                    for e in entries
                ):
                    raise DocumentError(
                        "Encrypted or excessive compression workbook rejected."
                    )
        else:
            decode(content)
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError("Malformed or unreadable document.") from exc
    return extension


class Parser(Protocol):
    def parse(self, content: bytes, document_id: str) -> ParsedDocument: ...


def result(content: bytes, document_id: str, kind: str) -> ParsedDocument:
    return ParsedDocument(
        document_id=document_id,
        fingerprint=fingerprint(content),
        parser=f"{PARSER_VERSION}:{kind}",
        blocks=[],
    )


def check_text(doc: ParsedDocument) -> None:
    import json

    if sum(len(b.text) for b in doc.blocks) > settings().max_text_chars:
        raise DocumentError("Extracted text exceeds the processing limit.")
    if (
        len(json.dumps(doc.model_dump(), ensure_ascii=False).encode("utf-8"))
        > settings().max_metadata_bytes
    ):
        raise DocumentError(
            "Parsed text/geometry metadata exceeds the retention budget."
        )


class TextParser:
    def parse(self, content: bytes, document_id: str) -> ParsedDocument:
        doc = result(content, document_id, "text")
        offset = 0
        for i, text in enumerate(decode(content).splitlines(keepends=True), 1):
            if text.strip():
                doc.blocks.append(
                    Block(
                        id=f"row:{i}",
                        text=text.rstrip(),
                        location=Location(
                            row=i, start=offset, end=offset + len(text.rstrip())
                        ),
                        method="text",
                    )
                )
            offset += len(text)
        check_text(doc)
        return doc


class CsvParser:
    def parse(self, content: bytes, document_id: str) -> ParsedDocument:
        doc = result(content, document_id, "csv")
        text = decode(content)
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        # Cover preamble rows with fewer columns (Sniffer expects uniform rows).
        sample_lines = text[:8192].splitlines()
        delimiter = max(
            ",;\t|", key=lambda c: sum(line.count(c) >= 2 for line in sample_lines)
        )
        if not any(line.count(delimiter) >= 2 for line in sample_lines):
            delimiter = getattr(dialect, "delimiter", ",")
        try:
            for i, cells in enumerate(
                csv.reader(
                    io.StringIO(text), dialect, delimiter=delimiter, strict=True
                ),
                1,
            ):
                if i > settings().max_rows or len(cells) > settings().max_columns:
                    raise DocumentError("CSV exceeds row or column limits.")
                doc.blocks.append(
                    Block(
                        id=f"row:{i}",
                        text=" | ".join(cells),
                        cells=cells,
                        location=Location(row=i),
                        method="csv",
                    )
                )
        except csv.Error as exc:
            raise DocumentError("Malformed CSV.") from exc
        check_text(doc)
        return doc


class ExcelParser:
    def parse(self, content: bytes, document_id: str) -> ParsedDocument:
        doc = result(content, document_id, "xlsx")
        book = None
        try:
            book = openpyxl.load_workbook(
                io.BytesIO(content), read_only=True, data_only=False, keep_links=False
            )
            if len(book.worksheets) > settings().max_sheets:
                raise DocumentError("Workbook exceeds worksheet limit.")
            total_rows = 0
            for sheet in book.worksheets:
                if (sheet.max_row or 0) > settings().max_rows or (
                    sheet.max_column or 0
                ) > settings().max_columns:
                    raise DocumentError("Workbook exceeds row or column limit.")
                for i, row in enumerate(sheet.iter_rows(), 1):
                    total_rows += 1
                    if total_rows > settings().max_rows:
                        raise DocumentError("Workbook exceeds total row limit.")
                    cells = []
                    for cell in row:
                        if cell.data_type == "f":
                            cells.append("")
                            doc.warnings.append(
                                f"Formula ignored: {sheet.title}!{cell.coordinate}"
                            )
                        else:
                            value = cell.value
                            # Excel numeric cells cannot preserve lost leading zeros.
                            if (
                                isinstance(value, (int, float))
                                and cell.number_format
                                and set(cell.number_format) == {"0"}
                            ):
                                value = str(int(value)).zfill(len(cell.number_format))
                            cells.append("" if value is None else str(value))
                    if any(cells):
                        doc.blocks.append(
                            Block(
                                id=f"sheet:{sheet.title}:row:{i}",
                                text=" | ".join(cells),
                                cells=cells,
                                location=Location(sheet=sheet.title, row=i),
                                method="xlsx",
                            )
                        )
            check_text(doc)
            return doc
        except DocumentError:
            raise
        except Exception as exc:
            raise DocumentError("Malformed XLSX workbook.") from exc
        finally:
            if book:
                book.close()


class PdfParser:
    def parse(self, content: bytes, document_id: str) -> ParsedDocument:
        from .ocr import ocr_page
        import pypdfium2 as pdfium

        doc = result(content, document_id, "pdf")
        cfg = settings()
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise DocumentError("Encrypted PDFs are unsupported.")
        doc.pages = len(reader.pages)
        if doc.pages > cfg.max_pages:
            raise DocumentError("PDF page limit exceeded.")
        for number, page in enumerate(reader.pages, 1):
            stream = page.get_contents()
            if stream and len(stream.get_data()) > cfg.max_uncompressed_bytes:
                raise DocumentError("PDF page stream exceeds resource limit.")
            text = page.extract_text(extraction_mode="layout") or ""
            resources = page.get("/Resources", {})
            if hasattr(resources, "get_object"):
                resources = resources.get_object()
            objects = resources.get("/XObject", {})
            if hasattr(objects, "get_object"):
                objects = objects.get_object()
            images = any(
                value.get_object().get("/Subtype") == "/Image"
                for value in objects.values()
            )
            if sum(c.isalnum() for c in text) < 24 or (
                images and sum(c.isalnum() for c in text) < 200
            ):
                dpi = cfg.ocr_dpi
                with pdfium.PdfDocument(content) as rendered:
                    rendered_page = rendered[number - 1]
                    try:
                        width, height = rendered_page.get_size()
                        if width * height * (dpi / 72) ** 2 > cfg.ocr_max_pixels:
                            raise DocumentError("PDF page exceeds OCR pixel limit.")
                        bitmap = rendered_page.render(scale=dpi / 72)
                        try:
                            blocks, metadata = ocr_page(
                                bitmap.to_pil(), number, cfg.ocr_strategy, dpi
                            )
                        finally:
                            bitmap.close()
                    finally:
                        rendered_page.close()
                doc.blocks.extend(blocks)
                doc.ocr_ms += metadata["duration_ms"]
                doc.ocr_pages.append(number)
                doc.metadata.setdefault("ocr_pages", []).append(metadata)
                doc.metadata["ocr_strategy"] = cfg.ocr_strategy
            else:
                offset = 0
                for row, line in enumerate(text.splitlines(keepends=True), 1):
                    if line.strip():
                        doc.blocks.append(
                            Block(
                                id=f"page:{number}:row:{row}",
                                text=line.rstrip(),
                                location=Location(
                                    page=number,
                                    row=row,
                                    start=offset,
                                    end=offset + len(line.rstrip()),
                                ),
                                method="pdf_native",
                            )
                        )
                    offset += len(line)
            check_text(doc)
        return doc


PARSERS: dict[str, type] = {
    ".pdf": PdfParser,
    ".csv": CsvParser,
    ".xlsx": ExcelParser,
    ".txt": TextParser,
}


def cache_identity(policy: str, filename: str) -> str:
    import hashlib
    import json

    if policy == "phase1":
        return "ownerpilot-parser/1.0"
    cfg = settings()
    from .ocr import OCR_VERSION

    configuration = {
        k: getattr(cfg, k)
        for k in (
            "ocr_strategy",
            "ocr_dpi",
            "ocr_language",
            "ocr_max_regions",
            "ocr_max_passes",
            "ocr_max_pixels",
        )
    }
    configuration["ocr_configuration_version"] = OCR_VERSION
    if Path(filename).suffix.lower() == ".pdf":
        from .ocr import engine_version

        configuration["engine"] = (
            engine_version(cfg.ocr_command)
            if shutil.which(cfg.ocr_command)
            else "unavailable"
        )
    return (
        PARSER_VERSION
        + ":"
        + hashlib.sha256(
            json.dumps(configuration, sort_keys=True).encode()
        ).hexdigest()[:20]
    )


def parse_document(
    name: str, content: bytes, document_id: str, policy: str | None = None
) -> ParsedDocument:
    if policy == "phase1":
        from .legacy_v1.parsers import parse_document as original

        return ParsedDocument.model_validate(
            original(name, content, document_id).model_dump()
        )
    started = time.perf_counter()
    extension = validate_upload(name, None, content)
    doc = PARSERS[extension]().parse(content, document_id)
    doc.duration_ms = (time.perf_counter() - started) * 1000
    return doc
