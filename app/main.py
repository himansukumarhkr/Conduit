"""
Conduit - Desktop Application Entrypoint
Orchestrates PyWebView Desktop Window, IPC API Bridge, and Automation Hub.
"""
import os
import sys
import json
import webview
from typing import List, Dict, Any

# Ensure workspace root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.core.catalog_manager import CatalogManager
from app.core.ast_normalizer import ASTNormalizer
from app.core.recorder import BrowserRecorder
from app.core.runner import TestRunner


class DesktopAPI:
    """
    Python API bridge exposed directly to JavaScript (window.pywebview.api).
    """

    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir
        self.catalog = CatalogManager(workspace_dir)
        self.ast_engine = ASTNormalizer()
        self.runner = TestRunner(workspace_dir)
        self.recorder: Optional[BrowserRecorder] = None
        self._current_recording_meta = {}
        self.window = None

    def set_window(self, window):
        self.window = window

    def get_scenarios(self) -> List[Dict[str, Any]]:
        """Returns all scenarios from the catalog."""
        return self.catalog.get_all_scenarios()

    def run_scenarios(self, scenario_ids: List[str], browser: str = "msedge", headless: bool = True, env: str = "QA"):
        """Launches pytest execution for selected scenario IDs."""
        test_files = []
        for s_id in scenario_ids:
            sc = self.catalog.get_scenario(s_id)
            if sc and sc.get("file_name"):
                test_path = os.path.join(self.catalog.tests_dir, sc["file_name"])
                if os.path.exists(test_path):
                    test_files.append(test_path)

        if not test_files:
            self._log_to_ui("ERROR", "No valid test files found on disk for selected scenarios.")
            return {"status": "error", "message": "No test files found"}

        def on_log(level: str, msg: str):
            self._log_to_ui(level, msg)

        def on_progress(data: Dict[str, Any]):
            self._emit_progress_to_ui(data)

        def on_finished(result: Dict[str, Any]):
            status = result.get("status", "Passed")
            dur = f"{result.get('duration', 0)}s"
            for s_id in scenario_ids:
                self.catalog.update_execution_result(s_id, status, dur)
            self._evaluate_js("loadScenariosFromBackend();")

        self.runner.run_tests_async(
            test_file_paths=test_files,
            browser=browser,
            headless=headless,
            env=env,
            on_log=on_log,
            on_progress=on_progress,
            on_finished=on_finished
        )
        return {"status": "started", "tests_count": len(test_files)}

    def start_recording(self, scenario_name: str, start_url: str, tags: List[str], browser: str = "msedge"):
        """Initiates a Playwright recording session with assertion overlay."""
        self._current_recording_meta = {
            "name": scenario_name,
            "url": start_url,
            "tags": tags,
            "browser": browser
        }

        def on_action(step_data: Dict[str, Any]):
            desc = step_data.get("human_description", "")
            self._log_to_ui("INFO", f"Recorded step: {desc}")

        self.recorder = BrowserRecorder(on_action_recorded=on_action)
        self.recorder.start_recording(initial_url=start_url, browser_channel=browser)

        return {
            "status": "recording_started",
            "message": f"Browser recorder launched for '{scenario_name}' on {browser}. Use Alt+Click in the browser to inject assertions."
        }

    def stop_recording(self):
        """Stops the recording session and synthesizes Page Objects + Pytest specs."""
        if not self.recorder or not self.recorder.is_recording:
            return {"status": "error", "message": "No active recording session"}

        actions = self.recorder.stop_recording()
        meta = self._current_recording_meta

        self._log_to_ui("INFO", f"Synthesizing Page Object Model and Pytest spec for {len(actions)} action(s)...")

        # Synthesize via AST Engine
        synth_result = self.ast_engine.synthesize_pom_and_test(
            scenario_name=meta.get("name", "Recorded Scenario"),
            tags=meta.get("tags", ["@smoke"]),
            actions=actions
        )

        # Save to catalog & filesystem
        new_scenario = {
            "id": f"sc_{os.urandom(4).hex()}",
            "name": meta.get("name", "Recorded Scenario"),
            "tags": meta.get("tags", ["@smoke"]),
            "last_execution": "Recorded just now",
            "status": "Passed",
            "duration": "--",
            "file_name": synth_result["file_name"],
            "steps": synth_result["steps"],
            "code": synth_result["test_code"],
            "pages": synth_result["pages"]
        }

        self.catalog.add_or_update_scenario(new_scenario)
        self._log_to_ui("SUCCESS", f"Synthesized Page Objects and Pytest scenario: {synth_result['file_name']}")

        # Refresh UI
        self._evaluate_js("loadScenariosFromBackend();")
        return {"status": "success", "scenario": new_scenario}

    def _log_to_ui(self, level: str, msg: str):
        safe_msg = json.dumps(msg)
        self._evaluate_js(f"(window.conduit_receive_log || window.testflow_receive_log) && (window.conduit_receive_log || window.testflow_receive_log)('{level}', {safe_msg});")

    def _emit_progress_to_ui(self, data: Dict[str, Any]):
        data_json = json.dumps(data)
        self._evaluate_js(f"(window.conduit_receive_progress || window.testflow_receive_progress) && (window.conduit_receive_progress || window.testflow_receive_progress)({data_json});")

    def _evaluate_js(self, script: str):
        if self.window:
            try:
                self.window.evaluate_js(script)
            except Exception:
                pass


def main():
    workspace_dir = os.path.join(BASE_DIR, "tests_workspace")
    api = DesktopAPI(workspace_dir)

    ui_dir = os.path.join(BASE_DIR, "app", "ui")
    index_html = os.path.join(ui_dir, "index.html")

    window = webview.create_window(
        title="Conduit",
        url=index_html,
        js_api=api,
        width=1340,
        height=820,
        min_size=(1080, 680),
        background_color="#080c14"
    )
    api.set_window(window)

    # Launch desktop application using Edge Chromium WebView2
    webview.start(gui="edgechromium", debug=False)


if __name__ == "__main__":
    main()
