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

def test_step_editor_dialog_on_save_updates_step_code(qapp):
    initial_step = {
        "action": "fill",
        "code": 'main_page.fill_email_address_or_mobile_number("himansukumar")',
        "human_description": "Fill 'himansukumar' into 'email_address_or_mobile_number'",
        "page_name": "MainPage",
        "selector_info": {
            "display": "email",
            "locator_expr": 'self.page.locator("#email")',
            "strategy": "id",
            "var_name": "email_address_or_mobile_number"
        },
        "value": "himansukumar"
    }
    avail_vars = {"username": "REGRESSIONMAKER"}
    dlg = StepEditorDialog(step_data=initial_step, available_vars=avail_vars)
    dlg._apply_variable("username")
    dlg.on_save()
    updated = dlg.get_step_data()
    assert updated["value"] == "{{username}}"
    assert updated["variable_name"] == "username"
    assert updated["code"] == 'main_page.fill_email_address_or_mobile_number(vars.get("username", "himansukumar"))'
    assert updated["page_name"] == "MainPage"

def test_patch_scenario_code_with_steps_updates_literal_and_fixture():
    code = (
        "import pytest\n"
        "from playwright.sync_api import Page, expect\n"
        "from pages.main_page import MainPage\n\n"
        "@pytest.mark.Sanity\n"
        "def test_checkout_cart_journey(page: Page):\n"
        "    main_page = MainPage(page)\n"
        '    page.goto("https://www.facebook.com")\n'
        '    main_page.fill_email_address_or_mobile_number("himansukumar")\n'
        '    main_page.fill_password("testtest")\n'
        "    main_page.click_log_in_span()\n"
    )
    steps = [
        {
            "action": "navigate",
            "code": 'page.goto("https://www.facebook.com")',
            "value": "https://www.facebook.com"
        },
        {
            "action": "fill",
            "code": 'main_page.fill_email_address_or_mobile_number(vars.get("username", ""))',
            "variable_name": "username",
            "value": "{{username}}",
            "selector_info": {"var_name": "email_address_or_mobile_number"}
        },
        {
            "action": "fill",
            "code": 'main_page.fill_password("testtest")',
            "value": "testtest",
            "selector_info": {"var_name": "password"}
        },
        {
            "action": "click",
            "code": 'main_page.click_log_in_span()',
            "selector_info": {"var_name": "log_in_span"}
        }
    ]
    patched = ASTNormalizer.patch_scenario_code_with_steps(code, steps)
    assert "def test_checkout_cart_journey(page: Page, test_data):" in patched
    assert 'vars = test_data.get("variables", {}) if isinstance(test_data, dict) else {}' in patched
    assert 'main_page.fill_email_address_or_mobile_number(vars.get("username", ""))' in patched
    assert '"himansukumar"' not in patched
    assert "main_page.fill_password(\"testtest\")" in patched

def test_recorder_semantic_matching_for_input_fields():
    from app.core.recorder import BrowserRecorder
    rec = BrowserRecorder()
    rec.variables = {"username": "REGRESSIONMAKER", "password": "SecretPassword123"}
    recorded = []
    rec.on_action_recorded = lambda a: recorded.append(a)

    rec._handle_raw_event(None, {
        "action": "fill",
        "value": "himansukumar",
        "url": "https://www.facebook.com",
        "meta": {
            "tag": "input",
            "type": "text",
            "name": "email",
            "id": "email",
            "placeholder": "Email address or phone number"
        }
    })
    assert len(rec.recorded_actions) == 1
    act = rec.recorded_actions[0]
    assert act["variable_name"] == "username"
    assert act["value"] == "{{username}}"
    assert act["fallback_value"] == "himansukumar"

