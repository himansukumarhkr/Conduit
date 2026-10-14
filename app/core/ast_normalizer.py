import ast
import re
from urllib.parse import urlparse
from typing import List, Dict, Any, Tuple
from jinja2 import Environment, FileSystemLoader
import os
import sys
from app.core.selector_engine import SelectorEngine



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
            norm_action = self.normalize_step(action)
            act_type = norm_action.get("action")
            raw_code = norm_action.get("code")
            if act_type == "custom" and raw_code:
                processed_steps.append({
                    "human_description": norm_action.get("human_description", ""),
                    "code": raw_code,
                    "action": "custom",
                    "page_name": "MainPage",
                    "value": norm_action.get("value", ""),
                    "selector_info": norm_action.get("selector_info", {})
                })
                continue

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
            sel = norm_action.get("selector_info") or {}
            var_name = sel.get("var_name", "element")
            locator_expr = sel.get("locator_expr", "self.page.locator('body')")
            val = norm_action.get("value", "")

            non_locator_actions = ["navigate", "wait", "take_screenshot", "assert_title", "assert_url", "api_request"]
            if var_name not in page_data["locators"] and act_type not in non_locator_actions:
                page_data["locators"][var_name] = {
                    "var_name": var_name,
                    "playwright_code": locator_expr
                }

            step_code, method_info = self._synthesize_step_and_method(
                current_page_name, act_type, var_name, val, norm_action
            )

            if method_info:
                method_name = method_info["name"]
                if method_name not in page_data["methods"]:
                    page_data["methods"][method_name] = method_info

            processed_steps.append({
                "human_description": norm_action.get("human_description", ""),
                "code": step_code if step_code and step_code != "pass" else raw_code,
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

        elif act_type == "wait":
            ms_val = int(val) if str(val).isdigit() else 1000
            return f'page.wait_for_timeout({ms_val})', None

        elif act_type == "take_screenshot":
            path_val = val or "evidence_screenshot.png"
            return f'page.screenshot(path="{path_val}")', None

        elif act_type == "assert_title":
            return f'expect(page).to_have_title("{val}")', None

        elif act_type == "assert_url":
            return f'expect(page).to_have_url("{val}")', None

        elif act_type == "api_request":
            return f'page.request.get("{val}")', None

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
            step_code = f'{page_var}.{method_name}("{val}")'
            return step_code, method

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

    def reconstruct_scenario(self, scenario: Dict[str, Any]) -> Dict[str, Any]:
        return self.synthesize_pom_and_test(
            scenario_name=scenario.get("name", "Scenario"),
            tags=scenario.get("tags", []),
            actions=scenario.get("steps", [])
        )

    @classmethod
    def normalize_step(cls, step_data: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(step_data or {})
        desc = str(data.get("human_description") or "")
        code = str(data.get("code") or "")
        raw_act = str(data.get("action") or "").lower().strip()
        val = data.get("value")
        sel = data.get("selector_info")

        valid_acts = [
            "click", "fill", "navigate", "press", "wait", "take_screenshot",
            "assert_visible", "assert_text", "assert_value", "assert_title", "assert_url", "api_request"
        ]

        combined = f"{code} {desc}".lower()
        if raw_act == "click" or raw_act not in valid_acts or raw_act == "custom":
            if "fill" in combined or "type '" in combined or "into '" in combined or "column" in combined or ".fill" in combined or "select " in combined:
                act = "fill"
            elif "to_have_title" in combined or "page title" in combined:
                act = "assert_title"
            elif "to_have_url" in combined or "page url" in combined:
                act = "assert_url"
            elif ("assert" in combined or "expect" in combined) and any(k in combined for k in ["counter", "equals", "value", "count"]):
                act = "assert_value"
            elif ("assert" in combined or "expect" in combined) and any(k in combined for k in ["text", "contains", "toast", "message"]):
                act = "assert_text"
            elif ("assert" in combined or "expect" in combined):
                act = "assert_visible"
            elif "goto" in combined or "navigate" in combined:
                act = "navigate"
            elif "press" in combined:
                act = "press"
            elif "wait" in combined:
                act = "wait"
            elif "screenshot" in combined:
                act = "take_screenshot"
            elif "request" in combined or "api" in combined:
                act = "api_request"
            elif "click" in combined:
                act = "click"
            else:
                act = raw_act or "click"
        else:
            act = raw_act

        if val is None or str(val) == "":
            extracted_val = ""
            if act == "fill":
                m = re.search(r"Type '([^']*)'", desc)
                if not m:
                    m = re.search(r"with '([^']*)'", desc)
                if m:
                    extracted_val = m.group(1)
                else:
                    m2 = re.search(r'\.(?:fill|fill_[a-zA-Z0-9_]+)\(["\']([^"\']*)["\']', code)
                    if m2:
                        extracted_val = m2.group(1)
            elif act == "navigate":
                m = re.search(r'Navigate to ([^\s]+)', desc)
                if m:
                    extracted_val = m.group(1)
                else:
                    m2 = re.search(r'\.goto\(["\']([^"\']*)["\']', code)
                    if m2:
                        extracted_val = m2.group(1)
            elif act == "press":
                m = re.search(r"Press key '([^']*)'", desc)
                if m:
                    extracted_val = m.group(1)
                else:
                    m2 = re.search(r'\.press\(["\']([^"\']*)["\']', code)
                    if m2:
                        extracted_val = m2.group(1)
            elif act == "wait":
                m = re.search(r'Wait for (\d+)', desc)
                if m:
                    extracted_val = m.group(1)
                else:
                    m2 = re.search(r'wait_for_timeout\((\d+)\)', code)
                    if m2:
                        extracted_val = m2.group(1)
            elif act in ["assert_title", "assert_url", "assert_text", "assert_value"]:
                m = re.search(r"'([^']*)'", desc)
                if m:
                    extracted_val = m.group(1)
                else:
                    m2 = re.search(r'\((?:["\']([^"\']*)["\'])', code)
                    if m2:
                        extracted_val = m2.group(1)
            val = extracted_val
        val = str(val) if val is not None else ""

        if not isinstance(sel, dict) or not sel.get("var_name"):
            display_val = ""
            var_name = ""
            if act == "fill":
                m = re.search(r"into '([^']*)'", desc)
                if not m:
                    m = re.search(r"Fill '([^']*)'", desc)
                if m:
                    display_val = m.group(1)
                else:
                    m2 = re.search(r'\.fill_([a-zA-Z0-9_]+)\(', code)
                    if m2:
                        var_name = m2.group(1)
                        display_val = var_name.replace("_", " ")
            elif act == "click":
                m = re.search(r"Click '([^']*)'", desc)
                if m:
                    display_val = m.group(1)
                else:
                    m2 = re.search(r'\.click_([a-zA-Z0-9_]+)\(', code)
                    if m2:
                        var_name = m2.group(1)
                        display_val = var_name.replace("_", " ")
            elif act == "press":
                m = re.search(r"on '([^']*)'", desc)
                if m:
                    display_val = m.group(1)
                else:
                    m2 = re.search(r'\.press_([a-zA-Z0-9_]+)\(', code)
                    if m2:
                        var_name = m2.group(1)
                        display_val = var_name.replace("_", " ")
            elif "assert" in act:
                m = re.search(r"'([^']*)'", desc)
                if not m:
                    m = re.search(r"Assert ([a-zA-Z0-9_ ]+) visible", desc)
                if m:
                    display_val = m.group(1)
                else:
                    m2 = re.search(r'\.assert_([a-zA-Z0-9_]+)_', code)
                    if m2:
                        var_name = m2.group(1)
                        display_val = var_name.replace("_", " ")

            if not var_name and display_val:
                var_name = SelectorEngine.clean_identifier(display_val)
            if not display_val and var_name:
                display_val = var_name.replace("_", " ")

            if display_val or var_name:
                sel = SelectorEngine.create_custom_selector("css", display_val or var_name, var_name)
            else:
                sel = sel if isinstance(sel, dict) else {}

        data["action"] = act
        data["value"] = val
        data["selector_info"] = sel
        data["human_description"] = desc
        data["code"] = code
        return data

    @classmethod
    def _call_to_step_dict(cls, call_node: ast.Call, raw_call: str) -> Dict[str, Any]:
        if "page.goto" in raw_call:
            arg = call_node.args[0].value if call_node.args and hasattr(call_node.args[0], 'value') else "URL"
            return {
                "human_description": f"Navigate to {arg}",
                "code": raw_call,
                "action": "navigate",
                "value": str(arg),
                "selector_info": {}
            }
        if "wait_for_timeout" in raw_call:
            arg = call_node.args[0].value if call_node.args and hasattr(call_node.args[0], 'value') else "1000"
            return {
                "human_description": f"Wait for {arg}ms",
                "code": raw_call,
                "action": "wait",
                "value": str(arg),
                "selector_info": {}
            }
        if "screenshot" in raw_call:
            arg = ""
            if call_node.args and hasattr(call_node.args[0], 'value'):
                arg = str(call_node.args[0].value)
            for kw in getattr(call_node, 'keywords', []):
                if kw.arg == "path" and hasattr(kw.value, 'value'):
                    arg = str(kw.value.value)
            return {
                "human_description": f"Take screenshot: {raw_call}",
                "code": raw_call,
                "action": "take_screenshot",
                "value": arg or "evidence_screenshot.png",
                "selector_info": {}
            }
        if "to_have_title" in raw_call:
            arg = call_node.args[0].value if call_node.args and hasattr(call_node.args[0], 'value') else ""
            return {
                "human_description": f"Assert page title equals '{arg}'",
                "code": raw_call,
                "action": "assert_title",
                "value": str(arg),
                "selector_info": {}
            }
        if "to_have_url" in raw_call:
            arg = call_node.args[0].value if call_node.args and hasattr(call_node.args[0], 'value') else ""
            return {
                "human_description": f"Assert page URL matches '{arg}'",
                "code": raw_call,
                "action": "assert_url",
                "value": str(arg),
                "selector_info": {}
            }
        if "page.request" in raw_call:
            arg = call_node.args[0].value if call_node.args and hasattr(call_node.args[0], 'value') else ""
            return {
                "human_description": f"API Request: {raw_call}",
                "code": raw_call,
                "action": "api_request",
                "value": str(arg),
                "selector_info": {}
            }
        if "click" in raw_call:
            func_name = getattr(call_node.func, "attr", "")
            target_raw = func_name.replace("click_", "").replace("_", " ") if func_name.startswith("click_") else "element"
            var_name = func_name.replace("click_", "") if func_name.startswith("click_") else "element"
            sel_info = SelectorEngine.create_custom_selector("css", target_raw or var_name, var_name)
            return {
                "human_description": f"Click '{target_raw}' button" if target_raw else "Click element",
                "code": raw_call,
                "action": "click",
                "value": "",
                "selector_info": sel_info
            }
        if "fill" in raw_call:
            func_name = getattr(call_node.func, "attr", "")
            target_raw = func_name.replace("fill_", "").replace("_", " ") if func_name.startswith("fill_") else "element"
            var_name = func_name.replace("fill_", "") if func_name.startswith("fill_") else "element"
            val = call_node.args[0].value if call_node.args and hasattr(call_node.args[0], 'value') else ""
            sel_info = SelectorEngine.create_custom_selector("css", target_raw or var_name, var_name)
            return {
                "human_description": f"Type '{val}' into '{target_raw}'",
                "code": raw_call,
                "action": "fill",
                "value": str(val),
                "selector_info": sel_info
            }
        if "press" in raw_call:
            func_name = getattr(call_node.func, "attr", "")
            target_raw = func_name.replace("press_", "").replace("_", " ") if func_name.startswith("press_") else "element"
            var_name = func_name.replace("press_", "") if func_name.startswith("press_") else "element"
            val = call_node.args[0].value if call_node.args and hasattr(call_node.args[0], 'value') else "Enter"
            sel_info = SelectorEngine.create_custom_selector("css", target_raw or var_name, var_name)
            return {
                "human_description": f"Press key '{val}' on '{target_raw}'" if target_raw else f"Press key '{val}'",
                "code": raw_call,
                "action": "press",
                "value": str(val),
                "selector_info": sel_info
            }
        if "assert" in raw_call or "expect" in raw_call:
            func_name = getattr(call_node.func, "attr", "")
            if "visible" in raw_call:
                target_raw = func_name.replace("assert_", "").replace("_visible", "").replace("_", " ")
                var_name = SelectorEngine.clean_identifier(target_raw)
                sel_info = SelectorEngine.create_custom_selector("css", target_raw or var_name, var_name)
                return {
                    "human_description": f"Assert '{target_raw}' is visible",
                    "code": raw_call,
                    "action": "assert_visible",
                    "value": "",
                    "selector_info": sel_info
                }
            elif "text" in raw_call:
                target_raw = func_name.replace("assert_", "").replace("_contains_text", "").replace("_", " ")
                var_name = SelectorEngine.clean_identifier(target_raw)
                val = call_node.args[0].value if call_node.args and hasattr(call_node.args[0], 'value') else ""
                sel_info = SelectorEngine.create_custom_selector("css", target_raw or var_name, var_name)
                return {
                    "human_description": f"Assert '{target_raw}' contains text '{val}'",
                    "code": raw_call,
                    "action": "assert_text",
                    "value": str(val),
                    "selector_info": sel_info
                }
            elif "value" in raw_call:
                target_raw = func_name.replace("assert_", "").replace("_has_value", "").replace("_", " ")
                var_name = SelectorEngine.clean_identifier(target_raw)
                val = call_node.args[0].value if call_node.args and hasattr(call_node.args[0], 'value') else ""
                sel_info = SelectorEngine.create_custom_selector("css", target_raw or var_name, var_name)
                return {
                    "human_description": f"Assert '{target_raw}' has value '{val}'",
                    "code": raw_call,
                    "action": "assert_value",
                    "value": str(val),
                    "selector_info": sel_info
                }
            else:
                return {
                    "human_description": f"Assert verification: {raw_call}",
                    "code": raw_call,
                    "action": "assert_visible",
                    "value": "",
                    "selector_info": {}
                }
        return {
            "human_description": f"Execute: {raw_call}",
            "code": raw_call,
            "action": "custom",
            "value": "",
            "selector_info": {}
        }

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
                        step_dict = cls._call_to_step_dict(call, call_repr)
                        result["steps"].append(step_dict)

        return result

    @classmethod
    def _call_to_human_step(cls, call_node: ast.Call, raw_call: str) -> str:
        return cls._call_to_step_dict(call_node, raw_call).get("human_description", f"Execute: {raw_call}")
