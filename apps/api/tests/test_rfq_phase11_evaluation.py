import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.rfq.contracts import Evidence, FieldValue, LineItem, Location
from api.rfq.evaluation.matching_v2 import match_items
from api.rfq.evaluation.quality_run import aggregate, run


def row(description, *, sheet=None, quantity="2"):
    evidence = Evidence(
        document_id="synthetic",
        fingerprint="0" * 64,
        block_id="row:2",
        location=Location(row=2, sheet=sheet),
        excerpt=description,
        method="deterministic",
        identity="explicit-evaluator-fixture",
        verified=True,
    )
    return LineItem(
        id="explicit-evaluation-fixture",
        extraction_method="deterministic",
        fields={
            "description": FieldValue(value=description, evidence=[evidence]),
            "quantity": FieldValue(value=quantity),
        },
    )


def test_duplicate_predictions_are_ambiguous_and_one_to_one():
    pairs = match_items(
        [{"description": "Laptop dock"}], [row("Laptop dock"), row("Laptop dock")]
    )
    assert len(pairs) == 1 and pairs[0]["ambiguous"]


def test_missing_mpn_does_not_prevent_identity_matching():
    pairs = match_items(
        [{"description": "Laptop dock", "mpn": "000-XY"}], [row("Laptop dock")]
    )
    assert len(pairs) == 1 and not pairs[0]["ambiguous"]


def test_incompatible_sheet_anchor_remains_unmatched():
    assert not match_items(
        [{"description": "Laptop dock", "source": {"sheet": "Compute"}}],
        [row("Laptop dock", sheet="Other")],
    )


@pytest.mark.parametrize(
    "expected,predicted", [([], [row("Cable")]), ([{"description": "Dock"}], [])]
)
def test_unmatched_state_is_explicit(expected, predicted):
    assert not match_items(expected, predicted)


def test_latency_excludes_failed_attempt_but_truth_includes_missed_items():
    samples = [
        dict(
            success=True,
            counts={
                "truth_items": 5,
                "predicted_items": 5,
                "matches": 5,
                "mpn_correct": 4,
            },
            timings={"latency_ms": 20},
        ),
        dict(success=False, counts={"truth_items": 5}, timings={"latency_ms": 900}),
    ]
    measured = aggregate(samples)
    assert measured["mpn_accuracy"] == 0.4 and measured["recall"] == 0.5
    assert measured["latency_ms"] == {
        "median": 20,
        "p95": 20,
        "successful_denominator": 1,
        "failed_attempt_ms": 900,
    }
    assert measured["field_column_accuracy"] is None


def test_frozen_v1_and_v2_payload_hashes():
    repository = Path(__file__).resolve().parents[3]
    for name in ("rfq", "rfq-v2"):
        root = repository / "data/evaluation" / name
        manifest = json.loads((root / "manifest.json").read_text())
        assert len(manifest["documents"]) == 48
        for document in manifest["documents"]:
            assert (
                hashlib.sha256((root / document["source"]).read_bytes()).hexdigest()
                == document["sha256"]
            )
            assert (
                hashlib.sha256((root / document["truth"]).read_bytes()).hexdigest()
                == document["truth_sha256"]
            )


def test_corrupt_dataset_is_recorded_without_extraction(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = Path("data/evaluation/corrupt-fixture")
    root.mkdir(parents=True)
    (root / "source.txt").write_text("Modified synthetic source")
    (root / "truth.json").write_text('{"header":{},"items":[]}')
    document = dict(
        id="corrupt",
        source="source.txt",
        truth="truth.json",
        format="txt",
        layout_group="fixture",
        difficulty="fixture",
        split="dev",
        expected_items=1,
        sha256="0" * 64,
        truth_sha256="0" * 64,
    )
    (root / "manifest.json").write_text(
        json.dumps(dict(version="explicit-corrupt-fixture", documents=[document]))
    )

    async def forbidden(*args, **kwargs):
        raise AssertionError("A corrupt frozen dataset must not reach inference.")

    monkeypatch.setattr("api.rfq.evaluation.quality_run.extract", forbidden)
    args = SimpleNamespace(
        dataset=str(root),
        split="dev",
        stratified=False,
        ids=None,
        model="",
        ocr="enhanced-v2",
        context=8192,
        output_tokens=4096,
        retries=0,
        output="result.json",
        mode="deterministic",
        profile="full",
        policy="selective-v2",
    )
    asyncio.run(run(args))
    report = json.loads(Path("result.json").read_text())
    assert (
        report["actual_samples"] == 1
        and report["metrics"]["failed_documents"] == 1
        and report["skipped_samples"] == 0
    )
    assert report["samples"][0]["failure"] == "ValueError"
