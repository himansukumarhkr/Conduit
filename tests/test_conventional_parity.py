import os
import ast
import tempfile
import pytest
from PySide6.QtWidgets import QApplication

from app.core.report_generator import ReportGenerator
from app.core.selector_engine import SelectorEngine
from app.core.ast_normalizer import ASTNormalizer
from app.core.runner import TestRunner
from app.ui.main_window import StepEditorDialog, ConduitMainWindow, SettingsDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def test_html_report_generator():
    with tempfile.TemporaryDirectory() as tmp_dir:
        run_data = {
            "total": 3,
            "passed": 2,
            "failed": 1,
            "duration": 14.5
        }
        scenario_results = [
            {
                "name": "Scenario One",
                "status": "Passed",
                "duration": 4.2,
                "retries_attempted": 0,
                "steps": [{"human_description": "Step 1", "code": "page.goto('url')"}]
            },
            {
                "name": "Scenario Two",
                "status": "Passed",
                "duration": 5.1,
                "retries_attempted": 1,
                "steps": [{"human_description": "Step A", "code": "page.click('btn')"}]
            },
            {
                "name": "Scenario Three",
                "status": "Failed",
                "duration": 5.2,
                "retries_attempted": 2,
                "steps": [{"human_description": "Step X", "code": "page.fill('input')"}]
            }
        ]

        report_path = ReportGenerator.generate_html_report(
            workspace_dir=tmp_dir,
            run_data=run_data,
            scenario_results=scenario_results,
            env="STAGING",
            browser="msedge",
            device="Desktop 1920x1080"
        )

        assert os.path.exists(report_path)
        assert report_path.endswith("latest_report.html")

        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "Conduit Execution Report" in content
        assert "STAGING" in content
        assert "msedge" in content
        assert "Desktop 1920x1080" in content
        assert "Scenario One" in content
        assert "Scenario Two" in content
        assert "Scenario Three" in content
        assert "66.7%" in content


def test_selector_engine_custom_selectors_and_human_steps():
    sel_css = SelectorEngine.create_custom_selector("css", "button.submit-btn", "submit_button")
    assert sel_css["var_name"] == "submit_button"
    assert "button.submit-btn" in sel_css["locator_expr"]

    sel_testid = SelectorEngine.create_custom_selector("testid", "login-input", "login_field")
    assert "data-testid='login-input'" in sel_testid["display"]

    sel_xpath = SelectorEngine.create_custom_selector("xpath", "//div[@role='dialog']", "modal_dialog")
    assert "xpath=//div[@role='dialog']" in sel_xpath["locator_expr"]

    desc_wait = SelectorEngine.generate_human_step("wait", {}, "1500")
    assert "1500ms" in desc_wait

    desc_shot = SelectorEngine.generate_human_step("take_screenshot", {}, "checkout_view.png")
    assert "checkout_view.png" in desc_shot

    desc_title = SelectorEngine.generate_human_step("assert_title", {}, "Home Page")
    assert "Home Page" in desc_title

    desc_url = SelectorEngine.generate_human_step("assert_url", {}, "/checkout")
    assert "/checkout" in desc_url

    desc_api = SelectorEngine.generate_human_step("api_request", {}, "https://api.test.com")
    assert "https://api.test.com" in desc_api


def test_ast_normalizer_reconstruct_and_step_types():
    normalizer = ASTNormalizer()
    steps = [
        {
            "action": "navigate",
            "value": "https://example.com/login",
            "human_description": "Navigate to login"
        },
        {
            "action": "fill",
            "value": "user@example.com",
            "selector_info": {"var_name": "email_input", "locator_expr": "self.page.locator('#email')"},
            "human_description": "Fill email"
        },
        {
            "action": "click",
            "value": "",
            "selector_info": {"var_name": "login_btn", "locator_expr": "self.page.locator('#login')"},
            "human_description": "Click login"
        },
        {
            "action": "wait",
            "value": "2000",
            "human_description": "Wait 2s"
        },
        {
            "action": "assert_title",
            "value": "Dashboard",
            "human_description": "Assert title"
        },
        {
            "action": "assert_url",
            "value": "/dashboard",
            "human_description": "Assert URL"
        },
        {
            "action": "take_screenshot",
            "value": "dashboard.png",
            "human_description": "Capture dashboard"
        }
    ]

    res = normalizer.synthesize_pom_and_test(
        scenario_name="User Checkout Flow",
        tags=["smoke", "e2e"],
        actions=steps
    )

    assert "test_user_checkout_flow" in res["test_func_name"]
    assert len(res["steps"]) == 7
    assert "wait_for_timeout(2000)" in res["test_code"]
    assert "to_have_title(\"Dashboard\")" in res["test_code"]
    assert "to_have_url(\"/dashboard\")" in res["test_code"]
    assert "screenshot(path=\"dashboard.png\")" in res["test_code"]
    ast.parse(res["test_code"])

    scenario_dict = {
        "name": "User Checkout Flow",
        "tags": ["smoke", "e2e"],
        "steps": steps
    }
    reconstruct_res = normalizer.reconstruct_scenario(scenario_dict)
    assert len(reconstruct_res["steps"]) == 7
    ast.parse(reconstruct_res["test_code"])


def test_ui_step_editor_and_bulk_selection(qapp):
    with tempfile.TemporaryDirectory() as tmp_dir:
        win = ConduitMainWindow(workspace_dir=tmp_dir)

        step_data = {
            "action": "fill",
            "value": "secret_pass",
            "selector_info": {"var_name": "password_field", "display": "#password"},
            "human_description": "Fill password"
        }
        dlg = StepEditorDialog(step_data=step_data, parent=win)
        saved = dlg.get_step_data()
        assert saved["action"] == "fill"
        assert saved["value"] == "secret_pass"

        win.set_bulk_selection(True)
        for r in range(win.table.rowCount()):
            assert win.table.item(r, 0).checkState().name == "Checked"

        win.set_bulk_selection(False)
        for r in range(win.table.rowCount()):
            assert win.table.item(r, 0).checkState().name == "Unchecked"

        win.search_box.setText("Login")
        win.apply_catalog_filters()
        for r in range(win.table.rowCount()):
            name = win.table.item(r, 1).text()
            if "login" in name.lower():
                assert not win.table.isRowHidden(r)

        win.search_box.setText("")
        win.apply_catalog_filters()


def test_ui_settings_retries_and_device(qapp):
    current_settings = {
        "browser": "msedge",
        "base_url": "https://example.com",
        "env": "QA",
        "timeout": 5000,
        "headless": True,
        "record_traces": True,
        "capture_evidence": True,
        "evidence_format": "both",
        "retries": 2,
        "device": "iPhone 14 (390x844)"
    }
    dlg = SettingsDialog(current_settings=current_settings)
    assert dlg.retries_combo.currentText().startswith("2")
    assert dlg.device_combo.currentText() == "iPhone 14 (390x844)"

    dlg.retries_combo.setCurrentIndex(3)
    dlg.device_combo.setCurrentText("Pixel 7 (412x915)")
    dlg.on_save()
    updated = dlg.get_settings()
    assert updated["retries"] == 3
    assert updated["device"] == "Pixel 7 (412x915)"
