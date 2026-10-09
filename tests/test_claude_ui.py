import os
import tempfile
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLineEdit

from app.core.claude_engine import ClaudeEngine
from app.core.test_data_manager import TestDataManager
from app.ui.main_window import (
    ConduitMainWindow,
    ClaudeWorker,
    ClaudePromptDialog,
    ClaudeHealDialog,
    ClaudeCodeDialog,
    SettingsDialog,
    TestDataDialog as DataManagerDialog
)


def test_claude_worker_execution():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication([])

    engine = ClaudeEngine()
    results = {}

    w1 = ClaudeWorker("generate_flow", engine, {"prompt": "User checkout flow", "base_url": "https://test.io"})
    w1.finished_signal.connect(lambda r: results.setdefault("flow", r))
    w1.run()
    assert "flow" in results
    assert "steps" in results["flow"]

    w2 = ClaudeWorker(
        "diagnose_and_heal",
        engine,
        {
            "scenario_name": "Login",
            "failed_step": {"action": "click", "selector_info": {"strategy": "css", "display": ".btn"}},
            "error_message": "Timeout"
        }
    )
    w2.finished_signal.connect(lambda r: results.setdefault("heal", r))
    w2.run()
    assert "heal" in results
    assert "healed_step" in results["heal"]

    w3 = ClaudeWorker("optimize_code", engine, {"code": "def test_a(): pass"})
    w3.finished_signal.connect(lambda r: results.setdefault("opt", r))
    w3.run()
    assert "opt" in results
    assert "explanation" in results["opt"]

    w4 = ClaudeWorker("synthesize_data", engine, {"topic": "Users", "count": 2})
    w4.finished_signal.connect(lambda r: results.setdefault("data", r))
    w4.run()
    assert "data" in results
    assert len(results["data"]["rows"]) == 2

    w5 = ClaudeWorker("test_connection", engine, {})
    w5.finished_signal.connect(lambda r: results.setdefault("conn", r))
    w5.run()
    assert "conn" in results
    assert not results["conn"]["success"]


def test_claude_prompt_dialog():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication([])

    engine = ClaudeEngine()
    dlg = ClaudePromptDialog(engine, base_url="https://demo.playwright.dev/todomvc/")
    assert dlg.windowTitle() == "Conduit - Claude AI Flow Generator"

    dlg.prompt_edit.setPlainText("Search product and add to cart")
    dlg.run_generation()
    assert dlg._worker is not None
    dlg._worker.wait()
    app.processEvents()

    sc = dlg.get_generated_scenario()
    assert sc is not None
    assert "id" in sc
    assert len(sc["steps"]) > 0
    assert dlg.btn_accept.isEnabled()


def test_claude_heal_dialog():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication([])

    engine = ClaudeEngine()
    dummy_sc = {
        "id": "sc_test",
        "name": "Cart Checkout",
        "steps": [
            {
                "action": "click",
                "human_description": "Click checkout button",
                "selector_info": {"strategy": "css", "locator_expr": "self.page.locator('.btn-checkout')"}
            }
        ]
    }
    dlg = ClaudeHealDialog(engine, dummy_sc, error_message="Timeout 5000ms")
    assert dlg.windowTitle() == "Conduit - Claude Autonomous Self-Healing"
    if dlg._worker:
        dlg._worker.wait()
    app.processEvents()

    healed = dlg.get_healed_data()
    assert healed is not None
    assert "healed_step" in healed
    assert dlg.btn_apply.isEnabled()


def test_claude_code_dialog():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication([])

    engine = ClaudeEngine()
    sample_code = "def test_login(page):\n    page.goto('url')\n"
    dlg = ClaudeCodeDialog(engine, sample_code)
    assert dlg.windowTitle() == "Conduit - Claude AI Code Assistant"
    if dlg._worker:
        dlg._worker.wait()
    app.processEvents()

    improved = dlg.get_optimized_code()
    assert improved is not None
    assert dlg.btn_apply.isEnabled()


def test_settings_dialog_claude_integration():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication([])

    settings = {
        "browser": "msedge",
        "base_url": "https://test.io",
        "claude_api_key": "sk-ant-test-key-99999",
        "claude_model": "claude-3-5-sonnet-20241022"
    }
    dlg = SettingsDialog(settings)
    assert dlg.claude_key_edit.text() == "sk-ant-test-key-99999"
    assert dlg.claude_key_edit.echoMode() == QLineEdit.Password

    dlg._toggle_key_visibility()
    assert dlg.claude_key_edit.echoMode() == QLineEdit.Normal
    dlg._toggle_key_visibility()
    assert dlg.claude_key_edit.echoMode() == QLineEdit.Password

    dlg.claude_model_combo.setCurrentText("claude-3-5-haiku-20241022")
    dlg.on_save()
    new_s = dlg.get_settings()
    assert new_s["claude_api_key"] == "sk-ant-test-key-99999"
    assert new_s["claude_model"] == "claude-3-5-haiku-20241022"


def test_test_data_dialog_claude_tab():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory() as tmp_dir:
        mgr = TestDataManager(tmp_dir)
        dlg = DataManagerDialog(mgr, current_env="QA", claude_api_key="sk-ant-mock", claude_model="claude-3-5-sonnet-20241022")
        assert dlg.tabs.count() == 4
        assert "Claude Synthetic Generator" in dlg.tabs.tabText(3)

        dlg.run_claude_data_synth()
        if dlg._ai_worker:
            dlg._ai_worker.wait()
        app.processEvents()

        assert len(dlg.last_ai_generated_rows) > 0
        assert dlg.btn_save_ai_dataset.isEnabled()
        dlg.ai_ds_name_edit.setText("ai_users")
        dlg.save_claude_generated_dataset()

        env_data = mgr.get_environment_data("QA")
        assert "ai_users" in env_data.get("datasets", {})


def test_main_window_claude_actions():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication([])

    with tempfile.TemporaryDirectory() as tmp_dir:
        win = ConduitMainWindow(tmp_dir)
        assert hasattr(win, "claude_engine")
        assert win.claude_engine is not None

        assert hasattr(win, "btn_claude_flow")
        assert win.btn_claude_flow.text() == "✨ Claude AI Flow"

        assert hasattr(win, "btn_auto_heal")
        assert win.btn_auto_heal.text() == "⚡ Auto-Heal"

        assert hasattr(win, "btn_claude_code")
        assert win.btn_claude_code.text() == "🤖 Claude Assistant"
