import os
import sys
import tempfile
import subprocess
import pytest
from app.core.catalog_manager import CatalogManager
from app.core.ast_normalizer import ASTNormalizer

def test_catalog_manager_auto_heals_conftest():
    with tempfile.TemporaryDirectory() as td:
        old_conftest = os.path.join(td, "conftest.py")
        with open(old_conftest, "w", encoding="utf-8") as f:
            f.write("import pytest\n\n@pytest.fixture\ndef old_fixture():\n    return 1\n")
        cm = CatalogManager(td)
        with open(old_conftest, "r", encoding="utf-8") as f:
            content = f.read()
        assert "def test_data" in content
        assert "conduit_step_evidence" in content
        assert "rep_setup" in content
        assert "CONDUIT_HOLD_BROWSER" in content

def test_ast_normalizer_patches_with_test_data_fixture():
    code = (
        "import pytest\n"
        "from playwright.sync_api import Page\n\n"
        "@pytest.mark.smoke\n"
        "def test_login(page: Page):\n"
        "    page.goto('https://example.com')\n"
    )
    steps = [
        {
            "action": "fill",
            "code": "page.fill_user(vars.get('username', 'admin'))",
            "variable_name": "username",
            "selector_info": {"var_name": "user"}
        }
    ]
    patched = ASTNormalizer.patch_scenario_code_with_steps(code, steps)
    assert "def test_data" in patched
    assert "vars = test_data.get" in patched
    assert "(page: Page, test_data):" in patched

def test_pytest_plugin_provides_test_data_to_pytest():
    with tempfile.TemporaryDirectory() as td:
        test_file = os.path.join(td, "test_check.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(
                "import pytest\n\n"
                "@pytest.mark.smoke\n"
                "def test_check(test_data):\n"
                "    assert isinstance(test_data, dict)\n"
            )
        conduit_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{td}{os.pathsep}{conduit_root}"
        cmd = [
            sys.executable,
            "-m", "pytest",
            test_file,
            "-o", "filterwarnings=ignore::pytest.PytestUnknownMarkWarning",
            "-p", "app.core.pytest_plugin"
        ]
        res = subprocess.run(cmd, env=env, capture_output=True, text=True)
        assert res.returncode == 0
        assert "1 passed" in res.stdout

def test_smart_var_dict_exact_and_case_insensitive():
    from app.core.pytest_plugin import SmartVarDict
    d = SmartVarDict({"Username": "testuser", "api_key": ""})
    assert d.get("Username") == "testuser"
    assert d.get("username") == "testuser"
    assert d.get("USERNAME") == "testuser"
    assert d.get("missing", "default_val") == "default_val"

def test_smart_var_dict_env_fallback():
    from app.core.pytest_plugin import SmartVarDict
    os.environ["CONDUIT_VAR_password"] = "env_pass_123"
    try:
        d = SmartVarDict({"password": ""})
        assert d.get("password") == "env_pass_123"
        assert d.get("Password") == "env_pass_123"
    finally:
        os.environ.pop("CONDUIT_VAR_password", None)

def test_selector_engine_parses_role_with_name():
    from app.core.selector_engine import SelectorEngine
    sel = SelectorEngine.create_custom_selector("role", "role='textbox', name='Email address or mobile number'", "email_input")
    assert sel["strategy"] == "role"
    assert 'get_by_role("textbox", name="Email address or mobile number")' in sel["code"]
    assert 'self.page.get_by_role("textbox", name="Email address or mobile number")' in sel["locator_expr"]

def test_selector_engine_parses_password_role():
    from app.core.selector_engine import SelectorEngine
    sel = SelectorEngine.create_custom_selector("role", "role='password', name='Password'", "password_input")
    assert sel["strategy"] == "role"
    assert 'get_by_role("password", name="Password")' in sel["code"]

