import asyncio
from types import SimpleNamespace
import subprocess

import httpx
from PIL import Image, ImageDraw
import pytest

from api.rfq.config import settings
from api.rfq.contracts import ParsedDocument, Block, Location, Proposal
from api.rfq.extraction import extract
from api.rfq.ocr import deskew_angle, ocr_page
from api.rfq.provider import OllamaProvider, ProviderError


def test_projection_deskew_detects_mild_rotation():
    image = Image.new("L", (600, 300), 255)
    draw = ImageDraw.Draw(image)
    for y in range(40, 280, 40):
        draw.line((30, y, 550, y), fill=0, width=3)
    rotated = image.rotate(3, fillcolor=255)
    assert abs(deskew_angle(rotated) + 3) <= 1


def test_ocr_timeout_is_actionable(monkeypatch):
    monkeypatch.setattr("api.rfq.ocr.shutil.which", lambda command: "fixture-tesseract")
    monkeypatch.setattr(
        "api.rfq.ocr.engine_version", lambda command: "explicit-test-fixture"
    )

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("explicit fixture", 1)

    monkeypatch.setattr("api.rfq.ocr.subprocess.run", timeout)
    with pytest.raises(Exception, match="timed out"):
        ocr_page(Image.new("L", (100, 100), 255), 1, "enhanced-v2", 300)


def test_targeted_ocr_retains_disagreeing_reading_and_real_fixture_boxes(monkeypatch):
    monkeypatch.setattr("api.rfq.ocr.shutil.which", lambda command: "fixture-tesseract")
    monkeypatch.setattr(
        "api.rfq.ocr.engine_version", lambda command: "explicit-test-fixture"
    )
    lines = [
        "level\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext"
    ]
    for line, values in [
        (1, ["Line", "MPN", "Description", "Manufacturer", "Qty", "UOM"]),
        (2, ["1", "00-X", "Laptop", "Northvale", "2", "EA"]),
    ]:
        for x, text in zip([5, 50, 120, 200, 280, 330], values):
            lines.append(f"5\t1\t1\t{line}\t{x}\t{line * 30}\t25\t12\t80\t{text}")
    calls = []

    def output(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(
            returncode=0,
            stdout=("\n".join(lines) if args[-1] == "tsv" else "OO-X").encode(),
        )

    monkeypatch.setattr("api.rfq.ocr.subprocess.run", output)
    blocks, meta = ocr_page(Image.new("L", (400, 150), 255), 2, "targeted-v2", 300)
    assert meta["regions"] == 1 and meta["disagreements"] == 1 and meta["passes"] == 2
    assert blocks[1].cells[1] == "00-X" and blocks[1].metadata["cells"][1][
        "alternatives"
    ] == ["OO-X"]
    assert blocks[1].cell_locations[1].bbox is not None and blocks[1].location.page == 2
    assert any("7" in call for call in calls)


def test_model_call_budget_fails_without_partial_success(monkeypatch):
    monkeypatch.setenv("RFQ_MAX_MODEL_CALLS", "1")
    monkeypatch.setenv("RFQ_MODEL_INPUT_CHARS", "500")
    settings.cache_clear()

    class ExplicitFixture:
        def __init__(self):
            self.calls = 0

        async def extract(self, blocks):
            self.calls += 1
            return Proposal.model_validate({"header": {}, "items": []}), {
                "model": "explicit-fixture"
            }

    provider = ExplicitFixture()
    doc = ParsedDocument(
        document_id="fixture",
        fingerprint="0" * 64,
        parser="fixture",
        blocks=[
            Block(
                id=str(i),
                text="Request " + "x" * 350,
                location=Location(row=i + 1),
                method="text",
            )
            for i in range(3)
        ],
    )
    with pytest.raises(ProviderError, match="budget"):
        asyncio.run(extract([doc], "llm", provider))
    assert provider.calls == 1
    settings.cache_clear()


def test_invalid_json_retry_count_is_bounded(monkeypatch):
    monkeypatch.setenv("RFQ_OLLAMA_MODEL", "fixture")
    monkeypatch.setenv("RFQ_MODEL_RETRIES", "1")
    settings.cache_clear()
    calls = []

    def respond(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "fixture"}]})
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "model": "fixture",
                "done": True,
                "message": {"content": "invalid-json"},
            },
        )

    with pytest.raises(ProviderError, match="invalid_structured_output"):
        asyncio.run(OllamaProvider(httpx.MockTransport(respond)).extract([]))
    assert calls == ["/api/chat", "/api/chat"]
    settings.cache_clear()


def test_ocr_pixel_limit_precedes_allocation_or_runtime(monkeypatch):
    monkeypatch.setenv("RFQ_OCR_MAX_PIXELS", "1000000")
    settings.cache_clear()
    with pytest.raises(Exception, match="pixel limit"):
        ocr_page(Image.new("L", (1100, 1100)), 1, "enhanced-v2", 300)
    settings.cache_clear()
