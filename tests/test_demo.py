"""Bounded demo acceptance: synthetic lineage, isolation, reset, zero model calls."""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.demo import OWNER, build_demo_app, fixture_records
from app.main import create_app
from app.receipt_intake.repository import read_original_bytes
from tests.test_receipt_extraction import blank_png, upload_png


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def content(client):
    rows = client.get("/api/memory").json()["purchases"]
    result = []
    for row in rows:
        purchase = client.get(f'/api/memory/{row["memory_id"]}').json()
        result.append((purchase["merchant"], purchase["purchase_date"],
                       [(i["item_name"], i["need_want_classification"]) for i in purchase["items"]]))
    return result


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    root = tmp_path_factory.mktemp("demo-acceptance")
    normal = Settings(data_dir=root / "normal" / "receipt_evidence")
    normal_app = create_app(normal)
    with TestClient(normal_app) as real:
        upload_png(real, blank_png(), "normal-storage-synthetic-sentinel.png")
        before = snapshot(root / "normal")
        app = build_demo_app(normal, root / "demo")
        with TestClient(app) as client:
            yield root, normal, real, app, client, before
        assert snapshot(root / "normal") == before


def test_demo_load_reuses_existing_fixture_fields(demo):
    _, _, _, _, client, _ = demo
    records = fixture_records()
    assert len(records) == 7
    assert len(client.get("/api/memory").json()["purchases"]) == len(records)
    assert {r["merchant"] for r in records} == {"North Market", "Corner Shop", "Walmart Supercenter"}


def test_real_storage_is_unchanged(demo):
    root, _, real, _, _, before = demo
    assert snapshot(root / "normal") == before
    assert real.get("/api/memory").json()["purchases"] == []
    assert "DEMO DATA" not in real.get("/").text


def test_overview_and_history_are_populated(demo):
    _, _, _, _, client, _ = demo
    assert client.get("/").status_code == 200
    assert client.get("/memory").status_code == 200
    rows = client.get("/api/memory").json()["purchases"]
    assert len(rows) == 7 and len({r["purchase_date"] for r in rows}) > 2
    assert len({r["merchant"] for r in rows}) == 3
    assert sum(len(p[2]) for p in content(client)) == 12


def test_patterns_have_repeat_intervals_and_classifications(demo):
    _, _, _, _, client, _ = demo
    report = client.get("/api/analytics").json()
    milk = next(i for i in report["repeat_items"] if i["analytics_key"] == "milk gallon")
    assert milk["occurrence_count"] == 4
    assert milk["average_interval_days"] == "12.5"
    assert milk["latest_interval_days"] == 15
    assert report["summary"]["repeating_items"] == 2
    assert all(report["classifications"]["need_want"][v] > 0 for v in ("need", "want", "unknown"))
    assert len(report["merchants"]) == 3


def test_food_recall_has_truthful_representative_and_text_states(demo):
    _, _, _, _, client, _ = demo
    items = client.get("/api/visual-recall").json()["items"]
    assert {i["display"] for i in items} == {"representative", "text-only"}
    assert len(items) == 4
    for item in items:
        if item["image_available"]:
            image = client.get(f'/api/visual-recall/enrichments/{item["enrichment_id"]}/image')
            assert image.status_code == 200 and b"<svg" in image.content
    assert "Purchased does not mean" in client.get("/food-recall").text


def test_ask_uses_grounded_existing_test_provider_without_writes(demo):
    root, _, _, _, client, _ = demo
    before = snapshot(root / "demo")
    for question in ("What do I buy often?", "What food did I buy recently?",
                     "What patterns are showing up?", "What have I bought at Walmart?"):
        answer = client.post("/api/ask", json={"question": question})
        assert answer.status_code == 200
        assert answer.json()["provider"] == "test-grounded-provider"
        assert answer.json()["grounded_fact_count"] > 0
        assert answer.json()["status"] in {"ready", "degraded"}
    assert snapshot(root / "demo") == before
    assert client.get("/api/ai-status").json()["model"] == "test-only"


def test_label_assets_and_personal_upload_protection(demo):
    _, _, _, _, client, _ = demo
    for path in ("/", "/memory", "/analytics", "/food-recall", "/ask", "/intake"):
        page = client.get(path)
        assert page.status_code == 200 and "DEMO DATA" in page.text
        assert "not a live AI model" in page.text
    assert client.get("/static/demo.css").status_code == 200
    assert client.post("/api/receipts", files={"file": ("blocked.png", blank_png())}).status_code == 403
    assert client.post("/api/purchases", json={}).status_code == 403


def test_every_purchase_has_real_synthetic_fixture_evidence_and_extraction(demo):
    root, _, _, app, client, _ = demo
    manifest = json.loads((root / "demo" / "demo-manifest.json").read_text())
    assert manifest["owner"] == OWNER
    for proof in manifest["summary"]["evidence"]:
        purchase = client.get(f'/api/purchases/{proof["purchase_id"]}').json()
        evidence = client.get(f'/api/receipts/{proof["evidence_id"]}').json()
        original = read_original_bytes(app.state.demo_settings, evidence["storage_reference"])
        assert hashlib.sha256(original).hexdigest() == proof["sha256"]
        extraction = client.get(f'/api/receipts/{proof["evidence_id"]}/extraction').json()
        assert extraction["extraction_id"] == purchase["extraction_id"]
        assert {i["source_line_id"] for i in purchase["items"]} <= {i["line_id"] for i in extraction["lines"]}
        assert b"normal-storage-synthetic-sentinel" not in original


def test_exit_restart_and_reset_leave_normal_state_untouched(demo):
    root, normal, real, _, client, before = demo
    expected = content(client)
    reused = build_demo_app(normal, root / "demo")
    with TestClient(reused) as again:
        assert content(again) == expected
    rebuilt = build_demo_app(normal, root / "demo", reset=True)
    with TestClient(rebuilt) as reset:
        assert content(reset) == expected
    assert snapshot(root / "normal") == before
    assert "DEMO DATA" not in real.get("/").text


def test_reset_refuses_normal_unowned_and_symlink_storage(tmp_path):
    normal = Settings(data_dir=tmp_path / "normal" / "receipt_evidence")
    for path in (normal.data_dir.parent, normal.data_dir, tmp_path):
        with pytest.raises(ValueError, match="overlap"):
            build_demo_app(normal, path, reset=True)
    unowned = tmp_path / "unowned"
    unowned.mkdir()
    sentinel = unowned / "keep.txt"
    sentinel.write_text("Do not remove")
    with pytest.raises(ValueError, match="unowned"):
        build_demo_app(normal, unowned, reset=True)
    assert sentinel.read_text() == "Do not remove"
    linked = tmp_path / "linked"
    linked.symlink_to(unowned, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        build_demo_app(normal, linked, reset=True)