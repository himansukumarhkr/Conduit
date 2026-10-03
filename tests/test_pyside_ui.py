import os
import tempfile
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from app.ui.main_window import ConduitMainWindow, ToggleSwitch


def test_main_window_components():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory() as tmp_dir:
        win = ConduitMainWindow(tmp_dir)
        win.show()
        assert win.windowTitle() == "Conduit"
        assert win.table.rowCount() > 0
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
        win.close()
