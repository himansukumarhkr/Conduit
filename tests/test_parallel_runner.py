import os
import tempfile
import shutil
import time
from app.core.runner import TestRunner
from app.core.evidence_manager import EvidenceCollector


def test_evidence_manager_process_isolation():
    tmp_dir = tempfile.mkdtemp()
    try:
        em1 = EvidenceCollector(tmp_dir, "test_flow_1")
        em2 = EvidenceCollector(tmp_dir, "test_flow_2")
        assert str(os.getpid()) in em1.evidence_dir
        assert str(os.getpid()) in em2.evidence_dir
        assert em1.evidence_dir != em2.evidence_dir
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_parallel_runner_workers_selection():
    tmp_workspace = tempfile.mkdtemp()
    try:
        runner = TestRunner(tmp_workspace)
        test1 = os.path.join(tmp_workspace, "test_sample1.py")
        test2 = os.path.join(tmp_workspace, "test_sample2.py")

        with open(test1, "w", encoding="utf-8") as f:
            f.write("def test_one():\n    assert 1 == 1\n")

        with open(test2, "w", encoding="utf-8") as f:
            f.write("def test_two():\n    assert 2 == 2\n")

        logs = []
        progress_events = []
        finished_results = []

        def on_log(level, msg):
            logs.append((level, msg))

        def on_prog(data):
            progress_events.append(data)

        def on_fin(res):
            finished_results.append(res)

        runner.run_tests_async(
            test_file_paths=[test1, test2],
            browser="chromium",
            headless=True,
            capture_evidence=False,
            workers=2,
            on_log=on_log,
            on_progress=on_prog,
            on_finished=on_fin
        )

        for _ in range(50):
            if finished_results or not runner.is_running:
                break
            time.sleep(0.2)

        assert len(finished_results) == 1
        res = finished_results[0]
        assert res["total"] == 2
        assert res["passed"] == 2
        assert res["failed"] == 0
        assert res["status"] == "Passed"

        log_texts = [msg for _, msg in logs]
        assert any("Parallel (2 workers)" in t for t in log_texts)
        assert any("[Worker-" in t for t in log_texts)
    finally:
        shutil.rmtree(tmp_workspace, ignore_errors=True)


def test_sequential_runner_single_worker():
    tmp_workspace = tempfile.mkdtemp()
    try:
        runner = TestRunner(tmp_workspace)
        test1 = os.path.join(tmp_workspace, "test_seq.py")

        with open(test1, "w", encoding="utf-8") as f:
            f.write("def test_seq():\n    assert True\n")

        logs = []
        finished_results = []

        runner.run_tests_async(
            test_file_paths=[test1],
            browser="chromium",
            headless=True,
            capture_evidence=False,
            workers=1,
            on_log=lambda lvl, msg: logs.append(msg),
            on_finished=lambda res: finished_results.append(res)
        )

        for _ in range(50):
            if finished_results or not runner.is_running:
                break
            time.sleep(0.2)

        assert len(finished_results) == 1
        res = finished_results[0]
        assert res["passed"] == 1
        assert any("Sequential (1 worker)" in t for t in logs)
    finally:
        shutil.rmtree(tmp_workspace, ignore_errors=True)
