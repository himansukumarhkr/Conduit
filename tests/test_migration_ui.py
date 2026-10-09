import os
import tempfile
import shutil
import pytest
from PySide6.QtWidgets import QApplication
from app.core.catalog_manager import CatalogManager
from app.core.claude_engine import ClaudeEngine
from app.ui.main_window import MigrationDialog, SettingsDialog, ConduitMainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def test_migration_dialog_lifecycle(qapp):
    tmp_workspace = tempfile.mkdtemp()
    try:
        catalog = CatalogManager(tmp_workspace)
        engine = ClaudeEngine(api_key="")
        dlg = MigrationDialog(catalog, engine)

        assert dlg.files_table.rowCount() == 0
        assert not dlg.btn_transpile_all.isEnabled()

        dlg._load_sample()
        assert dlg.files_table.rowCount() == 3
        assert len(dlg.scanned_files) == 3
        assert dlg.btn_transpile_all.isEnabled()

        dlg.files_table.selectRow(0)
        dlg._on_file_selected()
        assert "package com.example" in dlg.java_view.toPlainText()

        dlg._transpile_selected()
        assert len(dlg.transpiled_cache) == 1
        assert "class LoginPage:" in dlg.python_view.toPlainText()
        assert dlg.btn_import.isEnabled()

        dlg._transpile_all()
        assert len(dlg.transpiled_cache) == 3

        apply_res = dlg.mig_engine.apply_migration_to_conduit(dlg.transpiled_cache, catalog)
        assert len(apply_res["pages_written"]) == 2
        assert len(apply_res["tests_written"]) == 1
        assert apply_res["scenarios_added"] == 2

        dlg.close()
    finally:
        shutil.rmtree(tmp_workspace, ignore_errors=True)


def test_settings_dialog_workers(qapp):
    settings = {"workers": 2, "browser": "chrome"}
    dlg = SettingsDialog(settings, ["QA", "Staging"])
    assert dlg.workers_combo.currentIndex() == 1

    dlg.workers_combo.setCurrentIndex(2)
    dlg.on_save()
    new_settings = dlg.get_settings()
    assert new_settings["workers"] == 4
    dlg.close()


def test_main_window_workers_toggle(qapp):
    tmp_workspace = tempfile.mkdtemp()
    try:
        win = ConduitMainWindow(tmp_workspace)
        assert win.settings.get("workers", 1) == 1
        assert "1 Worker" in win.btn_workers.text()

        win.toggle_workers()
        assert win.settings["workers"] == 2
        assert "2 Workers" in win.btn_workers.text()

        win.toggle_workers()
        assert win.settings["workers"] == 4
        assert "4 Workers" in win.btn_workers.text()

        win.toggle_workers()
        assert win.settings["workers"] == "auto"
        assert "Auto Workers" in win.btn_workers.text()

        win.toggle_workers()
        assert win.settings["workers"] == 1
        assert "1 Worker" in win.btn_workers.text()

        win.close()
    finally:
        shutil.rmtree(tmp_workspace, ignore_errors=True)
