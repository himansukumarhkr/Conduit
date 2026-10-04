import os
import tempfile
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.core.test_data_manager import TestDataManager
from app.core.catalog_manager import CatalogManager
from app.core.ast_normalizer import ASTNormalizer
from app.ui.main_window import ConduitMainWindow

_app = QApplication.instance() or QApplication([])


def test_test_data_manager_environments():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        mgr = TestDataManager(tmp)
        envs = mgr.get_environments()
        assert "QA" in envs
        assert "Staging" in envs
        assert "Prod" in envs

        assert mgr.add_environment("UAT") is True
        assert "UAT" in mgr.get_environments()

        assert mgr.add_environment("UAT") is False

        mgr.set_active_environment("UAT")
        assert mgr.get_active_environment() == "UAT"

        assert mgr.remove_environment("Staging") is True
        assert "Staging" not in mgr.get_environments()

        for e in ["QA", "Prod"]:
            mgr.remove_environment(e)
        assert len(mgr.get_environments()) == 1
        assert mgr.remove_environment("UAT") is False


def test_test_data_variables_and_datasets():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        mgr = TestDataManager(tmp)
        mgr.set_variable("QA", "api_token", "qa_secret_123")
        mgr.set_variable("Prod", "api_token", "prod_secret_999")

        assert mgr.get_variables("QA")["api_token"] == "qa_secret_123"
        assert mgr.get_variables("Prod")["api_token"] == "prod_secret_999"

        mgr.save_dataset("QA", "users", [{"id": 1, "name": "QA Alice"}])
        mgr.save_dataset("Prod", "users", [{"id": 1, "name": "Prod Superuser"}])

        assert mgr.get_datasets("QA")["users"][0]["name"] == "QA Alice"
        assert mgr.get_datasets("Prod")["users"][0]["name"] == "Prod Superuser"

        assert mgr.delete_variable("QA", "api_token") is True
        assert "api_token" not in mgr.get_variables("QA")

        assert mgr.delete_dataset("QA", "users") is True
        assert "users" not in mgr.get_datasets("QA")


def test_main_window_checkbox_retention():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        win = ConduitMainWindow(tmp)
        scenarios = win.catalog.get_all_scenarios()
        assert len(scenarios) >= 3

        win.table.item(0, 0).setCheckState(Qt.Unchecked)
        win.table.item(1, 0).setCheckState(Qt.Checked)
        win.table.item(2, 0).setCheckState(Qt.Unchecked)

        win.load_scenarios()

        assert win.table.item(0, 0).checkState() == Qt.Unchecked
        assert win.table.item(1, 0).checkState() == Qt.Checked
        assert win.table.item(2, 0).checkState() == Qt.Unchecked


def test_code_editor_save_and_ast_sync():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        win = ConduitMainWindow(tmp)
        sc = win.catalog.get_all_scenarios()[0]
        win.select_scenario(sc["id"])

        new_code = (
            "def test_user_login_flow(page):\n"
            "    page.goto('https://example.com/login')\n"
            "    login_page = LoginPage(page)\n"
            "    login_page.click_submit_button()\n"
        )
        win.code_edit.setPlainText(new_code)
        win.save_current_code()

        updated_sc = win.catalog.get_scenario(sc["id"])
        assert "https://example.com/login" in updated_sc["code"]

        test_file_path = os.path.join(win.catalog.tests_dir, updated_sc["file_name"])
        with open(test_file_path, "r", encoding="utf-8") as f:
            saved_content = f.read()
        assert "https://example.com/login" in saved_content


def test_test_data_dialog_initialization():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        mgr = TestDataManager(tmp)
        from app.ui.main_window import TestDataDialog
        dlg = TestDataDialog(mgr, "QA")
        assert dlg.tabs.count() == 3
        assert dlg.var_table.rowCount() > 0
        dlg.close()
