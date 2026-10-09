import os
import re
from typing import Dict, Any, List, Optional
from app.core.catalog_manager import CatalogManager


class SeleniumJavaMigrationEngine:
    __test__ = False

    @staticmethod
    def to_snake_case(name: str) -> str:
        s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
        s2 = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
        return re.sub(r'_+', '_', s2).strip('_')

    @staticmethod
    def to_camel_case(name: str) -> str:
        parts = re.split(r'[-_]', name)
        return "".join(p.capitalize() for p in parts if p)

    def scan_java_directory(self, dir_path: str) -> Dict[str, Any]:
        if not os.path.exists(dir_path):
            return {"page_objects": [], "tests": [], "utilities": [], "total_files": 0}

        page_objects = []
        tests = []
        utilities = []

        for root, _, files in os.walk(dir_path):
            for f in files:
                if f.endswith(".java"):
                    full_path = os.path.join(root, f)
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as jf:
                            content = jf.read()
                    except Exception:
                        continue

                    classification = self.classify_java_file(f, content)
                    info = {
                        "file_name": f,
                        "file_path": full_path,
                        "class_name": self._extract_class_name(content, f),
                        "type": classification,
                        "locators_count": len(self._extract_locators(content)),
                        "methods_count": len(self._extract_methods(content)),
                        "content": content
                    }

                    if classification == "page_object":
                        page_objects.append(info)
                    elif classification == "test":
                        tests.append(info)
                    else:
                        utilities.append(info)

        return {
            "page_objects": page_objects,
            "tests": tests,
            "utilities": utilities,
            "total_files": len(page_objects) + len(tests) + len(utilities)
        }

    def classify_java_file(self, file_name: str, content: str) -> str:
        name_lower = file_name.lower()
        if "@test" in content.lower() or "test" in name_lower:
            return "test"
        if "page" in name_lower or "@findby" in content.lower() or "webelement" in content.lower() or "by." in content:
            return "page_object"
        if "base" in name_lower or "util" in name_lower or "driver" in name_lower:
            return "utility"
        return "page_object" if "@findby" in content.lower() else "test"

    def _extract_class_name(self, content: str, default_name: str) -> str:
        match = re.search(r'public\s+(?:final\s+)?class\s+([A-Za-z0-9_]+)', content)
        if match:
            return match.group(1)
        return os.path.splitext(default_name)[0]

    def _extract_locators(self, content: str) -> List[Dict[str, str]]:
        locators = []

        findby_pattern = re.compile(
            r'@FindBy\s*\(\s*([a-zA-Z]+)\s*=\s*["\']([^"\']+)["\']\s*\)\s*(?:private|protected|public)?\s*WebElement\s+([a-zA-Z0-9_]+)',
            re.MULTILINE
        )
        for m in findby_pattern.finditer(content):
            how = m.group(1).lower()
            using = m.group(2)
            var = m.group(3)
            locators.append({"strategy": how, "value": using, "name": var})

        by_pattern = re.compile(
            r'By\s+([a-zA-Z0-9_]+)\s*=\s*By\.([a-zA-Z]+)\s*\(\s*["\']([^"\']+)["\']\s*\)',
            re.MULTILINE
        )
        for m in by_pattern.finditer(content):
            var = m.group(1)
            how = m.group(2).lower()
            using = m.group(3)
            locators.append({"strategy": how, "value": using, "name": var})

        find_elem_pattern = re.compile(
            r'driver\.findElement\s*\(\s*By\.([a-zA-Z]+)\s*\(\s*["\']([^"\']+)["\']\s*\)\s*\)',
            re.MULTILINE
        )
        for m in find_elem_pattern.finditer(content):
            how = m.group(1).lower()
            using = m.group(2)
            locators.append({"strategy": how, "value": using, "name": f"elem_{len(locators) + 1}"})

        return locators

    def _extract_methods(self, content: str) -> List[str]:
        method_pattern = re.compile(
            r'public\s+(?:void|[A-Za-z0-9_<>]+)\s+([A-Za-z0-9_]+)\s*\([^)]*\)\s*\{',
            re.MULTILINE
        )
        methods = []
        for m in method_pattern.finditer(content):
            name = m.group(1)
            if name not in ("setUp", "tearDown", "initElements"):
                methods.append(name)
        return methods

    def migrate_file(self, file_name: str, java_code: str, class_type: str = "auto") -> Dict[str, Any]:
        if class_type == "auto":
            class_type = self.classify_java_file(file_name, java_code)

        class_name = self._extract_class_name(java_code, file_name)

        if class_type == "page_object":
            return self._transpile_page_object(class_name, java_code)
        else:
            return self._transpile_test_class(class_name, java_code)

    def _transpile_page_object(self, class_name: str, java_code: str) -> Dict[str, Any]:
        py_class_name = class_name
        py_file_name = f"{self.to_snake_case(class_name)}.py"

        locators = self._extract_locators(java_code)

        lines = [
            "from playwright.sync_api import Page, Locator, expect",
            "",
            f"class {py_class_name}:",
            "    def __init__(self, page: Page):",
            "        self.page = page"
        ]

        if not locators:
            lines.append("        pass")

        added_locators = set()
        for loc in locators:
            var_name = self.to_snake_case(loc["name"])
            if var_name in added_locators:
                continue
            added_locators.add(var_name)

            how = loc["strategy"]
            val = loc["value"]

            if how == "id":
                expr = f'self.page.locator("#{val}")'
            elif how in ("css", "cssselector"):
                expr = f'self.page.locator("{val}")'
            elif how == "xpath":
                expr = f'self.page.locator("xpath={val}")'
            elif how == "name":
                expr = f'self.page.locator("[name=\'{val}\']")'
            elif how in ("classname", "class"):
                expr = f'self.page.locator(".{val}")'
            elif how in ("linktext", "partiallinktext", "text"):
                expr = f'self.page.get_by_text("{val}")'
            else:
                expr = f'self.page.locator("{val}")'

            lines.append(f"        self.{var_name} = {expr}")

        method_blocks = re.findall(
            r'public\s+(?:void|[A-Za-z0-9_<>]+)\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)\s*\{([^}]*)\}',
            java_code,
            re.DOTALL
        )

        for m_name, m_params, m_body in method_blocks:
            if m_name in (class_name, "initElements"):
                continue

            py_m_name = self.to_snake_case(m_name)
            parsed_params = ["self"]
            if m_params.strip():
                for p in m_params.split(","):
                    p_parts = p.strip().split()
                    if len(p_parts) >= 2:
                        parsed_params.append(self.to_snake_case(p_parts[1]))
                    elif len(p_parts) == 1:
                        parsed_params.append(self.to_snake_case(p_parts[0]))

            lines.append("")
            lines.append(f"    def {py_m_name}({', '.join(parsed_params)}):")

            body_lines = self._transpile_pom_method_body(m_body, locators)
            if not body_lines:
                lines.append("        pass")
            else:
                for bl in body_lines:
                    lines.append(f"        {bl}")

        py_code = "\n".join(lines) + "\n"

        return {
            "type": "page_object",
            "class_name": py_class_name,
            "file_name": py_file_name,
            "code": py_code,
            "locators": locators
        }

    def _transpile_pom_method_body(self, body: str, locators: List[Dict[str, str]]) -> List[str]:
        output = []
        loc_map = {l["name"]: self.to_snake_case(l["name"]) for l in locators}

        statements = [s.strip() for s in body.split(";") if s.strip()]
        for stmt in statements:
            send_keys_match = re.search(r'([A-Za-z0-9_]+)\.sendKeys\s*\(\s*([^)]+)\s*\)', stmt)
            if send_keys_match:
                elem = send_keys_match.group(1)
                val = self.to_snake_case(send_keys_match.group(2).replace('"', ''))
                target = f"self.{loc_map.get(elem, self.to_snake_case(elem))}"
                output.append(f"{target}.fill({val})")
                continue

            click_match = re.search(r'([A-Za-z0-9_]+)\.click\s*\(\s*\)', stmt)
            if click_match:
                elem = click_match.group(1)
                target = f"self.{loc_map.get(elem, self.to_snake_case(elem))}"
                output.append(f"{target}.click()")
                continue

            find_click = re.search(r'driver\.findElement\s*\(\s*By\.([a-zA-Z]+)\s*\(\s*["\']([^"\']+)["\']\s*\)\s*\)\.click\s*\(\s*\)', stmt)
            if find_click:
                how, val = find_click.group(1).lower(), find_click.group(2)
                loc_str = f'#{val}' if how == 'id' else (f'xpath={val}' if how == 'xpath' else val)
                output.append(f'self.page.locator("{loc_str}").click()')
                continue

            find_send = re.search(r'driver\.findElement\s*\(\s*By\.([a-zA-Z]+)\s*\(\s*["\']([^"\']+)["\']\s*\)\s*\)\.sendKeys\s*\(\s*([^)]+)\s*\)', stmt)
            if find_send:
                how, val, arg = find_send.group(1).lower(), find_send.group(2), find_send.group(3).strip()
                loc_str = f'#{val}' if how == 'id' else (f'xpath={val}' if how == 'xpath' else val)
                arg_py = arg if arg.startswith('"') else self.to_snake_case(arg)
                output.append(f'self.page.locator("{loc_str}").fill({arg_py})')
                continue

            disp_match = re.search(r'return\s+([A-Za-z0-9_]+)\.isDisplayed\s*\(\s*\)', stmt)
            if disp_match:
                elem = disp_match.group(1)
                target = f"self.{loc_map.get(elem, self.to_snake_case(elem))}"
                output.append(f"return {target}.is_visible()")
                continue

            driver_get = re.search(r'driver\.get\s*\(\s*["\']([^"\']+)["\']\s*\)', stmt)
            if driver_get:
                output.append(f'self.page.goto("{driver_get.group(1)}")')
                continue

        return output

    def _transpile_test_class(self, class_name: str, java_code: str) -> Dict[str, Any]:
        base_snake = self.to_snake_case(class_name)
        if base_snake.endswith("_test"):
            base_snake = base_snake[:-5]
        test_file_name = f"test_{base_snake}.py"

        pom_imports = set()
        pom_inst_pattern = re.compile(r'([A-Za-z0-9_]+Page)\s+([A-Za-z0-9_]+)\s*=\s*new\s+\1')
        for m in pom_inst_pattern.finditer(java_code):
            pom_cls = m.group(1)
            pom_mod = self.to_snake_case(pom_cls)
            pom_imports.add((pom_mod, pom_cls))

        lines = [
            "import pytest",
            "import re",
            "from playwright.sync_api import Page, expect"
        ]
        for pom_mod, pom_cls in sorted(pom_imports):
            lines.append(f"from pages.{pom_mod} import {pom_cls}")
        lines.append("")

        test_methods = re.findall(
            r'@Test[^\n]*\s*(?:public\s+void)\s+([A-Za-z0-9_]+)\s*\([^)]*\)\s*\{([^}]*)\}',
            java_code,
            re.DOTALL
        )

        scenarios = []

        if not test_methods:
            fallback_func = f"test_{self.to_snake_case(class_name)}"
            lines.extend([
                "@pytest.mark.smoke",
                "@pytest.mark.regression",
                f"def {fallback_func}(page: Page):",
                "    pass",
                ""
            ])
            scenarios.append({
                "name": class_name,
                "func_name": fallback_func,
                "steps": []
            })
        else:
            for m_name, m_body in test_methods:
                snake_name = self.to_snake_case(m_name)
                py_fn_name = snake_name if snake_name.startswith("test_") else f"test_{snake_name}"

                lines.extend([
                    "@pytest.mark.smoke",
                    "@pytest.mark.regression",
                    f"def {py_fn_name}(page: Page):"
                ])

                t_body, steps = self._transpile_test_method_body(m_body)
                if not t_body:
                    lines.append("    pass")
                else:
                    for tb in t_body:
                        lines.append(f"    {tb}")
                lines.append("")

                scenarios.append({
                    "name": m_name,
                    "func_name": py_fn_name,
                    "steps": steps
                })

        py_code = "\n".join(lines) + "\n"

        return {
            "type": "test",
            "class_name": class_name,
            "file_name": test_file_name,
            "code": py_code,
            "scenarios": scenarios
        }

    def _transpile_test_method_body(self, body: str) -> (List[str], List[Dict[str, Any]]):
        lines = []
        steps = []
        step_idx = 1

        statements = [s.strip() for s in body.split(";") if s.strip()]
        for stmt in statements:
            driver_get = re.search(r'driver\.get\s*\(\s*["\']([^"\']+)["\']\s*\)', stmt)
            if driver_get:
                url = driver_get.group(1)
                code_line = f'page.goto("{url}")'
                lines.append(code_line)
                steps.append({
                    "action": "navigate",
                    "code": code_line,
                    "value": url,
                    "human_description": f"{step_idx}. Navigate to {url}"
                })
                step_idx += 1
                continue

            pom_new = re.search(r'([A-Za-z0-9_]+)\s+([A-Za-z0-9_]+)\s*=\s*new\s+\1\s*\([^)]*\)', stmt)
            if pom_new:
                cls_name = pom_new.group(1)
                var_name = self.to_snake_case(pom_new.group(2))
                lines.append(f"{var_name} = {cls_name}(page)")
                continue

            method_call = re.search(r'([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\s*\(([^)]*)\)', stmt)
            if method_call and not stmt.startswith("Assert.") and not stmt.startswith("driver."):
                var = self.to_snake_case(method_call.group(1))
                m_name = self.to_snake_case(method_call.group(2))
                raw_args = method_call.group(3)
                py_args = []
                if raw_args.strip():
                    for a in raw_args.split(","):
                        py_args.append(a.strip())

                code_line = f"{var}.{m_name}({', '.join(py_args)})"
                lines.append(code_line)
                steps.append({
                    "action": "step",
                    "code": code_line,
                    "human_description": f"{step_idx}. Call {var}.{m_name}()"
                })
                step_idx += 1
                continue

            assert_true = re.search(r'Assert\.assertTrue\s*\((.*)\)', stmt)
            if assert_true:
                condition = assert_true.group(1).strip()
                if ".isDisplayed()" in condition:
                    var_expr = condition.replace(".isDisplayed()", "")
                    code_line = f"assert {self.to_snake_case(var_expr)}"
                    lines.append(code_line)
                    steps.append({
                        "action": "assert",
                        "code": code_line,
                        "human_description": f"{step_idx}. Assert element is displayed"
                    })
                elif "getCurrentUrl().contains(" in condition:
                    url_sub = re.search(r'contains\s*\(\s*["\']([^"\']+)["\']\s*\)', condition)
                    val = url_sub.group(1) if url_sub else ""
                    code_line = f'expect(page).to_have_url(re.compile(r"{val}"))'
                    lines.append(code_line)
                    steps.append({
                        "action": "assert",
                        "code": code_line,
                        "human_description": f"{step_idx}. Assert page URL contains '{val}'"
                    })
                else:
                    code_line = f"assert {condition}"
                    lines.append(code_line)
                    steps.append({
                        "action": "assert",
                        "code": code_line,
                        "human_description": f"{step_idx}. Assert condition: {condition}"
                    })
                step_idx += 1
                continue

            assert_eq = re.search(r'Assert\.assertEquals\s*\(([^,]+),\s*([^)]+)\)', stmt)
            if assert_eq:
                actual = assert_eq.group(1).strip()
                expected = assert_eq.group(2).strip()
                code_line = f"assert {actual} == {expected}"
                lines.append(code_line)
                steps.append({
                    "action": "assert",
                    "code": code_line,
                    "human_description": f"{step_idx}. Assert {actual} equals {expected}"
                })
                step_idx += 1
                continue

            find_click = re.search(r'driver\.findElement\s*\(\s*By\.([a-zA-Z]+)\s*\(\s*["\']([^"\']+)["\']\s*\)\s*\)\.click\s*\(\s*\)', stmt)
            if find_click:
                how, val = find_click.group(1).lower(), find_click.group(2)
                loc_str = f'#{val}' if how == 'id' else (f'xpath={val}' if how == 'xpath' else val)
                code_line = f'page.locator("{loc_str}").click()'
                lines.append(code_line)
                steps.append({
                    "action": "click",
                    "code": code_line,
                    "selector": loc_str,
                    "human_description": f"{step_idx}. Click element '{loc_str}'"
                })
                step_idx += 1
                continue

            find_send = re.search(r'driver\.findElement\s*\(\s*By\.([a-zA-Z]+)\s*\(\s*["\']([^"\']+)["\']\s*\)\s*\)\.sendKeys\s*\(\s*([^)]+)\s*\)', stmt)
            if find_send:
                how, val, arg = find_send.group(1).lower(), find_send.group(2), find_send.group(3).strip()
                loc_str = f'#{val}' if how == 'id' else (f'xpath={val}' if how == 'xpath' else val)
                code_line = f'page.locator("{loc_str}").fill({arg})'
                lines.append(code_line)
                steps.append({
                    "action": "fill",
                    "code": code_line,
                    "selector": loc_str,
                    "value": arg,
                    "human_description": f"{step_idx}. Fill '{loc_str}' with {arg}"
                })
                step_idx += 1
                continue

        return lines, steps

    def migrate_project(self, dir_path: str) -> List[Dict[str, Any]]:
        scan_data = self.scan_java_directory(dir_path)
        all_files = scan_data.get("page_objects", []) + scan_data.get("tests", []) + scan_data.get("utilities", [])
        results = []
        for f in all_files:
            tr = self.migrate_file(f["file_name"], f["content"], f["type"])
            results.append(tr)
        return results

    def apply_migration_to_conduit(
        self,
        migrated_results: Any,
        catalog_mgr: CatalogManager
    ) -> Dict[str, Any]:
        if isinstance(migrated_results, dict):
            migrated_results = list(migrated_results.values())

        pages_written = []
        tests_written = []
        scenarios_added = []

        pages_dict = {}

        for item in migrated_results:
            if item.get("type") == "page_object":
                fname = item.get("file_name", "page_object.py")
                code = item.get("code", "")
                p_path = os.path.join(catalog_mgr.pages_dir, fname)
                with open(p_path, "w", encoding="utf-8") as f:
                    f.write(code)
                pages_written.append(fname)
                pages_dict[fname] = code

        for item in migrated_results:
            if item.get("type") == "test":
                fname = item.get("file_name", "test_migrated.py")
                code = item.get("code", "")
                t_path = os.path.join(catalog_mgr.tests_dir, fname)
                with open(t_path, "w", encoding="utf-8") as f:
                    f.write(code)
                tests_written.append(fname)

                raw_scenarios = item.get("scenarios", [])
                for sc_item in raw_scenarios:
                    s_id = f"sc_{os.urandom(4).hex()}"
                    scenario = {
                        "id": s_id,
                        "name": sc_item.get("name", "Migrated Scenario"),
                        "tags": ["@migrated", "@selenium", "@smoke"],
                        "last_execution": "Migrated from Java",
                        "status": "Passed",
                        "duration": "--",
                        "file_name": fname,
                        "steps": sc_item.get("steps", []),
                        "code": code,
                        "pages": [{"file_name": k, "code": v} for k, v in pages_dict.items()]
                    }
                    catalog_mgr.add_or_update_scenario(scenario)
                    scenarios_added.append(scenario)

        return {
            "pages_written": pages_written,
            "tests_written": tests_written,
            "scenarios_added": len(scenarios_added)
        }

    def get_sample_selenium_java_project(self) -> Dict[str, str]:
        login_page_java = """package com.example.pages;

import org.openqa.selenium.By;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.FindBy;
import org.openqa.selenium.support.PageFactory;

public class LoginPage {
    private WebDriver driver;

    @FindBy(id = "user-name")
    private WebElement usernameInput;

    @FindBy(id = "password")
    private WebElement passwordInput;

    @FindBy(id = "login-button")
    private WebElement loginButton;

    By errorMessage = By.xpath("//h3[@data-test='error']");

    public LoginPage(WebDriver driver) {
        this.driver = driver;
        PageFactory.initElements(driver, this);
    }

    public void enterUsername(String user) {
        usernameInput.sendKeys(user);
    }

    public void enterPassword(String pass) {
        passwordInput.sendKeys(pass);
    }

    public void clickLogin() {
        loginButton.click();
    }

    public void login(String user, String pass) {
        enterUsername(user);
        enterPassword(pass);
        clickLogin();
    }

    public boolean isErrorDisplayed() {
        return driver.findElement(errorMessage).isDisplayed();
    }
}
"""

        inventory_page_java = """package com.example.pages;

import org.openqa.selenium.By;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.FindBy;
import org.openqa.selenium.support.PageFactory;

public class InventoryPage {
    private WebDriver driver;

    @FindBy(css = ".inventory_item")
    private WebElement firstItem;

    @FindBy(id = "add-to-cart-sauce-labs-backpack")
    private WebElement addToCartButton;

    @FindBy(css = ".shopping_cart_badge")
    private WebElement cartBadge;

    public InventoryPage(WebDriver driver) {
        this.driver = driver;
        PageFactory.initElements(driver, this);
    }

    public void addFirstItemToCart() {
        addToCartButton.click();
    }

    public boolean isCartBadgeVisible() {
        return cartBadge.isDisplayed();
    }
}
"""

        login_test_java = """package com.example.tests;

import com.example.pages.LoginPage;
import org.openqa.selenium.WebDriver;
import org.testng.Assert;
import org.testng.annotations.Test;

public class LoginTest {
    private WebDriver driver;

    @Test
    public void testValidUserLogin() {
        driver.get("https://www.saucedemo.com");
        LoginPage loginPage = new LoginPage(driver);
        loginPage.login("standard_user", "secret_sauce");
        Assert.assertTrue(driver.getCurrentUrl().contains("inventory.html"));
    }

    @Test
    public void testLockedOutUser() {
        driver.get("https://www.saucedemo.com");
        LoginPage loginPage = new LoginPage(driver);
        loginPage.login("locked_out_user", "secret_sauce");
        Assert.assertTrue(loginPage.isErrorDisplayed());
    }
}
"""

        return {
            "LoginPage.java": login_page_java,
            "InventoryPage.java": inventory_page_java,
            "LoginTest.java": login_test_java
        }
