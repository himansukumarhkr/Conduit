import os
import tempfile
import shutil
from app.core.migration_engine import SeleniumJavaMigrationEngine
from app.core.catalog_manager import CatalogManager
from app.core.claude_engine import ClaudeEngine


def test_snake_and_camel_case_conversion():
    engine = SeleniumJavaMigrationEngine()
    assert engine.to_snake_case("LoginPage") == "login_page"
    assert engine.to_snake_case("enterUsername") == "enter_username"
    assert engine.to_camel_case("login_page") == "LoginPage"


def test_sample_project_generation():
    engine = SeleniumJavaMigrationEngine()
    samples = engine.get_sample_selenium_java_project()
    assert "LoginPage.java" in samples
    assert "InventoryPage.java" in samples
    assert "LoginTest.java" in samples
    assert "@FindBy" in samples["LoginPage.java"]
    assert "@Test" in samples["LoginTest.java"]


def test_classify_java_file():
    engine = SeleniumJavaMigrationEngine()
    samples = engine.get_sample_selenium_java_project()
    assert engine.classify_java_file("LoginPage.java", samples["LoginPage.java"]) == "page_object"
    assert engine.classify_java_file("LoginTest.java", samples["LoginTest.java"]) == "test"


def test_transpile_page_object():
    engine = SeleniumJavaMigrationEngine()
    samples = engine.get_sample_selenium_java_project()
    res = engine.migrate_file("LoginPage.java", samples["LoginPage.java"], "page_object")
    assert res["type"] == "page_object"
    assert res["class_name"] == "LoginPage"
    assert res["file_name"] == "login_page.py"
    code = res["code"]
    assert "from playwright.sync_api import Page, Locator, expect" in code
    assert "class LoginPage:" in code
    assert 'self.username_input = self.page.locator("#user-name")' in code
    assert "def enter_username(self, user):" in code
    assert "def is_error_displayed(self):" in code


def test_transpile_test_class():
    engine = SeleniumJavaMigrationEngine()
    samples = engine.get_sample_selenium_java_project()
    res = engine.migrate_file("LoginTest.java", samples["LoginTest.java"], "test")
    assert res["type"] == "test"
    assert res["class_name"] == "LoginTest"
    assert res["file_name"] == "test_login.py"
    code = res["code"]
    assert "import pytest" in code
    assert "from playwright.sync_api import Page, expect" in code
    assert "def test_valid_user_login(page: Page):" in code
    assert 'page.goto("https://www.saucedemo.com")' in code
    assert "def test_locked_out_user(page: Page):" in code


def test_scan_java_directory():
    tmp_dir = tempfile.mkdtemp()
    try:
        engine = SeleniumJavaMigrationEngine()
        samples = engine.get_sample_selenium_java_project()
        for fname, content in samples.items():
            with open(os.path.join(tmp_dir, fname), "w", encoding="utf-8") as f:
                f.write(content)

        scan_res = engine.scan_java_directory(tmp_dir)
        assert scan_res["total_files"] == 3
        assert len(scan_res["page_objects"]) == 2
        assert len(scan_res["tests"]) == 1
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_migrate_project_and_apply_to_conduit():
    tmp_workspace = tempfile.mkdtemp()
    tmp_java_dir = tempfile.mkdtemp()
    try:
        catalog = CatalogManager(tmp_workspace)
        engine = SeleniumJavaMigrationEngine()
        samples = engine.get_sample_selenium_java_project()
        for fname, content in samples.items():
            with open(os.path.join(tmp_java_dir, fname), "w", encoding="utf-8") as f:
                f.write(content)

        migrated_bundle = engine.migrate_project(tmp_java_dir)
        assert len(migrated_bundle) == 3

        apply_res = engine.apply_migration_to_conduit(migrated_bundle, catalog)
        assert len(apply_res["pages_written"]) == 2
        assert len(apply_res["tests_written"]) == 1
        assert apply_res["scenarios_added"] == 2

        scenarios = catalog.get_all_scenarios()
        migrated_scenarios = [s for s in scenarios if "@migrated" in s.get("tags", [])]
        assert len(migrated_scenarios) == 2
        sc_names = [s["name"] for s in migrated_scenarios]
        assert "testValidUserLogin" in sc_names
        assert "testLockedOutUser" in sc_names

        page_file = os.path.join(tmp_workspace, "pages", "login_page.py")
        assert os.path.exists(page_file)
        test_file = os.path.join(tmp_workspace, "tests", "test_login.py")
        assert os.path.exists(test_file)
    finally:
        shutil.rmtree(tmp_workspace, ignore_errors=True)
        shutil.rmtree(tmp_java_dir, ignore_errors=True)


def test_claude_engine_migration_fallback():
    engine = ClaudeEngine(api_key="")
    samples = SeleniumJavaMigrationEngine().get_sample_selenium_java_project()
    res = engine.migrate_selenium_java_to_playwright(samples["LoginPage.java"], "page_object")
    assert res["type"] == "page_object"
    assert res["class_name"] == "LoginPage"
    assert "class LoginPage:" in res["code"]
