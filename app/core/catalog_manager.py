import os
import re
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
        conftest_code = """import os
import json
import time
import pytest
from app.core.evidence_manager import EvidenceCollector

def pytest_configure(config):
    config.addinivalue_line("filterwarnings", "ignore::pytest.PytestUnknownMarkWarning")

class SmartVarDict(dict):
    def get(self, key, default=""):
        val = super().get(key)
        if val is not None and str(val) != "":
            return val
        kl = str(key).lower()
        for k, v in self.items():
            if str(k).lower() == kl and v is not None and str(v) != "":
                return v
        import os
        for env_k in (f"CONDUIT_VAR_{key}", key, str(key).upper(), str(key).lower()):
            if env_k in os.environ and os.environ[env_k] != "":
                return os.environ[env_k]
        return default

@pytest.fixture
def test_data():
    workspace = os.environ.get("CONDUIT_WORKSPACE", os.getcwd())
    env = os.environ.get("CONDUIT_ENV", "QA")
    candidates = [
        os.path.join(workspace, "test_data", f"{env}.json"),
        os.path.join(workspace, f"{env}.json"),
        os.path.join(os.getcwd(), "test_data", f"{env}.json")
    ]
    raw_data = None
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                    break
            except Exception:
                pass
    if not raw_data:
        try:
            from app.core.test_data_manager import TestDataManager
            raw_data = TestDataManager(workspace).get_environment_data(env)
        except Exception:
            raw_data = {"environment": env, "variables": {}}

    vars_dict = raw_data.get("variables", {}) if isinstance(raw_data, dict) else {}
    if isinstance(raw_data, dict):
        raw_data["variables"] = SmartVarDict(vars_dict)
    return raw_data

@pytest.fixture(autouse=True)
def conduit_step_evidence(request):
    has_page = "page" in request.fixturenames
    page = request.getfixturevalue("page") if has_page else None
    collector = None

    enabled = os.environ.get("CONDUIT_CAPTURE_EVIDENCE", "0") == "1"
    if enabled and page:
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

    rep_setup = getattr(request.node, "rep_setup", None)
    rep_call = getattr(request.node, "rep_call", None)
    passed = True
    if rep_setup and not rep_setup.passed:
        passed = False
    elif rep_call and not rep_call.passed:
        passed = False

    if collector:
        collector.finalize(test_passed=passed)

    if page and os.environ.get("CONDUIT_HEADLESS", "0") != "1":
        try:
            hold_mode = os.environ.get("CONDUIT_HOLD_BROWSER", "").lower()
            if hold_mode in ("manual", "open", "keep_open", "inspect"):
                page.wait_for_event("close", timeout=600000)
            else:
                hold_secs = float(os.environ.get("CONDUIT_HOLD_BROWSER_SECS", "3"))
                if not passed:
                    hold_secs = max(hold_secs, float(os.environ.get("CONDUIT_HOLD_ON_FAILURE_SECS", "5")))
                if hold_secs > 0:
                    time.sleep(hold_secs)
        except Exception:
            pass

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    device = os.environ.get("CONDUIT_DEVICE", "Desktop 1280x800")
    context_args = dict(browser_context_args)
    if "1920x1080" in device:
        context_args["viewport"] = {"width": 1920, "height": 1080}
    elif "1280x800" in device:
        context_args["viewport"] = {"width": 1280, "height": 800}
    elif "iPhone" in device:
        context_args["viewport"] = {"width": 390, "height": 844}
        context_args["is_mobile"] = True
    elif "Pixel" in device:
        context_args["viewport"] = {"width": 412, "height": 915}
        context_args["is_mobile"] = True
    elif "iPad" in device:
        context_args["viewport"] = {"width": 1024, "height": 1366}
        context_args["is_mobile"] = True
    return context_args
"""
        should_write = not os.path.exists(conftest_path)
        if not should_write:
            try:
                with open(conftest_path, "r", encoding="utf-8") as f:
                    c = f.read()
                if "SmartVarDict" not in c or "def test_data" not in c or "CONDUIT_HOLD_BROWSER" not in c or "rep_setup" not in c:
                    should_write = True
            except Exception:
                should_write = True
        if should_write:
            with open(conftest_path, "w", encoding="utf-8") as f:
                f.write(conftest_code)

    def _normalize_scenarios(self):
        from app.core.ast_normalizer import ASTNormalizer
        for sc in self.scenarios:
            steps = sc.get("steps", [])
            normalized_steps = []
            for st in steps:
                normalized_steps.append(ASTNormalizer.normalize_step(st))
            sc["steps"] = normalized_steps

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
                    self._normalize_scenarios()
                    healed_any = False
                    user_loc_replacement = 'locator("[name=\'username\'], [name=\'email\'], #email, #username, [data-testid=\'username\'], input[autocomplete*=\'username\' i], input[placeholder*=\'username\' i], input[placeholder*=\'email\' i], input[type=\'text\'], input[type=\'email\']")'
                    pass_loc_replacement = 'locator("input[type=\'password\'], [name=\'password\'], #password, [data-testid=\'password\']")'

                    for sc in self.scenarios:
                        sc_healed = False
                        for st in sc.get("steps", []):
                            s_info = st.get("selector_info") or {}
                            loc = s_info.get("locator_expr", "")
                            act = st.get("action", "")
                            if act == "fill" and ("user" in str(st.get("variable_name", "")).lower() or "user" in str(s_info.get("var_name", "")).lower()):
                                if loc in ("self.page.locator('username')", "self.page.locator('Username')", "self.page.locator('body')"):
                                    s_info["locator_expr"] = f"self.page.{user_loc_replacement}"
                                    s_info["code"] = f"page.{user_loc_replacement}"
                                    st["selector_info"] = s_info
                                    sc_healed = True
                            elif act == "fill" and ("pass" in str(st.get("variable_name", "")).lower() or "pass" in str(s_info.get("var_name", "")).lower()):
                                if loc in ("self.page.locator('password')", "self.page.locator('Password')", "self.page.locator('body')") or "get_by_text" in loc:
                                    s_info["locator_expr"] = f"self.page.{pass_loc_replacement}"
                                    s_info["code"] = f"page.{pass_loc_replacement}"
                                    st["selector_info"] = s_info
                                    sc_healed = True
                            elif act == "click" and ('get_by_role("div"' in loc or "get_by_role('div'" in loc or 'get_by_role("span"' in loc or "get_by_role('span'" in loc):
                                m_n = re.search(r'name=[\'"]([^\'"]*)[\'"]', loc)
                                nm = m_n.group(1) if m_n else "button"
                                rep = f'locator("button:has-text(\'{nm}\'), [role=\'button\']:has-text(\'{nm}\'), input[value=\'{nm}\'], div:has-text(\'{nm}\')")'
                                s_info["locator_expr"] = f"self.page.{rep}"
                                s_info["code"] = f"page.{rep}"
                                st["selector_info"] = s_info
                                sc_healed = True

                        for page in sc.get("pages", []):
                            p_code = page.get("code", "")
                            orig_p_code = p_code
                            if "role='role=" in p_code or 'get_by_role("role=' in p_code or "get_by_role('role=" in p_code:
                                p_code = re.sub(
                                    r'get_by_role\([\'"]role=[\'"]([a-zA-Z0-9_-]+)[\'"],\s*name=[\'"]([^\'"]*)[\'"]\)',
                                    r'get_by_role("\1", name="\2")',
                                    p_code
                                )
                            if 'get_by_role("div"' in p_code or "get_by_role('div'" in p_code or 'get_by_role("span"' in p_code or "get_by_role('span'" in p_code:
                                p_code = re.sub(
                                    r'get_by_role\([\'"](?:div|span)[\'"],\s*name=[\'"]([^\'"]*)[\'"]\)',
                                    r'locator("button:has-text(\'\1\'), [role=\'button\']:has-text(\'\1\'), input[value=\'\1\'], div:has-text(\'\1\')")',
                                    p_code
                                )
                            if "locator('username')" in p_code or "locator('Username')" in p_code:
                                p_code = re.sub(
                                    r"locator\([\'\"][Uu]sername[\'\"]\)",
                                    user_loc_replacement,
                                    p_code
                                )
                            if "locator('password')" in p_code or "locator('Password')" in p_code:
                                p_code = re.sub(
                                    r"locator\([\'\"][Pp]assword[\'\"]\)",
                                    pass_loc_replacement,
                                    p_code
                                )
                            if "get_by_text('Password', exact=True)" in p_code or 'get_by_text("Password", exact=True)' in p_code:
                                p_code = re.sub(
                                    r"get_by_text\([\'\"]Password[\'\"],\s*exact=True\)",
                                    pass_loc_replacement,
                                    p_code
                                )
                            if "self.Username" in p_code or "fill_Username" in p_code:
                                p_code = p_code.replace("self.Username", "self.username").replace("fill_Username", "fill_username")
                            if "self.Password" in p_code or "fill_Password" in p_code:
                                p_code = p_code.replace("self.Password", "self.password").replace("fill_Password", "fill_password")

                            if p_code != orig_p_code:
                                page["code"] = p_code
                                sc_healed = True

                        sc_code = sc.get("code", "")
                        orig_sc_code = sc_code
                        if "fill_Username" in sc_code:
                            sc_code = sc_code.replace("fill_Username", "fill_username")
                        if "fill_Password" in sc_code:
                            sc_code = sc_code.replace("fill_Password", "fill_password")
                        if sc_code != orig_sc_code:
                            sc["code"] = sc_code
                            sc_healed = True

                        if sc_healed:
                            healed_any = True
                            self._write_scenario_files(sc)

                        for page in sc.get("pages", []):
                            p_file = page.get("file_name")
                            if p_file and not os.path.exists(os.path.join(self.pages_dir, p_file)):
                                self._write_scenario_files(sc)
                                break
                    if healed_any:
                        self.save_catalog()

                    if os.path.exists(self.pages_dir):
                        for pf in os.listdir(self.pages_dir):
                            if pf.endswith(".py"):
                                p_path = os.path.join(self.pages_dir, pf)
                                try:
                                    with open(p_path, "r", encoding="utf-8") as f:
                                        p_txt = f.read()
                                    orig_txt = p_txt
                                    if "role='role=" in p_txt or 'get_by_role("role=' in p_txt or "get_by_role('role=" in p_txt:
                                        p_txt = re.sub(
                                            r'get_by_role\([\'"]role=[\'"]([a-zA-Z0-9_-]+)[\'"],\s*name=[\'"]([^\'"]*)[\'"]\)',
                                            r'get_by_role("\1", name="\2")',
                                            p_txt
                                        )
                                    if 'get_by_role("div"' in p_txt or "get_by_role('div'" in p_txt or 'get_by_role("span"' in p_txt or "get_by_role('span'" in p_txt:
                                        p_txt = re.sub(
                                            r'get_by_role\([\'"](?:div|span)[\'"],\s*name=[\'"]([^\'"]*)[\'"]\)',
                                            r'locator("button:has-text(\'\1\'), [role=\'button\']:has-text(\'\1\'), input[value=\'\1\'], div:has-text(\'\1\')")',
                                            p_txt
                                        )
                                    if "locator('username')" in p_txt or "locator('Username')" in p_txt:
                                        p_txt = re.sub(
                                            r"locator\([\'\"][Uu]sername[\'\"]\)",
                                            user_loc_replacement,
                                            p_txt
                                        )
                                    if "locator('password')" in p_txt or "locator('Password')" in p_txt:
                                        p_txt = re.sub(
                                            r"locator\([\'\"][Pp]assword[\'\"]\)",
                                            pass_loc_replacement,
                                            p_txt
                                        )
                                    if "get_by_text('Password', exact=True)" in p_txt or 'get_by_text("Password", exact=True)' in p_txt:
                                        p_txt = re.sub(
                                            r"get_by_text\([\'\"]Password[\'\"],\s*exact=True\)",
                                            pass_loc_replacement,
                                            p_txt
                                        )
                                    if "self.Username" in p_txt or "fill_Username" in p_txt:
                                        p_txt = p_txt.replace("self.Username", "self.username").replace("fill_Username", "fill_username")
                                    if "self.Password" in p_txt or "fill_Password" in p_txt:
                                        p_txt = p_txt.replace("self.Password", "self.password").replace("fill_Password", "fill_password")

                                    if p_txt != orig_txt:
                                        with open(p_path, "w", encoding="utf-8") as f:
                                            f.write(p_txt)
                                except Exception:
                                    pass

                    if os.path.exists(self.tests_dir):
                        for tf in os.listdir(self.tests_dir):
                            if tf.endswith(".py"):
                                t_path = os.path.join(self.tests_dir, tf)
                                try:
                                    with open(t_path, "r", encoding="utf-8") as f:
                                        t_txt = f.read()
                                    orig_t = t_txt
                                    if "fill_Username" in t_txt:
                                        t_txt = t_txt.replace("fill_Username", "fill_username")
                                    if "fill_Password" in t_txt:
                                        t_txt = t_txt.replace("fill_Password", "fill_password")
                                    if t_txt != orig_t:
                                        with open(t_path, "w", encoding="utf-8") as f:
                                            f.write(t_txt)
                                except Exception:
                                    pass
                    return
            except Exception as e:
                print(f"[Catalog Load Error]: {e}")

        self.scenarios = self._get_seed_scenarios()
        self._normalize_scenarios()
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
        if "steps" in scenario:
            from app.core.ast_normalizer import ASTNormalizer
            scenario["steps"] = [ASTNormalizer.normalize_step(st) for st in scenario["steps"]]

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

    def create_empty_scenario(self, name: str, tags: Optional[List[str]] = None, base_url: str = "https://example.com") -> Dict[str, Any]:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
        if not slug:
            slug = "custom_flow"
        file_name = f"test_{slug}.py"
        target_path = os.path.join(self.tests_dir, file_name)
        counter = 1
        while os.path.exists(target_path):
            file_name = f"test_{slug}_{counter}.py"
            target_path = os.path.join(self.tests_dir, file_name)
            counter += 1

        fn_name = f"test_{slug}"
        tags_list = tags if tags is not None else ["@smoke"]
        tag_decorators = "\n".join([f"@pytest.mark.{t.lstrip('@')}" for t in tags_list if t.strip()])
        if tag_decorators:
            tag_decorators += "\n"

        code = f'''import pytest
from playwright.sync_api import Page, expect

{tag_decorators}def {fn_name}(page: Page):
    page.goto("{base_url}")
'''

        steps = [
            {
                "human_description": f"1. Navigate to {base_url}",
                "code": f'page.goto("{base_url}")',
                "action": "navigate",
                "value": base_url,
                "url": base_url
            }
        ]

        scenario = {
            "id": f"sc_{int(time.time() * 1000)}",
            "name": name,
            "tags": tags_list,
            "last_execution": "Never",
            "status": "Ready",
            "duration": "--",
            "file_name": file_name,
            "steps": steps,
            "code": code,
            "pages": []
        }
        return self.add_or_update_scenario(scenario)

    def delete_scenario(self, scenario_id: str, delete_file: bool = True) -> bool:
        sc = self.get_scenario(scenario_id)
        if not sc:
            return False
        self.scenarios = [s for s in self.scenarios if s.get("id") != scenario_id]
        if delete_file:
            file_name = sc.get("file_name")
            if file_name:
                fpath = os.path.join(self.tests_dir, file_name)
                if os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
        self.save_catalog()
        return True

    def duplicate_scenario(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        sc = self.get_scenario(scenario_id)
        if not sc:
            return None
        new_name = f"{sc.get('name', 'Scenario')} (Copy)"
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", new_name.strip().lower()).strip("_")
        file_name = f"test_{slug}.py"
        target_path = os.path.join(self.tests_dir, file_name)
        counter = 1
        while os.path.exists(target_path):
            file_name = f"test_{slug}_{counter}.py"
            target_path = os.path.join(self.tests_dir, file_name)
            counter += 1

        new_sc = dict(sc)
        new_sc["id"] = f"sc_{int(time.time() * 1000)}"
        new_sc["name"] = new_name
        new_sc["file_name"] = file_name
        new_sc["last_execution"] = "Never"
        new_sc["status"] = "Ready"
        new_sc["duration"] = "--"
        if "steps" in sc:
            new_sc["steps"] = [dict(st) for st in sc["steps"]]
        if "pages" in sc:
            new_sc["pages"] = [dict(p) for p in sc["pages"]]

        return self.add_or_update_scenario(new_sc)

    def rename_scenario(self, scenario_id: str, new_name: str) -> Optional[Dict[str, Any]]:
        sc = self.get_scenario(scenario_id)
        if not sc:
            return None
        sc["name"] = new_name
        self.save_catalog()
        return sc

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
