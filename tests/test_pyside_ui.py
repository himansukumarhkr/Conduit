import os
import tempfile
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from app.ui.main_window import (
    ConduitMainWindow, ToggleSwitch, SettingsDialog, SuitesDialog, HistoryDialog, StepEditorDialog
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

        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QMessageBox

        ev_click = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPoint(5, 5), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        win.toggle_lbl.mousePressEvent(ev_click)
        assert win.code_toggle.isChecked()
        assert win.code_viewer_frame.isVisible()
        assert win.toggle_lbl.text() == "Hide Code"

        win.btn_view_steps.click()
        assert not win.code_toggle.isChecked()
        assert not win.code_viewer_frame.isVisible()
        assert win.steps_box.isVisible()
        assert win.toggle_lbl.text() == "Show Code"

        win.btn_view_code.click()
        assert win.code_toggle.isChecked()
        assert win.code_viewer_frame.isVisible()

        win.btn_view_steps.click()
        assert not win.code_viewer_frame.isVisible()

        win.set_environment("Staging")
        assert win.current_env == "Staging"

        assert win.test_data_mgr.add_environment("Dev-Test")
        win.render_env_pills()
        assert "Dev-Test" in win.test_data_mgr.get_environments()
        orig_q = QMessageBox.question
        QMessageBox.question = lambda *args, **kwargs: QMessageBox.Yes
        win.delete_specific_env("Dev-Test")
        assert "Dev-Test" not in win.test_data_mgr.get_environments()
        QMessageBox.question = orig_q

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


def test_step_editor_dialog_prepopulation():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication([])

    step_fill = {
        "human_description": "Type 'testtest' into 'password'",
        "code": "page.fill_password('testtest')"
    }
    dlg = StepEditorDialog(step_data=step_fill)
    assert dlg.action_combo.currentData() == "fill"
    assert dlg.action_combo.currentText() == "Fill / Type Text"
    assert dlg.val_edit.text() == "testtest"
    assert "password" in dlg.selector_edit.text()
    assert dlg.var_name_edit.text() == "password"
    assert dlg.desc_edit.text() == "Type 'testtest' into 'password'"

    dlg.on_save()
    saved = dlg.get_step_data()
    assert saved["action"] == "fill"
    assert saved["value"] == "testtest"
    assert saved["selector_info"]["var_name"] == "password"

    step_click = {
        "human_description": "Click 'Submit' button",
        "code": "login_page.click_submit()"
    }
    dlg_click = StepEditorDialog(step_data=step_click)
    assert dlg_click.action_combo.currentData() == "click"
    assert dlg_click.action_combo.currentText() == "Click Element"
    assert "submit" in dlg_click.selector_edit.text().lower()

    step_nav = {
        "human_description": "Navigate to https://example.com",
        "code": 'page.goto("https://example.com")'
    }
    dlg_nav = StepEditorDialog(step_data=step_nav)
    assert dlg_nav.action_combo.currentData() == "navigate"
    assert dlg_nav.val_edit.text() == "https://example.com"
