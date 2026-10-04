"""Explicit, isolated operator demo built from existing synthetic test fixtures."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.config import PROJECT_ROOT, Settings

DEMO_ROOT = PROJECT_ROOT / "demo_data"
OWNER = "purchase-intelligence-synthetic-demo"
SOURCES = (
    ("test_purchase_analytics.py", "test_repeated_item_frequency_quantity_and_trace"),
    ("test_visual_recall.py", "test_walmart_food_recall_uses_representative_or_text"),
)


def fixture_records() -> list[dict]:
    """Read only the existing, named synthetic fixture calls; never evaluate code."""
    from tests.test_purchase_analytics import _milk

    records = []
    for filename, function_name in SOURCES:
        tree = ast.parse((PROJECT_ROOT / "tests" / filename).read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function_name)
        calls = sorted(
            (n for n in ast.walk(function)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "remember"),
            key=lambda n: n.lineno,
        )
        for call in calls:
            merchant, day = (ast.literal_eval(n) for n in call.args[3:5])
            items = []
            for item in call.args[5].elts:
                if isinstance(item, ast.Call):
                    if not isinstance(item.func, ast.Name) or item.func.id != "_milk":
                        raise ValueError("Unexpected fixture helper.")
                    items.append(_milk(ast.literal_eval(item.args[0])))
                else:
                    items.append(ast.literal_eval(item))
            records.append({"merchant": merchant, "date": day, "items": items})
    return records


def fixture_correction(filename: str, function_name: str, classification: str) -> dict:
    tree = ast.parse((PROJECT_ROOT / "tests" / filename).read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function_name)
    for node in ast.walk(function):
        if isinstance(node, ast.keyword) and node.arg == "json" and isinstance(node.value, ast.Dict):
            try:
                value = ast.literal_eval(node.value)
            except ValueError:
                continue
            if value.get("need_want_classification") == classification:
                return value
    raise ValueError("Existing classification fixture was not found.")


def _guard(root: Path, normal: Settings) -> Path:
    if root.is_symlink():
        raise ValueError("Demo storage must not be a symlink.")
    root = root.resolve()
    normal_root = normal.data_dir.parent.resolve()
    if root.is_relative_to(normal_root) or normal_root.is_relative_to(root):
        raise ValueError("Demo storage must not overlap normal storage.")
    if root.exists() and any(path.is_symlink() for path in root.rglob("*")):
        raise ValueError("Demo storage must not contain symlinks.")
    return root


def _seed(app, settings: Settings) -> dict:
    from fastapi.testclient import TestClient
    from app.receipt_extraction.parser import parse_receipt_text
    from app.receipt_extraction.repository import replace_extraction
    from app.receipt_intake.repository import read_original_bytes
    from tests.test_purchase_confirmation import confirmation_body
    from tests.test_receipt_extraction import receipt_png

    need = fixture_correction("live_mvp_validate.py", "prepare", "need")
    want = fixture_correction(
        "test_purchase_memory.py", "test_confirmed_purchase_becomes_recallable_history", "want",
    )
    proofs = []
    with TestClient(app) as client:
        if client.get("/api/memory").json()["purchases"]:
            raise ValueError("Demo seeding requires empty isolated storage.")
        for record in fixture_records():
            # Render the existing fixture fields using the existing receipt-image
            # helper. These are fixture evidence, not fabricated evidence rows.
            lines = [record["merchant"]]
            if record["date"]:
                lines.append(record["date"])
            lines.extend(f'{item["name"]} {item["line_total"]}' for item in record["items"])
            # The existing analytics remember() helper uses this synthetic total.
            lines.append("Total 10.00")
            original = receipt_png(lines)
            uploaded = client.post("/api/receipts", files={"file": ("synthetic-demo.png", original, "image/png")})
            uploaded.raise_for_status()
            evidence = uploaded.json()
            # Feed the exact rendered fixture text through the existing parser;
            # no OCR/model request is necessary for known synthetic source text.
            extraction = replace_extraction(
                settings, evidence["evidence_id"], parse_receipt_text(lines),
            ).to_public_dict()
            if len(extraction["lines"]) != len(record["items"]):
                raise ValueError("Fixture extraction did not preserve all source lines.")
            body = confirmation_body(extraction)
            body["merchant"], body["purchase_date"] = record["merchant"], record["date"]
            for item, fixture in zip(body["items"], record["items"], strict=True):
                item.update(item_name=fixture["name"], quantity=fixture.get("quantity"),
                            unit_price=None, line_total=fixture.get("line_total"))
            confirmed = client.post("/api/purchases", json=body)
            confirmed.raise_for_status()
            purchase = confirmed.json()
            memory = client.get(f'/api/memory/{purchase["memory_id"]}').json()
            for item in memory["items"]:
                correction = need if item["item_name"] == "Milk Gallon" else want if item["item_name"] == "ZXQ-17" else None
                if correction:
                    result = client.patch(
                        f'/api/memory/{memory["memory_id"]}/items/{item["memory_item_id"]}', json=correction,
                    )
                    result.raise_for_status()
            stored = read_original_bytes(settings, evidence["storage_reference"])
            if stored != original:
                raise ValueError("Demo receipt evidence changed.")
            proofs.append({"evidence_id": evidence["evidence_id"],
                           "purchase_id": purchase["purchase_id"],
                           "sha256": hashlib.sha256(original).hexdigest()})
        analytics = client.get("/api/analytics").json()
        recall = client.get("/api/visual-recall").json()
    return {"purchases": analytics["summary"]["remembered_purchases"],
            "items": analytics["summary"]["remembered_items"],
            "merchants": analytics["merchants"], "classifications": analytics["classifications"],
            "repeat_items": analytics["summary"]["repeating_items"],
            "food_image_states": sorted({i["display"] for i in recall["items"]}),
            "evidence": proofs}


class DemoPresentation(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method not in {"GET", "HEAD"} and request.url.path != "/api/ask":
            return JSONResponse(status_code=403, content={
                "status": "rejected", "reason": "Demo is read-only. Personal uploads are disabled.",
            })
        response = await call_next(request)
        if "text/html" not in response.headers.get("content-type", ""):
            return response
        body = b"".join([chunk async for chunk in response.body_iterator]).decode()
        banner = (
            '<section class="demo-banner" role="note" aria-label="Synthetic demo data">'
            '<strong>DEMO DATA — synthetic, read-only fixtures</strong>'
            '<p>Ask AI uses the existing test provider, not a live AI model. '
            'Purchased does not mean currently available.</p>'
            '<p>To exit, restart with the normal run.py command. '
            'Reset only this demo with run_demo.py --reset.</p></section>'
        )
        body = body.replace("</head>", '<link rel="stylesheet" href="/static/demo.css"></head>')
        body = re.sub(r"(<main\b[^>]*>)", lambda match: match.group(1) + banner, body, count=1)
        headers = dict(response.headers)
        headers.pop("content-length", None)
        return Response(body, status_code=response.status_code, headers=headers,
                        background=response.background)


def build_demo_app(normal: Settings, root: Path = DEMO_ROOT, *, reset: bool = False):
    root = _guard(root, normal)
    manifest = root / "demo-manifest.json"
    if root.exists():
        if not manifest.is_file() or json.loads(manifest.read_text()).get("owner") != OWNER:
            raise ValueError("Refusing to modify an unowned demo directory.")
        if reset:
            shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    fresh = not manifest.exists()
    if fresh:
        manifest.write_text(json.dumps({"owner": OWNER, "state": "building"}))
    settings = Settings(data_dir=root / "receipt_evidence",
                        allow_preview_embedding=normal.allow_preview_embedding)
    # app.main has a module-level app. Import it with isolated storage selected,
    # so a fresh demo process never initializes or writes normal databases.
    previous = os.environ.get("PIA_DATA_DIR")
    os.environ["PIA_DATA_DIR"] = str(settings.data_dir)
    try:
        from app.main import create_app
        from tests.test_ai_intelligence import RecordingProvider
    finally:
        if previous is None:
            os.environ.pop("PIA_DATA_DIR", None)
        else:
            os.environ["PIA_DATA_DIR"] = previous
    if fresh:
        summary = _seed(create_app(settings, ai_provider=RecordingProvider()), settings)
        manifest.write_text(json.dumps({"owner": OWNER, "state": "ready", "summary": summary}, indent=2))
    elif json.loads(manifest.read_text()).get("state") != "ready":
        raise ValueError("Demo preparation was interrupted; restart with --reset.")
    # Seed through a separate app instance; middleware must be installed before
    # the serving instance handles its first request.
    app = create_app(settings, ai_provider=RecordingProvider())
    app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/api/ai-status"]

    @app.get("/api/ai-status")
    def demo_ai_status():
        return {"status": "configured", "provider": "test-grounded-provider",
                "model": "test-only", "health_verified": False, "demo": True}

    app.state.demo_settings = settings
    app.add_middleware(DemoPresentation)
    return app