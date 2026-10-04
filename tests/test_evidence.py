import os
import tempfile
import json
from app.core.evidence_manager import EvidenceCollector


def test_evidence_collector_both_formats():
    with tempfile.TemporaryDirectory() as tmp_dir:
        collector = EvidenceCollector(
            workspace_dir=tmp_dir,
            scenario_name="Test Checkout Flow",
            format_mode="both",
            env="QA",
            browser="msedge"
        )

        dummy_img = os.path.join(tmp_dir, "dummy.png")
        with open(dummy_img, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")

        os.makedirs(collector.evidence_dir, exist_ok=True)
        img_dest = os.path.join(collector.evidence_dir, "step_01_navigate.png")
        with open(img_dest, "wb") as f:
            f.write(open(dummy_img, "rb").read())

        collector.steps.append({
            "step_number": 1,
            "description": "Navigate to https://demo.playwright.dev/todomvc/",
            "image_path": img_dest,
            "image_name": "step_01_navigate.png",
            "status": "Passed",
            "timestamp": "12:00:00"
        })

        summary = collector.finalize(test_passed=True)

        assert os.path.exists(collector.evidence_dir)
        assert os.path.exists(img_dest)
        assert os.path.exists(collector.docx_path)
        assert collector.docx_path.endswith(".docx")

        sum_json = os.path.join(collector.evidence_dir, "summary.json")
        assert os.path.exists(sum_json)
        with open(sum_json, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert data["scenario"] == "Test Checkout Flow"
            assert data["status"] == "Passed"
            assert data["steps_count"] == 1


def test_evidence_collector_word_only():
    with tempfile.TemporaryDirectory() as tmp_dir:
        collector = EvidenceCollector(
            workspace_dir=tmp_dir,
            scenario_name="Test Login Flow",
            format_mode="word",
            env="Staging",
            browser="chrome"
        )

        dummy_img = os.path.join(tmp_dir, "dummy2.png")
        with open(dummy_img, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")

        os.makedirs(collector.evidence_dir, exist_ok=True)
        img_dest = os.path.join(collector.evidence_dir, "step_01_login.png")
        with open(img_dest, "wb") as f:
            f.write(open(dummy_img, "rb").read())

        collector.steps.append({
            "step_number": 1,
            "description": "Fill login credentials",
            "image_path": img_dest,
            "image_name": "step_01_login.png",
            "status": "Passed",
            "timestamp": "12:05:00"
        })

        summary = collector.finalize(test_passed=True)

        assert os.path.exists(collector.docx_path)
        assert not os.path.exists(img_dest)
