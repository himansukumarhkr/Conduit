import subprocess
import sys
import threading
import time
import os
from typing import List, Dict, Any, Callable, Optional


class TestRunner:

    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir
        self.is_running = False
        self._current_process: Optional[subprocess.Popen] = None

    def run_tests_async(
        self,
        test_file_paths: List[str],
        browser: str = "msedge",
        headless: bool = True,
        env: str = "QA",
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

            if on_log:
                on_log("INFO", f"Starting execution of {total_tests} scenario(s) on [{browser}] [Env: {env}] [Headless: {headless}]...")

            if on_progress:
                on_progress({
                    "total": total_tests,
                    "completed": 0,
                    "current": 0,
                    "percentage": 5,
                    "status_text": f"Initializing {total_tests} scenario(s)..."
                })

            for idx, test_file in enumerate(test_file_paths, 1):
                scenario_name = os.path.splitext(os.path.basename(test_file))[0]
                if on_log:
                    on_log("INFO", f"Running scenario ({idx}/{total_tests}): {scenario_name}")

                current_pct = int(((idx - 1) / total_tests) * 90) + 10
                if on_progress:
                    on_progress({
                        "total": total_tests,
                        "completed": idx - 1,
                        "current": idx,
                        "percentage": current_pct,
                        "status_text": f"Running ({idx}/{total_tests}): {scenario_name}"
                    })

                cmd = [
                    sys.executable,
                    "-m", "pytest",
                    test_file,
                    "-v",
                    "--tb=short",
                    "-s",
                    f"--browser-channel={browser}" if browser in ("msedge", "chrome") else "",
                    "--headed" if not headless else "--headless"
                ]
                cmd = [arg for arg in cmd if arg]

                env_vars = os.environ.copy()
                env_vars["CONDUIT_ENV"] = env
                env_vars["TESTFLOW_ENV"] = env
                env_vars["PYTHONPATH"] = self.workspace_dir

                try:
                    self._current_process = subprocess.Popen(
                        cmd,
                        cwd=self.workspace_dir,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        env=env_vars,
                        text=True,
                        bufsize=1
                    )

                    if self._current_process.stdout:
                        for line in iter(self._current_process.stdout.readline, ""):
                            cleaned = line.rstrip()
                            if not cleaned:
                                continue
                            log_type = "INFO"
                            if "FAILED" in cleaned or "ERROR" in cleaned:
                                log_type = "ERROR"
                            elif "PASSED" in cleaned:
                                log_type = "SUCCESS"
                            if on_log:
                                on_log(log_type, cleaned)

                    self._current_process.wait()
                    exit_code = self._current_process.returncode

                    if exit_code == 0:
                        passed_count += 1
                        if on_log:
                            on_log("SUCCESS", f"Scenario PASSED: {scenario_name}")
                    else:
                        failed_count += 1
                        if on_log:
                            on_log("ERROR", f"Scenario FAILED: {scenario_name} (Exit code {exit_code})")

                except Exception as ex:
                    failed_count += 1
                    if on_log:
                        on_log("ERROR", f"Execution error on {scenario_name}: {str(ex)}")

            duration = round(time.time() - start_time, 2)
            self.is_running = False

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
                    "status": "Passed" if failed_count == 0 else "Failed"
                })

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def stop_execution(self):
        if self._current_process and self.is_running:
            self._current_process.terminate()
            self.is_running = False
