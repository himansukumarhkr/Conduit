import ast
import re
from urllib.parse import urlparse
from typing import List, Dict, Any, Tuple
from jinja2 import Environment, FileSystemLoader
import os
import sys


class ASTNormalizer:

    def __init__(self, template_dir: str = None):
        if not template_dir:
            base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            candidate = os.path.join(base, "templates")
            if not os.path.exists(candidate):
                candidate = os.path.join(base, "app", "templates")
            template_dir = candidate
        self.jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            trim_blocks=True,
            lstrip_blocks=True
        )

    @staticmethod
    def infer_page_name(url: str, default: str = "MainPage") -> str:
        if not url or url.startswith("about:"):
            return default
        try:
            parsed = urlparse(url)
            path = parsed.path.strip("/")
            if not path or path == "":
                host = parsed.netloc.split(".")[0].capitalize()
                return f"{host}HomePage" if host else default
            segments = [s for s in path.split("/") if s and not s.isdigit()]
            if not segments:
                return default
            name = segments[-1].replace("-", " ").replace("_", " ").title().replace(" ", "")
            return f"{name}Page"
        except Exception:
            return default

    def synthesize_pom_and_test(
        self,
        scenario_name: str,
        tags: List[str],
        actions: List[Dict[str, Any]],
        scenario_description: str = ""
    ) -> Dict[str, Any]:
        pages_dict: Dict[str, Dict[str, Any]] = {}
        processed_steps: List[Dict[str, Any]] = []

        current_url = ""
        current_page_name = "MainPage"

        for action in actions:
            act_type = action.get("action")
            url = action.get("url") or current_url
            if url:
                current_url = url
                current_page_name = action.get("page_name") or self.infer_page_name(url)

            if current_page_name not in pages_dict:
                pages_dict[current_page_name] = {
                    "class_name": current_page_name,
                    "module_name": f"{self._to_snake(current_page_name)}",
                    "page_url": current_url,
                    "locators": {},
                    "methods": {}
                }

            page_data = pages_dict[current_page_name]
            sel = action.get("selector_info") or {}
            var_name = sel.get("var_name", "element")
            locator_expr = sel.get("locator_expr", "self.page.locator('body')")
            val = action.get("value", "")

            if var_name not in page_data["locators"] and act_type != "navigate":
                page_data["locators"][var_name] = {
                    "var_name": var_name,
                    "playwright_code": locator_expr
                }

            step_code, method_info = self._synthesize_step_and_method(
                current_page_name, act_type, var_name, val, action
            )

            if method_info:
                method_name = method_info["name"]
                if method_name not in page_data["methods"]:
                    page_data["methods"][method_name] = method_info

            processed_steps.append({
                "human_description": action.get("human_description", ""),
                "code": step_code,
                "action": act_type,
                "page_name": current_page_name,
                "value": val,
                "selector_info": sel
            })

        generated_pages = []
        pom_template = self.jinja_env.get_template("page_object.py.jinja")
        for p_name, p_data in pages_dict.items():
            locators_list = list(p_data["locators"].values())
            methods_list = list(p_data["methods"].values())
            rendered_code = pom_template.render(
                class_name=p_data["class_name"],
                page_url=p_data["page_url"],
                locators=locators_list,
                methods=methods_list
            )
            ast.parse(rendered_code)
            generated_pages.append({
                "class_name": p_data["class_name"],
                "file_name": f"{p_data['module_name']}.py",
                "code": rendered_code
            })

        test_template = self.jinja_env.get_template("test_spec.py.jinja")
        test_func_name = f"test_{self._to_snake(scenario_name)}"
        pom_imports = [
            {"module": f"pages.{p['module_name']}", "class_name": p["class_name"]}
            for p in pages_dict.values()
        ]
        pom_instantiations = [
            f"{self._to_snake(p['class_name'])} = {p['class_name']}(page)"
            for p in pages_dict.values()
        ]

        test_code = test_template.render(
            scenario_name=scenario_name,
            scenario_description=scenario_description or f"Test scenario for {scenario_name}",
            tags=[t.lstrip("@") for t in tags],
            test_func_name=test_func_name,
            pom_imports=pom_imports,
            pom_instantiations=pom_instantiations,
            steps=processed_steps
        )
        ast.parse(test_code)

        return {
            "test_code": test_code,
            "test_func_name": test_func_name,
            "file_name": f"{test_func_name}.py",
            "pages": generated_pages,
            "steps": processed_steps
        }

    def _synthesize_step_and_method(
        self, page_class: str, act_type: str, var_name: str, val: str, action: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        page_var = self._to_snake(page_class)

        if act_type == "navigate":
            return f'page.goto("{val}")', None

        elif act_type == "click":
            method_name = f"click_{var_name}"
            method = {
                "name": method_name,
                "params_signature": "",
                "docstring": "",
                "body_lines": [f"self.{var_name}.click()"]
            }
            step_code = f"{page_var}.{method_name}()"
            return step_code, method

        elif act_type == "fill":
            method_name = f"fill_{var_name}"
            method = {
                "name": method_name,
                "params_signature": ", value: str",
                "docstring": "",
                "body_lines": [f"self.{var_name}.fill(value)"]
            }
            step_code = f'{page_var}.{method_name}("{val}")'
            return step_code, method

        elif act_type == "assert_visible":
            method_name = f"assert_{var_name}_visible"
            method = {
                "name": method_name,
                "params_signature": "",
                "docstring": "",
                "body_lines": [f"expect(self.{var_name}).to_be_visible()"]
            }
            step_code = f"{page_var}.{method_name}()"
            return step_code, method

        elif act_type == "assert_text":
            method_name = f"assert_{var_name}_contains_text"
            method = {
                "name": method_name,
                "params_signature": ", expected_text: str",
                "docstring": "",
                "body_lines": [f"expect(self.{var_name}).to_contain_text(expected_text)"]
            }
            step_code = f'{page_var}.{method_name}("{val}")'
            return step_code, method

        elif act_type == "assert_value":
            method_name = f"assert_{var_name}_has_value"
            method = {
                "name": method_name,
                "params_signature": ", expected_val: str",
                "docstring": "",
                "body_lines": [f"expect(self.{var_name}).to_have_value(expected_val)"]
            }
        elif act_type == "press":
            method_name = f"press_{var_name}"
            method = {
                "name": method_name,
                "params_signature": ", key: str = 'Enter'",
                "docstring": "",
                "body_lines": [f"self.{var_name}.press(key)"]
            }
            step_code = f'{page_var}.{method_name}("{val}")'
            return step_code, method

        return "pass", None

    @staticmethod
    def _to_snake(name: str) -> str:
        s = re.sub(r'[\s\-]+', '_', name.strip())
        s = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', s)
        s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s)
        s = re.sub(r'[^a-zA-Z0-9_]', '', s)
        s = re.sub(r'_+', '_', s).strip('_').lower()
        return s or "test"

    @classmethod
    def reverse_parse_test_file(cls, py_content: str) -> Dict[str, Any]:
        tree = ast.parse(py_content)
        result = {
            "scenario_name": "Imported Test",
            "tags": [],
            "docstring": "",
            "steps": []
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                result["scenario_name"] = node.name.replace("test_", "").replace("_", " ").title()
                result["docstring"] = ast.get_docstring(node) or ""

                for dec in node.decorator_list:
                    if isinstance(dec, ast.Attribute) and dec.attr != "mark":
                        result["tags"].append(f"@{dec.attr}")
                    elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        result["tags"].append(f"@{dec.func.attr}")

                for stmt in node.body:
                    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                        call = stmt.value
                        call_repr = ast.unparse(call)
                        human_step = cls._call_to_human_step(call, call_repr)
                        result["steps"].append({
                            "human_description": human_step,
                            "code": call_repr
                        })

        return result

    @staticmethod
    def _call_to_human_step(call_node: ast.Call, raw_call: str) -> str:
        if "page.goto" in raw_call:
            arg = call_node.args[0].value if call_node.args and hasattr(call_node.args[0], 'value') else "URL"
            return f"Navigate to {arg}"
        if "click" in raw_call:
            func_name = getattr(call_node.func, "attr", "")
            target = func_name.replace("click_", "").replace("_", " ")
            return f"Click '{target}' button" if target else "Click element"
        if "fill" in raw_call:
            func_name = getattr(call_node.func, "attr", "")
            target = func_name.replace("fill_", "").replace("_", " ")
            val = call_node.args[0].value if call_node.args and hasattr(call_node.args[0], 'value') else ""
        if "press" in raw_call:
            func_name = getattr(call_node.func, "attr", "")
            target = func_name.replace("press_", "").replace("_", " ")
            key_val = call_node.args[0].value if call_node.args and hasattr(call_node.args[0], 'value') else "Enter"
            return f"Press key '{key_val}' on '{target}'" if target else f"Press key '{key_val}'"
        if "assert" in raw_call or "expect" in raw_call:
            return f"Assert verification: {raw_call}"
        return f"Execute: {raw_call}"
