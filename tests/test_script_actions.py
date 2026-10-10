import os
import tempfile
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton

from app.core.catalog_manager import CatalogManager
from app.ui.main_window import ConduitMainWindow, NewScriptDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def test_catalog_manager_script_crud():
    with tempfile.TemporaryDirectory() as tmp_dir:
        catalog = CatalogManager(tmp_dir)
        initial_len = len(catalog.get_all_scenarios())

        created = catalog.create_empty_scenario(
            name="New Checkout Workflow",
            tags=["@smoke", "@fast"],
            base_url="https://demo.playwright.dev"
        )
        assert created["name"] == "New Checkout Workflow"
        assert "@smoke" in created["tags"]
        assert len(catalog.get_all_scenarios()) == initial_len + 1
        test_file = os.path.join(tmp_dir, "tests", created["file_name"])
        assert os.path.exists(test_file)
        with open(test_file, "r", encoding="utf-8") as f:
            code = f.read()
        assert "def test_new_checkout_workflow(page: Page):" in code
        assert 'page.goto("https://demo.playwright.dev")' in code

        duplicated = catalog.duplicate_scenario(created["id"])
        assert duplicated is not None
        assert "Copy" in duplicated["name"]
        assert len(catalog.get_all_scenarios()) == initial_len + 2
        dup_file = os.path.join(tmp_dir, "tests", duplicated["file_name"])
        assert os.path.exists(dup_file)

        renamed = catalog.rename_scenario(created["id"], "Renamed Checkout Workflow")
        assert renamed["name"] == "Renamed Checkout Workflow"
        assert catalog.get_scenario(created["id"])["name"] == "Renamed Checkout Workflow"

        del_res = catalog.delete_scenario(created["id"], delete_file=True)
        assert del_res is True
        assert catalog.get_scenario(created["id"]) is None
        assert not os.path.exists(test_file)
        assert len(catalog.get_all_scenarios()) == initial_len + 1


def test_ui_new_script_dialog(qapp):
    dlg = NewScriptDialog(default_url="https://example.com/login")
    assert dlg.windowTitle() == "Create New Test Script"
    dlg.name_edit.setText("Smoke Test 1")
    dlg.url_edit.setText("https://example.com/home")
    dlg.tags_edit.setText("@smoke, @ui")
    name, url, tags, mode = dlg.get_data()
    assert name == "Smoke Test 1"
    assert url == "https://example.com/home"
    assert "@smoke" in tags
    assert "@ui" in tags
    assert mode == "blank"
    dlg.close()


def test_ui_script_row_actions_and_buttons(qapp):
    with tempfile.TemporaryDirectory() as tmp_dir:
        win = ConduitMainWindow(workspace_dir=tmp_dir)
        win.show()

        assert hasattr(win, "btn_add_script")
        assert win.btn_add_script.text() == "+ New Script"
        assert hasattr(win, "btn_delete_flow")
        assert "Delete" in win.btn_delete_flow.text()

        init_count = win.table.rowCount()
        assert init_count > 0

        act_widget = win.table.cellWidget(0, 6)
        assert act_widget is not None
        buttons = act_widget.findChildren(QPushButton)
        assert len(buttons) == 2
        play_btn = buttons[0]
        more_btn = buttons[1]
        assert play_btn.text() == "▶"
        assert more_btn.text() == "⋮"

        sc = win.catalog.create_empty_scenario("Dynamic UI Flow")
        win.load_scenarios(current_selected=sc["id"])
        assert win.table.rowCount() == init_count + 1

        win.duplicate_scenario(sc["id"])
        assert win.table.rowCount() == init_count + 2

        all_sc = win.catalog.get_all_scenarios()
        dup_sc = [s for s in all_sc if "Dynamic UI Flow (Copy)" in s["name"]][0]

        win.catalog.rename_scenario(dup_sc["id"], "Custom Renamed Flow")
        win.load_scenarios(current_selected=dup_sc["id"])
        assert win.table.item(0, 1).text() == "Custom Renamed Flow" or any(win.table.item(r, 1).text() == "Custom Renamed Flow" for r in range(win.table.rowCount()))

        win.catalog.delete_scenario(dup_sc["id"], delete_file=True)
        win.load_scenarios()
        assert win.table.rowCount() == init_count + 1

        win.close()
