import os
import ast
import tempfile
import pytest

from app.core.selector_engine import SelectorEngine
from app.core.ast_normalizer import ASTNormalizer
from app.core.catalog_manager import CatalogManager


def test_selector_engine_ranking():
    meta_with_testid = {
        "tag": "button",
        "attributes": {"data-testid": "submit-login", "class": "btn btn-primary"},
        "text": "Sign In",
        "role": "button"
    }
    sel = SelectorEngine.rank_selector(meta_with_testid)
    assert sel["strategy"] == "testid"
    assert "data-testid='submit-login'" in sel["code"]
    assert sel["var_name"] == "submit_login_button"

    meta_role = {
        "tag": "button",
        "attributes": {},
        "text": "Checkout Now",
        "role": "button"
    }
    sel_role = SelectorEngine.rank_selector(meta_role)
    assert sel_role["strategy"] == "role"
    assert 'get_by_role("button", name="Checkout Now")' in sel_role["code"]


def test_selector_engine_human_step():
    sel = {"var_name": "email_input", "display": "email input"}
    step_fill = SelectorEngine.generate_human_step("fill", sel, "user@test.com")
    assert "Fill 'email input' with 'user@test.com'" == step_fill

    step_click = SelectorEngine.generate_human_step("click", sel)
    assert "Click 'email input'" == step_click

    step_assert = SelectorEngine.generate_human_step("assert_visible", sel)
    assert "Assert 'email input' is visible" == step_assert


def test_ast_normalizer_synthesis():
    normalizer = ASTNormalizer()
    scenario_name = "User Login Flow"
    tags = ["@smoke", "@regression"]
    actions = [
        {
            "action": "navigate",
            "url": "https://app.example.com/login",
            "value": "https://app.example.com/login",
            "selector_info": {"var_name": "page"},
            "human_description": "1. Navigate to /login"
        },
        {
            "action": "fill",
            "url": "https://app.example.com/login",
            "value": "admin@example.com",
            "selector_info": {
                "var_name": "email_input",
                "locator_expr": "self.page.locator('[data-testid=\"email\"]')",
                "display": "data-testid='email'"
            },
            "human_description": "2. Fill 'email' input"
        },
        {
            "action": "click",
            "url": "https://app.example.com/login",
            "value": "",
            "selector_info": {
                "var_name": "submit_button",
                "locator_expr": "self.page.get_by_role('button', name='Sign In')",
                "display": "role='button', name='Sign In'"
            },
            "human_description": "3. Click 'Submit' button"
        },
        {
            "action": "assert_visible",
            "url": "https://app.example.com/login",
            "value": "",
            "selector_info": {
                "var_name": "dashboard_banner",
                "locator_expr": "self.page.locator('.welcome-banner')",
                "display": ".welcome-banner"
            },
            "human_description": "4. Assert dashboard banner visible"
        }
    ]

    result = normalizer.synthesize_pom_and_test(
        scenario_name=scenario_name,
        tags=tags,
        actions=actions
    )

    assert "def test_user_login_flow(page: Page):" in result["test_code"]
    assert "@pytest.mark.smoke" in result["test_code"]
    assert "@pytest.mark.regression" in result["test_code"]
    ast.parse(result["test_code"])

    assert len(result["pages"]) == 1
    pom = result["pages"][0]
    assert pom["class_name"] == "LoginPage"
    assert "class LoginPage:" in pom["code"]
    assert "def fill_email_input(self, value: str):" in pom["code"]
    assert "def click_submit_button(self):" in pom["code"]
    assert "def assert_dashboard_banner_visible(self):" in pom["code"]
    ast.parse(pom["code"])


def test_ast_normalizer_reverse_parser():
    sample_pytest = '''import pytest

@pytest.mark.smoke
def test_checkout_journey(page):
    page.goto("https://shop.example.com")
    catalog_page.click_add_to_cart()
    cart_page.fill_promo_code("DISCOUNT50")
'''
    parsed = ASTNormalizer.reverse_parse_test_file(sample_pytest)
    assert parsed["scenario_name"] == "Checkout Journey"
    assert "@smoke" in parsed["tags"]
    assert len(parsed["steps"]) == 3
    assert parsed["steps"][0]["human_description"] == "Navigate to https://shop.example.com"


def test_catalog_manager():
    with tempfile.TemporaryDirectory() as tmp_dir:
        cm = CatalogManager(tmp_dir)
        scenarios = cm.get_all_scenarios()
        assert len(scenarios) >= 5
        assert scenarios[0]["name"] == "User Login Flow"
        assert os.path.exists(os.path.join(tmp_dir, "conduit.json"))
        assert os.path.exists(os.path.join(tmp_dir, "tests", "test_user_login_flow.py"))
