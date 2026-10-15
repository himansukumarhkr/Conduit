import os
import pytest
from PySide6.QtWidgets import QApplication
from app.core.ast_normalizer import ASTNormalizer
from app.core.selector_engine import SelectorEngine
from app.ui.main_window import StepEditorDialog

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

def test_ast_normalizer_synthesizes_dynamic_variable():
    normalizer = ASTNormalizer()
    actions = [
        {
            "action": "navigate",
            "url": "https://example.com",
            "value": "{{base_url}}",
            "variable_name": "base_url",
            "human_description": "Navigate to base_url"
        },
        {
            "action": "fill",
            "selector_info": {"var_name": "username_field", "display": "#username", "strategy": "css"},
            "value": "{{username}}",
            "variable_name": "username",
            "human_description": "Fill username"
        },
        {
            "action": "click",
            "selector_info": {"var_name": "submit_btn", "display": "#submit", "strategy": "css"},
            "human_description": "Click submit"
        }
    ]
    res = normalizer.synthesize_pom_and_test("Login Flow", ["smoke"], actions)
    code = res["test_code"]
    assert "def test_login_flow(page: Page, test_data):" in code
    assert 'vars = test_data.get("variables", {}) if isinstance(test_data, dict) else {}' in code
    assert 'page.goto(vars.get("base_url", ""))' in code
    assert 'fill_username_field(vars.get("username", ""))' in code

def test_ast_normalizer_reverse_parses_variable_call():
    py_code = """
import pytest
from playwright.sync_api import Page, expect
from pages.main_page import MainPage

def test_flow(page: Page, test_data):
    vars = test_data.get("variables", {}) if isinstance(test_data, dict) else {}
    main_page = MainPage(page)
    page.goto(vars.get("base_url", ""))
    main_page.fill_user_input(vars.get("username", ""))
    main_page.click_submit()
"""
    parsed = ASTNormalizer.reverse_parse_test_file(py_code)
    steps = parsed["steps"]
    assert len(steps) == 3
    assert steps[0]["action"] == "navigate"
    assert steps[0]["variable_name"] == "base_url"
    assert steps[0]["value"] == "{{base_url}}"
    assert steps[1]["action"] == "fill"
    assert steps[1]["variable_name"] == "username"
    assert steps[1]["value"] == "{{username}}"
    assert steps[2]["action"] == "click"

def test_step_editor_dialog_variable_selection(qapp):
    avail_vars = {
        "username": "tester@domain.com",
        "password": "secret_password_123",
        "base_url": "https://test.domain.com"
    }
    dlg = StepEditorDialog(available_vars=avail_vars)
    assert dlg.available_vars == avail_vars
    dlg._apply_variable("username")
    assert dlg.val_edit.text() == "{{username}}"
    assert dlg.selected_variable_name == "username"
    assert "tester@domain.com" in dlg.var_badge_lbl.text()
    dlg.selector_edit.setText("#user-input")
    dlg.var_name_edit.setText("user_input")
    dlg.action_combo.setCurrentIndex(1)
    dlg.on_save()
    step_data = dlg.get_step_data()
    assert step_data["action"] == "fill"
    assert step_data["variable_name"] == "username"
    assert step_data["value"] == "{{username}}"
    assert "variable 'username'" in step_data["human_description"]

def test_step_editor_dialog_auto_detect_variable_typing(qapp):
    avail_vars = {
        "user_email": "qa@test.com",
        "api_key": "xyz987"
    }
    dlg = StepEditorDialog(available_vars=avail_vars)
    dlg.val_edit.setText("{{user_email}}")
    assert dlg.selected_variable_name == "user_email"
    assert "qa@test.com" in dlg.var_badge_lbl.text()
    dlg.val_edit.setText("$api_key")
    assert dlg.selected_variable_name == "api_key"
    dlg.val_edit.setText("user_email")
    assert dlg.selected_variable_name == "user_email"

def test_selector_engine_generates_variable_human_step():
    sel = {"var_name": "password_input", "display": "password"}
    desc = SelectorEngine.generate_human_step("fill", sel, "{{password}}")
    assert desc == "Fill 'password input' with variable 'password'"
    desc_nav = SelectorEngine.generate_human_step("navigate", {}, "{{app_url}}")
    assert desc_nav == "Navigate to variable 'app_url'"
