import os
import tempfile
import time
from app.main import DesktopAPI


def test_desktop_api_scenarios_and_execution():
    with tempfile.TemporaryDirectory() as tmp_dir:
        api = DesktopAPI(tmp_dir)
        scenarios = api.get_scenarios()
        assert len(scenarios) > 0
        first_id = scenarios[0]["id"]

        logs = []
        progress_events = []
        finished_events = []

        def on_log(level, msg):
            logs.append((level, msg))

        def on_progress(data):
            progress_events.append(data)

        def on_finished(result):
            finished_events.append(result)

        test_file = os.path.join(api.catalog.tests_dir, scenarios[0]["file_name"])
        assert os.path.exists(test_file)

        api.runner.run_tests_async(
            test_file_paths=[test_file],
            browser="msedge",
            headless=True,
            env="QA",
            on_log=on_log,
            on_progress=on_progress,
            on_finished=on_finished
        )

        for _ in range(30):
            if finished_events:
                break
            time.sleep(0.5)

        assert len(logs) > 0
        assert len(progress_events) > 0
        assert len(finished_events) == 1
        assert finished_events[0]["total"] == 1
