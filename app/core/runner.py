import subprocess
import sys
import threading
import time
import os
import re
import concurrent.futures
from typing import List, Dict, Any, Callable, Optional
from app.core.report_generator import ReportGenerator


class TestRunner:
    __test__ = False

    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir
        self.is_running = False
        self._lock = threading.Lock()
        self._active_processes: List[subprocess.Popen] = []

    def _execute_single_scenario(
        self,
        test_file: str,
        browser: str,
        headless: bool,
        env: str,
        capture_evidence: bool,
        evidence_format: str,
        retries: int,
        device: str,
        worker_id: int,
        on_log: Optional[Callable[[str, str], None]] = None
    ) -> Dict[str, Any]:
        scenario_name = os.path.splitext(os.path.basename(test_file))[0]
        prefix = f"[Worker-{worker_id}] " if worker_id > 0 else ""

        if on_log:
            on_log("INFO", f"{prefix}Starting scenario: {scenario_name}")

        cmd = [
            sys.executable,
            "-m", "pytest",
            test_file,
            "-v",
            "--tb=short",
            "-s",
            f"--browser-channel={browser}" if browser in ("msedge", "chrome") else "",
            "--headed" if not headless else ""
        ]
        cmd = [arg for arg in cmd if arg]

        env_vars = os.environ.copy()
        env_vars["CONDUIT_ENV"] = env
        env_vars["TESTFLOW_ENV"] = env
        env_vars["PYTHONPATH"] = f"{self.workspace_dir}{os.pathsep}{os.getcwd()}"
        env_vars["CONDUIT_WORKSPACE"] = self.workspace_dir
        env_vars["CONDUIT_BROWSER"] = browser
        env_vars["CONDUIT_DEVICE"] = device
        env_vars["CONDUIT_CAPTURE_EVIDENCE"] = "1" if capture_evidence else "0"
        env_vars["CONDUIT_EVIDENCE_FORMAT"] = evidence_format
        env_vars["CONDUIT_WORKER_ID"] = str(worker_id)

        sc_start = time.time()
        sc_passed = False
        sc_ev_dir = ""
        sc_docx = ""
        attempts = 0
        max_attempts = 1 + max(0, retries)

        while attempts < max_attempts and not sc_passed:
            attempts += 1
            if attempts > 1 and on_log:
                on_log("WARNING", f"{prefix}Retrying {scenario_name} (Attempt {attempts}/{max_attempts})...")

            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=self.workspace_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=env_vars,
                    text=True,
                    bufsize=1
                )
                with self._lock:
                    self._active_processes.append(proc)

                if proc.stdout:
                    for line in iter(proc.stdout.readline, ""):
                        cleaned = line.rstrip()
                        if not cleaned:
                            continue
                        if "[CONDUIT_EVIDENCE]:" in cleaned:
                            ev_dir = cleaned.split("[CONDUIT_EVIDENCE]:")[-1].strip()
                            sc_ev_dir = ev_dir
                            if on_log:
                                on_log("SUCCESS", f"{prefix}Step Evidence Folder: {ev_dir}")
                            continue
                        if "[CONDUIT_DOCX]:" in cleaned:
                            docx_file = cleaned.split("[CONDUIT_DOCX]:")[-1].strip()
                            sc_docx = docx_file
                            if on_log:
                                on_log("SUCCESS", f"{prefix}Word Evidence Report: {docx_file}")
                            continue

                        log_type = "INFO"
                        if "FAILED" in cleaned or "ERROR" in cleaned:
                            log_type = "ERROR"
                        elif "PASSED" in cleaned:
                            log_type = "SUCCESS"
                        if on_log:
                            on_log(log_type, f"{prefix}{cleaned}")

                proc.wait()
                exit_code = proc.returncode
                with self._lock:
                    if proc in self._active_processes:
                        self._active_processes.remove(proc)

                if exit_code == 0:
                    sc_passed = True
                    if on_log:
                        on_log("SUCCESS", f"{prefix}Scenario PASSED: {scenario_name}")
                else:
                    if attempts >= max_attempts and on_log:
                        on_log("ERROR", f"{prefix}Scenario FAILED: {scenario_name} (Exit code {exit_code})")

            except Exception as ex:
                if attempts >= max_attempts and on_log:
                    on_log("ERROR", f"{prefix}Execution error on {scenario_name}: {str(ex)}")

        sc_dur = round(time.time() - sc_start, 2)
        return {
            "name": scenario_name,
            "status": "Passed" if sc_passed else "Failed",
            "duration": sc_dur,
            "retries_attempted": attempts - 1,
            "evidence_dir": sc_ev_dir,
            "docx_path": sc_docx,
            "passed": sc_passed
        }

    def run_tests_async(
        self,
        test_file_paths: List[str],
        browser: str = "msedge",
        headless: bool = True,
        env: str = "QA",
        capture_evidence: bool = True,
        evidence_format: str = "both",
        retries: int = 0,
        device: str = "Desktop 1280x800",
        workers: Any = 1,
        on_log: Optional[Callable[[str, str], None]] = None,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_finished: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        if self.is_running:
            if on_log:
                on_log("ERROR", "A test execution is already in progress.")
            return

        def _worker():
            self.is_running = True
            start_time = time.time()
            total_tests = len(test_file_paths)
            passed_count = 0
            failed_count = 0
            evidence_dirs = []
            evidence_reports = []
            scenario_results = []

            num_workers = 1
            if str(workers).lower() == "auto":
                num_workers = min(total_tests, max(1, os.cpu_count() or 4))
            else:
                try:
                    num_workers = max(1, int(workers))
                except Exception:
                    num_workers = 1

            if on_log:
                worker_msg = f"Parallel ({num_workers} workers)" if num_workers > 1 else "Sequential (1 worker)"
                on_log("INFO", f"Starting execution of {total_tests} scenario(s) [{worker_msg}] on [{browser}] [Env: {env}] [Device: {device}] [Headless: {headless}] [Retries: {retries}] [Evidence: {'ON (' + evidence_format + ')' if capture_evidence else 'OFF'}]...")

            if on_progress:
                on_progress({
                    "total": total_tests,
                    "completed": 0,
                    "current": 0,
                    "percentage": 5,
                    "status_text": f"Initializing {total_tests} scenario(s)..."
                })

            if num_workers > 1 and total_tests > 1:
                num_workers = min(num_workers, total_tests)
                completed_count = 0

                with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                    future_map = {
                        executor.submit(
                            self._execute_single_scenario,
                            test_file,
                            browser,
                            headless,
                            env,
                            capture_evidence,
                            evidence_format,
                            retries,
                            device,
                            (i % num_workers) + 1,
                            on_log
                        ): test_file
                        for i, test_file in enumerate(test_file_paths)
                    }

                    for future in concurrent.futures.as_completed(future_map):
                        res = future.result()
                        with self._lock:
                            scenario_results.append(res)
                            if res["passed"]:
                                passed_count += 1
                            else:
                                failed_count += 1
                            if res["evidence_dir"] and res["evidence_dir"] not in evidence_dirs:
                                evidence_dirs.append(res["evidence_dir"])
                            if res["docx_path"] and res["docx_path"] not in evidence_reports:
                                evidence_reports.append(res["docx_path"])
                            completed_count += 1
                            pct = int((completed_count / total_tests) * 90) + 10
                            if on_progress:
                                on_progress({
                                    "total": total_tests,
                                    "completed": completed_count,
                                    "current": completed_count,
                                    "percentage": pct,
                                    "status_text": f"Parallel ({completed_count}/{total_tests}) completed: {res['name']}"
                                })
            else:
                for idx, test_file in enumerate(test_file_paths, 1):
                    current_pct = int(((idx - 1) / total_tests) * 90) + 10
                    if on_progress:
                        on_progress({
                            "total": total_tests,
                            "completed": idx - 1,
                            "current": idx,
                            "percentage": current_pct,
                            "status_text": f"Running ({idx}/{total_tests}): {os.path.splitext(os.path.basename(test_file))[0]}"
                        })
                    res = self._execute_single_scenario(
                        test_file,
                        browser,
                        headless,
                        env,
                        capture_evidence,
                        evidence_format,
                        retries,
                        device,
                        0,
                        on_log
                    )
                    scenario_results.append(res)
                    if res["passed"]:
                        passed_count += 1
                    else:
                        failed_count += 1
                    if res["evidence_dir"] and res["evidence_dir"] not in evidence_dirs:
                        evidence_dirs.append(res["evidence_dir"])
                    if res["docx_path"] and res["docx_path"] not in evidence_reports:
                        evidence_reports.append(res["docx_path"])

            duration = round(time.time() - start_time, 2)
            self.is_running = False

            html_report_path = ""
            try:
                html_report_path = ReportGenerator.generate_html_report(
                    workspace_dir=self.workspace_dir,
                    run_data={
                        "total": total_tests,
                        "passed": passed_count,
                        "failed": failed_count,
                        "duration": duration
                    },
                    scenario_results=scenario_results,
                    env=env,
                    browser=browser,
                    device=device
                )
                if on_log:
                    on_log("SUCCESS", f"Interactive HTML Report: {html_report_path}")
            except Exception as ex:
                if on_log:
                    on_log("WARNING", f"Report generation error: {ex}")

            if on_progress:
                on_progress({
                    "total": total_tests,
                    "completed": total_tests,
                    "current": total_tests,
                    "percentage": 100,
                    "status_text": f"Completed {total_tests} scenarios ({passed_count} Passed, {failed_count} Failed) in {duration}s"
                })

            if on_log:
                on_log("INFO", f"Suite finished in {duration}s — {passed_count} Passed, {failed_count} Failed.")

            if on_finished:
                on_finished({
                    "total": total_tests,
                    "passed": passed_count,
                    "failed": failed_count,
                    "duration": duration,
                    "status": "Passed" if failed_count == 0 else "Failed",
                    "evidence_dirs": evidence_dirs,
                    "evidence_reports": evidence_reports,
                    "html_report": html_report_path,
                    "scenario_results": scenario_results
                })

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def stop_execution(self):
        with self._lock:
            for p in self._active_processes:
                try:
                    p.terminate()
                except Exception:
                    pass
            self._active_processes.clear()
        self.is_running = False
