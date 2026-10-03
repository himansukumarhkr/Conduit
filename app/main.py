import os
import sys
from typing import List, Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.core.catalog_manager import CatalogManager
from app.core.ast_normalizer import ASTNormalizer
from app.core.recorder import BrowserRecorder
from app.core.runner import TestRunner
from app.ui.main_window import ConduitMainWindow


class DesktopAPI:
    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir
        self.catalog = CatalogManager(workspace_dir)
        self.ast_engine = ASTNormalizer()
        self.runner = TestRunner(workspace_dir)
        self.recorder = None
        self._current_recording_meta = {}

    def get_scenarios(self) -> List[Dict[str, Any]]:
        return self.catalog.get_all_scenarios()

    def run_scenarios(self, scenario_ids: List[str], browser: str = "msedge", headless: bool = True, env: str = "QA", on_log=None, on_progress=None, on_finished=None):
        test_files = []
        for s_id in scenario_ids:
            sc = self.catalog.get_scenario(s_id)
            if sc and sc.get("file_name"):
                test_path = os.path.join(self.catalog.tests_dir, sc["file_name"])
                if os.path.exists(test_path):
                    test_files.append(test_path)

        if not test_files:
            if on_log:
                on_log("ERROR", "No valid test files found on disk for selected scenarios.")
            return {"status": "error", "message": "No test files found"}

        def internal_on_finished(result: Dict[str, Any]):
            status = result.get("status", "Passed")
            dur = f"{result.get('duration', 0)}s"
            for s_id in scenario_ids:
                self.catalog.update_execution_result(s_id, status, dur)
            if on_finished:
                on_finished(result)

        self.runner.run_tests_async(
            test_file_paths=test_files,
            browser=browser,
            headless=headless,
            env=env,
            on_log=on_log or (lambda lvl, msg: None),
            on_progress=on_progress or (lambda data: None),
            on_finished=internal_on_finished
        )
        return {"status": "started", "tests_count": len(test_files)}

    def start_recording(self, scenario_name: str, start_url: str, tags: List[str], browser: str = "msedge", on_action=None):
        self._current_recording_meta = {
            "name": scenario_name,
            "url": start_url,
            "tags": tags,
            "browser": browser
        }

        self.recorder = BrowserRecorder(on_action_recorded=on_action)
        self.recorder.start_recording(initial_url=start_url, browser_channel=browser)

        return {
            "status": "recording_started",
            "message": f"Browser recorder launched for '{scenario_name}' on {browser}."
        }

    def stop_recording(self):
        if not self.recorder or not self.recorder.is_recording:
            return {"status": "error", "message": "No active recording session"}

        actions = self.recorder.stop_recording()
        meta = self._current_recording_meta

        synth_result = self.ast_engine.synthesize_pom_and_test(
            scenario_name=meta.get("name", "Recorded Scenario"),
            tags=meta.get("tags", ["@smoke"]),
            actions=actions
        )

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
        return {"status": "success", "scenario": new_scenario}


def main():
    from PySide6.QtWidgets import QApplication
    workspace_dir = os.path.join(BASE_DIR, "tests_workspace")
    app = QApplication(sys.argv)
    window = ConduitMainWindow(workspace_dir)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
