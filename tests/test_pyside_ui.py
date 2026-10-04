import os
import tempfile
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from app.ui.main_window import (
    ConduitMainWindow, ToggleSwitch, SettingsDialog, SuitesDialog, HistoryDialog
)


def test_main_window_components():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory() as tmp_dir:
        win = ConduitMainWindow(tmp_dir)
        win.show()
        assert win.windowTitle() == "Conduit"
        initial_count = win.table.rowCount()
        assert initial_count > 0
        assert win.current_env == "QA"
        assert win.selected_browser == "msedge"

        assert not win.code_viewer_frame.isVisible()
        assert win.steps_box.isVisible()

        win.code_toggle.setChecked(True)
        assert win.code_viewer_frame.isVisible()
        assert not win.steps_box.isVisible()

        win.code_toggle.setChecked(False)
        assert not win.code_viewer_frame.isVisible()
        assert win.steps_box.isVisible()

        win.set_environment("Staging")
        assert win.current_env == "Staging"

        win.set_browser("chrome")
        assert win.selected_browser == "chrome"

        win.toggle_headless()
        assert not win.headless
        win.toggle_headless()
        assert win.headless

        toggle = ToggleSwitch()
        assert not toggle.isChecked()
        toggle.setChecked(True)
        assert toggle.isChecked()

        settings_dlg = SettingsDialog(win.settings)
        assert settings_dlg.windowTitle() == "Conduit Settings"
        settings_dlg.headless_chk.setChecked(False)
        settings_dlg.on_save()
        new_settings = settings_dlg.get_settings()
        assert not new_settings["headless"]

        suites_dlg = SuitesDialog(win.catalog)
        assert suites_dlg.windowTitle() == "Test Suites & Tags"

        history_dlg = HistoryDialog(win.catalog)
        assert history_dlg.windowTitle() == "Execution History"

        test_actions = [
            {
                "action": "navigate",
                "url": "https://example.com",
                "value": "https://example.com",
                "selector_info": {"var_name": "page", "display": "page"},
                "human_description": "Navigate to https://example.com"
            },
            {
                "action": "click",
                "url": "https://example.com",
                "value": "",
                "selector_info": {
                    "var_name": "login_btn",
                    "display": "button#login",
                    "locator_expr": "self.page.locator('button#login')"
                },
                "human_description": "Click 'login_btn' button"
            }
        ]

        win._current_recording_meta = {
            "name": "E2E Checkout Flow",
            "url": "https://example.com",
            "tags": ["@smoke", "@checkout"]
        }
        win.on_recording_completed(test_actions)

        assert win.table.rowCount() == initial_count + 1
        top_name = win.table.item(0, 1).text()
        assert top_name == "E2E Checkout Flow"
        assert win.steps_container_layout.count() > 0

        win.close()
