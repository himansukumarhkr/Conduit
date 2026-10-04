import os
import json
import time
from typing import List, Dict, Any, Optional


class CatalogManager:

    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir
        self.pages_dir = os.path.join(workspace_dir, "pages")
        self.tests_dir = os.path.join(workspace_dir, "tests")
        self.catalog_file = os.path.join(workspace_dir, "conduit.json")
        self._ensure_dirs()
        self.scenarios: List[Dict[str, Any]] = []
        self.load_catalog()

    def _ensure_dirs(self):
        os.makedirs(self.workspace_dir, exist_ok=True)
        os.makedirs(self.pages_dir, exist_ok=True)
        os.makedirs(self.tests_dir, exist_ok=True)
        for d in (self.workspace_dir, self.pages_dir, self.tests_dir):
            init_file = os.path.join(d, "__init__.py")
            if not os.path.exists(init_file):
                with open(init_file, "w", encoding="utf-8") as f:
                    f.write('pass\n')
        conftest_path = os.path.join(self.workspace_dir, "conftest.py")
        if not os.path.exists(conftest_path):
            conftest_code = """import os
import pytest
from app.core.evidence_manager import EvidenceCollector

@pytest.fixture(autouse=True)
def conduit_step_evidence(page, request):
    enabled = os.environ.get("CONDUIT_CAPTURE_EVIDENCE", "0") == "1"
    if not enabled:
        yield
        return

    workspace = os.environ.get("CONDUIT_WORKSPACE", os.getcwd())
    scenario_name = request.node.name
    format_mode = os.environ.get("CONDUIT_EVIDENCE_FORMAT", "both")
    env = os.environ.get("CONDUIT_ENV", "QA")
    browser = os.environ.get("CONDUIT_BROWSER", "msedge")

    collector = EvidenceCollector(
        workspace_dir=workspace,
        scenario_name=scenario_name,
        format_mode=format_mode,
        env=env,
        browser=browser
    )
    collector.attach(page)

    yield

    rep_call = getattr(request.node, "rep_call", None)
    passed = rep_call.passed if rep_call else True
    collector.finalize(test_passed=passed)

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)

@pytest.fixture
def test_data():
    from app.core.test_data_manager import TestDataManager
    workspace = os.environ.get("CONDUIT_WORKSPACE", os.getcwd())
    env = os.environ.get("CONDUIT_ENV", "QA")
    mgr = TestDataManager(workspace)
    return mgr.get_environment_data(env)
"""
            with open(conftest_path, "w", encoding="utf-8") as f:
                f.write(conftest_code)

    def load_catalog(self):
        target_file = self.catalog_file
        if not os.path.exists(target_file):
            legacy_file = os.path.join(self.workspace_dir, "testflow.json")
            if os.path.exists(legacy_file):
                target_file = legacy_file

        if os.path.exists(target_file):
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.scenarios = data.get("scenarios", [])
                    return
            except Exception as e:
                print(f"[Catalog Load Error]: {e}")

        self.scenarios = self._get_seed_scenarios()
        self.save_catalog()

    def save_catalog(self):
        data = {
            "version": "1.0",
            "last_updated": time.time(),
            "scenarios": self.scenarios
        }
        with open(self.catalog_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_all_scenarios(self) -> List[Dict[str, Any]]:
        return self.scenarios

    def get_scenario(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        for sc in self.scenarios:
            if sc.get("id") == scenario_id:
                return sc
        return None

    def add_or_update_scenario(self, scenario: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.get_scenario(scenario.get("id"))
        if existing:
            existing.update(scenario)
            target = existing
        else:
            if not scenario.get("id"):
                scenario["id"] = f"sc_{int(time.time() * 1000)}"
            self.scenarios.insert(0, scenario)
            target = scenario

        self._write_scenario_files(target)
        self.save_catalog()
        return target

    def _write_scenario_files(self, sc: Dict[str, Any]):
        file_name = sc.get("file_name")
        test_code = sc.get("code")
        if file_name and test_code:
            test_path = os.path.join(self.tests_dir, file_name)
            with open(test_path, "w", encoding="utf-8") as f:
                f.write(test_code)

        for page in sc.get("pages", []):
            p_file = page.get("file_name")
            p_code = page.get("code")
            if p_file and p_code:
                page_path = os.path.join(self.pages_dir, p_file)
                with open(page_path, "w", encoding="utf-8") as f:
                    f.write(p_code)

    def update_execution_result(self, scenario_id: str, status: str, duration: str):
        sc = self.get_scenario(scenario_id)
        if sc:
            sc["status"] = status
            sc["duration"] = duration
            sc["last_execution"] = "Just now"
            self.save_catalog()

    def _get_seed_scenarios(self) -> List[Dict[str, Any]]:
        login_steps = [
            {"human_description": "1. Navigate to /login", "code": 'page.goto("https://demo.playwright.dev/todomvc/#/login")'},
            {"human_description": "2. Fill 'email' input", "code": 'login_page.fill_email("admin@conduit.io")'},
            {"human_description": "3. Fill 'password' input", "code": 'login_page.fill_password("SuperSecret123!")'},
            {"human_description": "4. Click 'Submit' button", "code": 'login_page.click_submit()'},
            {"human_description": "5. Assert success message visible", "code": 'login_page.assert_success_message_visible()'}
        ]

        login_code = '''import pytest
from playwright.sync_api import Page, expect
from pages.login_page import LoginPage

@pytest.mark.smoke
@pytest.mark.regression
def test_user_login_flow(page: Page):
    login_page = LoginPage(page)
    page.goto("https://demo.playwright.dev/todomvc/")
    login_page.fill_email("admin@conduit.io")
    login_page.fill_password("SuperSecret123!")
    login_page.click_submit()
    login_page.assert_success_message_visible()
'''

        login_page_code = '''from playwright.sync_api import Page, Locator, expect

class LoginPage:
    def __init__(self, page: Page):
        self.page = page
        self.email_input: Locator = page.locator("[data-testid='email-input']")
        self.password_input: Locator = page.get_by_label("Password")
        self.submit_button: Locator = page.get_by_role("button", name="Sign In")
        self.success_message: Locator = page.locator(".toast-success")

    def fill_email(self, email: str):
        self.email_input.fill(email)

    def fill_password(self, password: str):
        self.password_input.fill(password)

    def click_submit(self):
        self.submit_button.click()

    def assert_success_message_visible(self):
        expect(self.success_message).to_be_visible()
'''

        seeds = [
            {
                "id": "sc_001",
                "name": "User Login Flow",
                "tags": ["@smoke", "@regression"],
                "last_execution": "5 min ago",
                "status": "Passed",
                "duration": "1min 20s",
                "file_name": "test_user_login_flow.py",
                "steps": login_steps,
                "code": login_code,
                "pages": [{"class_name": "LoginPage", "file_name": "login_page.py", "code": login_page_code}]
            },
            {
                "id": "sc_002",
                "name": "Add Item to Cart",
                "tags": ["@smoke", "@checkout"],
                "last_execution": "5 min ago",
                "status": "Failed",
                "duration": "45s",
                "file_name": "test_add_item_to_cart_checkout.py",
                "steps": [
                    {"human_description": "1. Navigate to /catalog", "code": 'page.goto("https://demo.playwright.dev/todomvc/")'},
                    {"human_description": "2. Click 'Add to Cart' button", "code": 'catalog_page.click_add_to_cart()'},
                    {"human_description": "3. Assert cart counter equals '1'", "code": 'cart_page.assert_counter("1")'}
                ],
                "code": '''import pytest
from pages.catalog_page import CatalogPage
from pages.cart_page import CartPage

@pytest.mark.smoke
@pytest.mark.checkout
def test_add_item_to_cart_checkout(page):
    catalog_page = CatalogPage(page)
    cart_page = CartPage(page)
    page.goto("https://demo.playwright.dev/todomvc/")
    catalog_page.click_add_to_cart()
    cart_page.assert_counter("1")
''',
                "pages": []
            },
            {
                "id": "sc_003",
                "name": "Add Item to Cart",
                "tags": ["@smoke", "@regression"],
                "last_execution": "3 min ago",
                "status": "Passed",
                "duration": "45s",
                "file_name": "test_add_item_to_cart_regression.py",
                "steps": [
                    {"human_description": "1. Navigate to /catalog", "code": 'page.goto("https://demo.playwright.dev/todomvc/")'},
                    {"human_description": "2. Select quantity '2'", "code": 'catalog_page.select_quantity("2")'},
                    {"human_description": "3. Click 'Add to Cart' button", "code": 'catalog_page.click_add_to_cart()'},
                    {"human_description": "4. Assert cart badge visible", "code": 'cart_page.assert_badge_visible()'}
                ],
                "code": '''import pytest
from pages.catalog_page import CatalogPage
from pages.cart_page import CartPage

@pytest.mark.smoke
@pytest.mark.regression
def test_add_item_to_cart_regression(page):
    catalog_page = CatalogPage(page)
    cart_page = CartPage(page)
    page.goto("https://demo.playwright.dev/todomvc/")
    catalog_page.select_quantity("2")
    catalog_page.click_add_to_cart()
    cart_page.assert_badge_visible()
''',
                "pages": []
            },
            {
                "id": "sc_004",
                "name": "Assert Item Management",
                "tags": ["@smoke", "@checkout"],
                "last_execution": "2 min ago",
                "status": "Passed",
                "duration": "45s",
                "file_name": "test_assert_item_management.py",
                "steps": [
                    {"human_description": "1. Navigate to /admin/items", "code": 'page.goto("https://demo.playwright.dev/todomvc/")'},
                    {"human_description": "2. Assert items table visible", "code": 'admin_page.assert_items_table_visible()'},
                    {"human_description": "3. Click 'Filter by Active'", "code": 'admin_page.click_filter_active()'}
                ],
                "code": '''import pytest
from pages.admin_page import AdminPage

@pytest.mark.smoke
@pytest.mark.checkout
def test_assert_item_management(page):
    admin_page = AdminPage(page)
    page.goto("https://demo.playwright.dev/todomvc/")
    admin_page.assert_items_table_visible()
    admin_page.click_filter_active()
''',
                "pages": []
            },
            {
                "id": "sc_005",
                "name": "Assert success message Flow",
                "tags": ["@regression"],
                "last_execution": "3 min ago",
                "status": "Passed",
                "duration": "1min 20s",
                "file_name": "test_assert_success_message_flow.py",
                "steps": [
                    {"human_description": "1. Fill 'Feedback' form", "code": 'feedback_page.fill_feedback("Great platform!")'},
                    {"human_description": "2. Click 'Submit Feedback'", "code": 'feedback_page.click_submit()'},
                    {"human_description": "3. Assert toast message contains 'Success'", "code": 'feedback_page.assert_toast("Success")'}
                ],
                "code": '''import pytest
from pages.feedback_page import FeedbackPage

@pytest.mark.regression
def test_assert_success_message_flow(page):
    feedback_page = FeedbackPage(page)
    feedback_page.fill_feedback("Great platform!")
    feedback_page.click_submit()
    feedback_page.assert_toast("Success")
''',
                "pages": []
            },
            {
                "id": "sc_006",
                "name": "Assert Login Flow",
                "tags": ["@checkout"],
                "last_execution": "3 min ago",
                "status": "Passed",
                "duration": "45s",
                "file_name": "test_assert_login_flow.py",
                "steps": [
                    {"human_description": "1. Navigate to /checkout", "code": 'page.goto("https://demo.playwright.dev/todomvc/")'},
                    {"human_description": "2. Assert login required prompt visible", "code": 'checkout_page.assert_login_prompt()'}
                ],
                "code": '''import pytest
from pages.checkout_page import CheckoutPage

@pytest.mark.checkout
def test_assert_login_flow(page):
    checkout_page = CheckoutPage(page)
    page.goto("https://demo.playwright.dev/todomvc/")
    checkout_page.assert_login_prompt()
''',
                "pages": []
            },
            {
                "id": "sc_007",
                "name": "Assert success message",
                "tags": ["@smoke", "@failed"],
                "last_execution": "1 min ago",
                "status": "Passed",
                "duration": "1min 20s",
                "file_name": "test_assert_success_message.py",
                "steps": [
                    {"human_description": "1. Trigger alert message", "code": 'alert_page.trigger_alert()'},
                    {"human_description": "2. Assert banner visible", "code": 'alert_page.assert_banner_visible()'}
                ],
                "code": '''import pytest
from pages.alert_page import AlertPage

@pytest.mark.smoke
@pytest.mark.failed
def test_assert_success_message(page):
    alert_page = AlertPage(page)
    alert_page.trigger_alert()
    alert_page.assert_banner_visible()
''',
                "pages": []
            }
        ]

        for s in seeds:
            self._write_scenario_files(s)

        return seeds
