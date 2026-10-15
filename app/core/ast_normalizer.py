import ast
import re
from urllib.parse import urlparse
from typing import List, Dict, Any, Tuple, Optional
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
            netloc = parsed.netloc.lower()
            if netloc.startswith("www."):
                netloc = netloc[4:]
            parts = [p for p in netloc.split(".") if p and p not in ("com", "org", "net", "io", "dev", "co", "in", "app", "gov", "edu")]
            domain_part = parts[0].capitalize() if parts else ""
            path = parsed.path.strip("/")
            if not path or path == "":
                return f"{domain_part}HomePage" if domain_part else default
            segments = [s for s in path.split("/") if s and not s.isdigit()]
            if not segments:
                return f"{domain_part}HomePage" if domain_part else default
            name = segments[-1].replace("-", " ").replace("_", " ").title().replace(" ", "")
            return f"{name}Page" if name else (f"{domain_part}HomePage" if domain_part else default)
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
        for act in actions:
            if act.get("page_name"):
                current_page_name = act.get("page_name")
                break

        for action in actions:
            norm_action = self.normalize_step(action)
            act_type = norm_action.get("action")
            raw_code = norm_action.get("code")
            if act_type == "custom" and raw_code:
                processed_steps.append({
                    "human_description": norm_action.get("human_description", ""),
                    "code": raw_code,
                    "action": "custom",
                    "page_name": current_page_name,
                    "value": norm_action.get("value", ""),
                    "selector_info": norm_action.get("selector_info", {})
                })
                continue

            url = action.get("url") or current_url
            if url:
                current_url = url
                current_page_name = action.get("page_name") or self.infer_page_name(url)
            elif action.get("page_name"):
                current_page_name = action.get("page_name")

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
            locator_expr = sel.get("locator_expr", "")
            if not locator_expr or locator_expr == "self.page.locator('body')":
                display_q = sel.get("display") or var_name
                strat = sel.get("strategy", "css")
                loc_cand = SelectorEngine.create_custom_selector(strat, display_q, var_name)
                locator_expr = loc_cand.get("locator_expr", "self.page.locator('body')")
            elif "role='role=" in locator_expr or 'get_by_role("role=' in locator_expr or "get_by_role('role=" in locator_expr or ("role='" in locator_expr and "name=" in locator_expr and 'get_by_role("' in locator_expr and ', name=' not in locator_expr):
                m_fix = re.search(r"role=['\"]([a-zA-Z0-9_-]+)['\"](?:,\s*name=['\"]([^'\"]*)['\"])?", locator_expr)
                if m_fix:
                    r_type = m_fix.group(1)
                    r_name = m_fix.group(2)
                    if r_name:
                        locator_expr = f'self.page.get_by_role("{r_type}", name="{r_name}")'
                    else:
                        locator_expr = f'self.page.get_by_role("{r_type}")'

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

            step_dict = {
                "human_description": norm_action.get("human_description", ""),
                "code": step_code if step_code and step_code != "pass" else raw_code,
                "action": act_type,
                "page_name": current_page_name,
                "value": val,
                "selector_info": sel,
                "url": url
            }
            if norm_action.get("variable_name"):
                step_dict["variable_name"] = norm_action["variable_name"]
            processed_steps.append(step_dict)

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

        has_variables = any(
            ("vars.get(" in (s.get("code") or "")) or bool(s.get("variable_name"))
            for s in processed_steps
        )

        safe_tags = []
        raw_tags = tags if isinstance(tags, (list, tuple)) else [tags]
        for t in raw_tags:
            t_str = str(t).strip().lstrip("@")
            if t_str and re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', t_str):
                safe_tags.append(t_str)

        test_code = test_template.render(
            scenario_name=scenario_name,
            scenario_description=scenario_description or f"Test scenario for {scenario_name}",
            tags=safe_tags,
            test_func_name=test_func_name,
            pom_imports=pom_imports,
            pom_instantiations=pom_instantiations,
            steps=processed_steps,
            has_variables=has_variables
        )
        ast.parse(test_code)

        return {
            "test_code": test_code,
            "test_func_name": test_func_name,
            "file_name": f"{test_func_name}.py",
            "pages": generated_pages,
            "steps": processed_steps
        }

    @classmethod
    def _get_variable_info(cls, action: Dict[str, Any], val: Any) -> Tuple[Optional[str], str]:
        var_key = action.get("variable_name")
        val_str = str(val) if val is not None else ""
        if not var_key:
            m = re.match(r'^\{\{\s*([a-zA-Z0-9_]+)\s*\}\}$', val_str)
            if m:
                var_key = m.group(1)
            elif val_str.startswith("$") and len(val_str) > 1 and not val_str.startswith("$$"):
                var_key = val_str[1:].strip()
        fallback = action.get("fallback_value") or action.get("default_value") or ""
        if not fallback and not val_str.startswith("{{") and not val_str.startswith("$") and val_str != var_key:
            fallback = val_str
        if not fallback:
            m_fb = re.search(r"with '([^']*)'", str(action.get("human_description") or ""))
            if m_fb:
                fallback = m_fb.group(1)
        return (var_key, fallback)

    def _synthesize_step_and_method(
        self, page_class: str, act_type: str, var_name: str, val: str, action: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        page_var = self._to_snake(page_class)
        var_key, fallback_val = self._get_variable_info(action, val)

        if act_type == "navigate":
            if var_key:
                return f'page.goto(vars.get("{var_key}", "{fallback_val}"))', None
            return f'page.goto("{val}")', None

        elif act_type == "wait":
            ms_val = int(val) if str(val).isdigit() else 1000
            return f'page.wait_for_timeout({ms_val})', None

        elif act_type == "take_screenshot":
            path_val = val or "evidence_screenshot.png"
            return f'page.screenshot(path="{path_val}")', None

        elif act_type == "assert_title":
            if var_key:
                return f'expect(page).to_have_title(vars.get("{var_key}", "{fallback_val}"))', None
            return f'expect(page).to_have_title("{val}")', None

        elif act_type == "assert_url":
            if var_key:
                return f'expect(page).to_have_url(vars.get("{var_key}", "{fallback_val}"))', None
            return f'expect(page).to_have_url("{val}")', None

        elif act_type == "api_request":
            if var_key:
                return f'page.request.get(vars.get("{var_key}", "{fallback_val}"))', None
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
            if var_key:
                step_code = f'{page_var}.{method_name}(vars.get("{var_key}", "{fallback_val}"))'
            else:
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
            if var_key:
                step_code = f'{page_var}.{method_name}(vars.get("{var_key}", "{fallback_val}"))'
            else:
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
            if var_key:
                step_code = f'{page_var}.{method_name}(vars.get("{var_key}", "{fallback_val}"))'
            else:
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
            if var_key:
                step_code = f'{page_var}.{method_name}(vars.get("{var_key}", "{fallback_val}"))'
            else:
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
    def patch_scenario_code_with_steps(cls, py_code: str, step_list: List[Dict[str, Any]]) -> str:
        if not py_code or not py_code.strip():
            return py_code
        has_vars = any(
            bool(s.get("variable_name")) or ("vars.get(" in (s.get("code") or ""))
            for s in step_list
        )
        lines = py_code.splitlines()
        fn_def_idx = -1
        for i, line in enumerate(lines):
            if re.match(r'^\s*def\s+test_[a-zA-Z0-9_]*\(', line):
                fn_def_idx = i
                if has_vars:
                    if "test_data" not in line:
                        lines[i] = re.sub(
                            r'\(([^)]*)\):',
                            lambda m: f"({m.group(1).rstrip()}, test_data):" if m.group(1).strip() else "(page: Page, test_data):",
                            line
                        )
                break

        if has_vars and fn_def_idx != -1:
            vars_stmts = [
                '    vars = test_data.get("variables", {}) if isinstance(test_data, dict) else {}',
                '    if not isinstance(vars, SmartVarDict):',
                '        vars = SmartVarDict(vars)'
            ]
            has_vars_stmt = any("vars = test_data.get(" in l for l in lines)
            if not has_vars_stmt:
                for offset, vs in enumerate(vars_stmts):
                    lines.insert(fn_def_idx + 1 + offset, vs)
            elif not any("isinstance(vars, SmartVarDict)" in l for l in lines):
                for i_l, l in enumerate(lines):
                    if "vars = test_data.get(" in l:
                        lines.insert(i_l + 1, '    if not isinstance(vars, SmartVarDict):\n        vars = SmartVarDict(vars)')
                        break

            if not any("class SmartVarDict" in l for l in lines):
                smart_var_lines = [
                    "class SmartVarDict(dict):",
                    "    def get(self, key, default=''):",
                    "        val = super().get(key)",
                    "        if val is not None and str(val) != '':",
                    "            return val",
                    "        kl = str(key).lower()",
                    "        for k, v in self.items():",
                    "            if str(k).lower() == kl and v is not None and str(v) != '':",
                    "                return v",
                    "        import os",
                    "        for env_k in (f'CONDUIT_VAR_{key}', key, str(key).upper(), str(key).lower()):",
                    "            if env_k in os.environ and os.environ[env_k] != '':",
                    "                return os.environ[env_k]",
                    "        return default",
                    ""
                ]
                for offset, fl in enumerate(smart_var_lines):
                    lines.insert(offset, fl)
                fn_def_idx += len(smart_var_lines)

            if not any("def test_data" in l for l in lines):
                insert_idx = fn_def_idx
                while insert_idx > 0 and lines[insert_idx - 1].strip().startswith("@"):
                    insert_idx -= 1
                fixture_lines = [
                    "@pytest.fixture",
                    "def test_data():",
                    "    import os, json",
                    "    workspace = os.environ.get('CONDUIT_WORKSPACE', os.getcwd())",
                    "    env = os.environ.get('CONDUIT_ENV', 'QA')",
                    "    candidates = [",
                    "        os.path.join(workspace, 'test_data', f'{env}.json'),",
                    "        os.path.join(workspace, f'{env}.json'),",
                    "        os.path.join(os.getcwd(), 'test_data', f'{env}.json')",
                    "    ]",
                    "    raw_data = None",
                    "    for p in candidates:",
                    "        if os.path.exists(p):",
                    "            try:",
                    "                with open(p, 'r', encoding='utf-8') as f:",
                    "                    raw_data = json.load(f)",
                    "                    break",
                    "            except Exception:",
                    "                pass",
                    "    if not raw_data:",
                    "        try:",
                    "            from app.core.test_data_manager import TestDataManager",
                    "            raw_data = TestDataManager(workspace).get_environment_data(env)",
                    "        except Exception:",
                    "            raw_data = {'environment': env, 'variables': {}}",
                    "    vars_dict = raw_data.get('variables', {}) if isinstance(raw_data, dict) else {}",
                    "    if isinstance(raw_data, dict):",
                    "        raw_data['variables'] = SmartVarDict(vars_dict)",
                    "    return raw_data",
                    ""
                ]
                for offset, fl in enumerate(fixture_lines):
                    lines.insert(insert_idx + offset, fl)

        for st in step_list:
            st_code = (st.get("code") or "").strip()
            if not st_code:
                continue
            st_act = st.get("action", "")
            sel = st.get("selector_info") or {}
            var_name = sel.get("var_name", "")

            replaced = False
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped == st_code:
                    replaced = True
                    break
                if var_name:
                    pattern = rf'^\s*([a-zA-Z0-9_]+\.)?(fill|click|press|assert)_[a-zA-Z0-9_]*{re.escape(var_name)}[a-zA-Z0-9_]*\('
                    if re.search(pattern, stripped):
                        indent = len(line) - len(stripped)
                        lines[i] = " " * indent + st_code
                        replaced = True
                        break
                if st_act == "navigate" and ("page.goto(" in stripped or "navigate(" in stripped):
                    indent = len(line) - len(stripped)
                    lines[i] = " " * indent + st_code
                    replaced = True
                    break

        result = "\n".join(lines)
        if py_code.endswith("\n"):
            result += "\n"
        try:
            ast.parse(result)
            return result
        except Exception:
            return py_code

    @classmethod
    def normalize_step(cls, step_data: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(step_data or {})
        desc = str(data.get("human_description") or "")
        code = str(data.get("code") or "")
        raw_act = str(data.get("action") or "").lower().strip()
        val = data.get("value")
        sel = data.get("selector_info")
        env_var = data.get("variable_name")

        if not env_var and val is not None:
            v_str = str(val).strip()
            if v_str.startswith("{{") and v_str.endswith("}}"):
                env_var = v_str[2:-2].strip()
            elif v_str.startswith("$") and len(v_str) > 1 and not v_str.startswith("$$"):
                env_var = v_str[1:].strip()

        if not env_var and code:
            m_code = re.search(r'vars\.get\(["\']([^"\']+)["\']', code)
            if m_code:
                env_var = m_code.group(1)
                if not val or val == "None":
                    val = f"{{{{{env_var}}}}}"

        if not env_var and desc:
            m_desc = re.search(r"variable ['\"]([^'\"]+)['\"]", desc)
            if m_desc:
                env_var = m_desc.group(1)
                if not val or val == "None":
                    val = f"{{{{{env_var}}}}}"

        if env_var:
            data["variable_name"] = env_var
            if val is None or str(val) == "":
                val = f"{{{{{env_var}}}}}"

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
            elem_var_name = ""
            if act == "fill":
                m = re.search(r"into '([^']*)'", desc)
                if not m:
                    m = re.search(r"Fill '([^']*)'", desc)
                if m:
                    display_val = m.group(1)
                else:
                    m2 = re.search(r'\.fill_([a-zA-Z0-9_]+)\(', code)
                    if m2:
                        elem_var_name = m2.group(1)
                        display_val = elem_var_name.replace("_", " ")
            elif act == "click":
                m = re.search(r"Click '([^']*)'", desc)
                if m:
                    display_val = m.group(1)
                else:
                    m2 = re.search(r'\.click_([a-zA-Z0-9_]+)\(', code)
                    if m2:
                        elem_var_name = m2.group(1)
                        display_val = elem_var_name.replace("_", " ")
            elif act == "press":
                m = re.search(r"on '([^']*)'", desc)
                if m:
                    display_val = m.group(1)
                else:
                    m2 = re.search(r'\.press_([a-zA-Z0-9_]+)\(', code)
                    if m2:
                        elem_var_name = m2.group(1)
                        display_val = elem_var_name.replace("_", " ")
            elif "assert" in act:
                m = re.search(r"'([^']*)'", desc)
                if not m:
                    m = re.search(r"Assert ([a-zA-Z0-9_ ]+) visible", desc)
                if m:
                    display_val = m.group(1)
                else:
                    m2 = re.search(r'\.assert_([a-zA-Z0-9_]+)_', code)
                    if m2:
                        elem_var_name = m2.group(1)
                        display_val = elem_var_name.replace("_", " ")

            if not elem_var_name and display_val:
                elem_var_name = SelectorEngine.clean_identifier(display_val)
            if not display_val and elem_var_name:
                display_val = elem_var_name.replace("_", " ")

            if display_val or elem_var_name:
                sel = SelectorEngine.create_custom_selector("css", display_val or elem_var_name, elem_var_name)
            else:
                sel = sel if isinstance(sel, dict) else {}

        if isinstance(sel, dict):
            loc_expr = sel.get("locator_expr", "")
            if "role='role=" in loc_expr or 'get_by_role("role=' in loc_expr or "get_by_role('role=" in loc_expr or ("role='" in loc_expr and "name=" in loc_expr and 'get_by_role("' in loc_expr and ', name=' not in loc_expr):
                m_fix = re.search(r"role=['\"]([a-zA-Z0-9_-]+)['\"](?:,\s*name=['\"]([^'\"]*)['\"])?", loc_expr)
                if m_fix:
                    r_type = m_fix.group(1)
                    r_name = m_fix.group(2)
                    if r_name:
                        sel["strategy"] = "role"
                        sel["locator_expr"] = f'self.page.get_by_role("{r_type}", name="{r_name}")'
                        sel["code"] = f'page.get_by_role("{r_type}", name="{r_name}")'
                        sel["display"] = f"role='{r_type}', name='{r_name}'"
                    else:
                        sel["strategy"] = "role"
                        sel["locator_expr"] = f'self.page.get_by_role("{r_type}")'
                        sel["code"] = f'page.get_by_role("{r_type}")'
                        sel["display"] = f"role='{r_type}'"

        data["action"] = act
        data["value"] = val
        data["selector_info"] = sel
        data["human_description"] = desc
        data["code"] = code
        if env_var:
            data["variable_name"] = env_var
        return data

    @classmethod
    def _extract_arg_and_variable(cls, node: ast.AST) -> Tuple[str, Optional[str]]:
        if node is None:
            return ("", None)
        if isinstance(node, ast.Constant):
            return (str(node.value), None)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "get":
                var_key = None
                fallback = ""
                if node.args and isinstance(node.args[0], ast.Constant):
                    var_key = str(node.args[0].value)
                if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                    fallback = str(node.args[1].value)
                if var_key:
                    return (f"{{{{{var_key}}}}}", var_key)
            try:
                return (ast.unparse(node), None)
            except Exception:
                return ("", None)
        if isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Constant):
                var_key = str(node.slice.value)
                return (f"{{{{{var_key}}}}}", var_key)
        if isinstance(node, ast.Name):
            return (node.id, None)
        try:
            return (ast.unparse(node), None)
        except Exception:
            return ("", None)

    @classmethod
    def _call_to_step_dict(cls, call_node: ast.Call, raw_call: str) -> Dict[str, Any]:
        if "page.goto" in raw_call:
            arg_node = call_node.args[0] if call_node.args else None
            val, var_name = cls._extract_arg_and_variable(arg_node)
            desc = f"Navigate to variable '{var_name}'" if var_name else f"Navigate to {val or 'URL'}"
            res = {
                "human_description": desc,
                "code": raw_call,
                "action": "navigate",
                "value": val or "URL",
                "selector_info": {}
            }
            if var_name:
                res["variable_name"] = var_name
            return res
        if "wait_for_timeout" in raw_call:
            arg_node = call_node.args[0] if call_node.args else None
            val, var_name = cls._extract_arg_and_variable(arg_node)
            res = {
                "human_description": f"Wait for {val or '1000'}ms",
                "code": raw_call,
                "action": "wait",
                "value": str(val or "1000"),
                "selector_info": {}
            }
            if var_name:
                res["variable_name"] = var_name
            return res
        if "screenshot" in raw_call:
            arg_node = call_node.args[0] if call_node.args else None
            val, var_name = cls._extract_arg_and_variable(arg_node)
            for kw in getattr(call_node, 'keywords', []):
                if kw.arg == "path":
                    val, var_name = cls._extract_arg_and_variable(kw.value)
            res = {
                "human_description": f"Take screenshot: {raw_call}",
                "code": raw_call,
                "action": "take_screenshot",
                "value": val or "evidence_screenshot.png",
                "selector_info": {}
            }
            if var_name:
                res["variable_name"] = var_name
            return res
        if "to_have_title" in raw_call:
            arg_node = call_node.args[0] if call_node.args else None
            val, var_name = cls._extract_arg_and_variable(arg_node)
            desc = f"Assert page title equals variable '{var_name}'" if var_name else f"Assert page title equals '{val}'"
            res = {
                "human_description": desc,
                "code": raw_call,
                "action": "assert_title",
                "value": str(val),
                "selector_info": {}
            }
            if var_name:
                res["variable_name"] = var_name
            return res
        if "to_have_url" in raw_call:
            arg_node = call_node.args[0] if call_node.args else None
            val, var_name = cls._extract_arg_and_variable(arg_node)
            desc = f"Assert page URL matches variable '{var_name}'" if var_name else f"Assert page URL matches '{val}'"
            res = {
                "human_description": desc,
                "code": raw_call,
                "action": "assert_url",
                "value": str(val),
                "selector_info": {}
            }
            if var_name:
                res["variable_name"] = var_name
            return res
        if "page.request" in raw_call:
            arg_node = call_node.args[0] if call_node.args else None
            val, var_name = cls._extract_arg_and_variable(arg_node)
            res = {
                "human_description": f"API Request: {raw_call}",
                "code": raw_call,
                "action": "api_request",
                "value": str(val),
                "selector_info": {}
            }
            if var_name:
                res["variable_name"] = var_name
            return res
        if "click" in raw_call:
            func_name = getattr(call_node.func, "attr", "")
            target_raw = func_name.replace("click_", "").replace("_", " ") if func_name.startswith("click_") else "element"
            elem_var_name = func_name.replace("click_", "") if func_name.startswith("click_") else "element"
            sel_info = SelectorEngine.create_custom_selector("css", target_raw or elem_var_name, elem_var_name)
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
            elem_var_name = func_name.replace("fill_", "") if func_name.startswith("fill_") else "element"
            arg_node = call_node.args[0] if call_node.args else None
            val, var_name = cls._extract_arg_and_variable(arg_node)
            sel_info = SelectorEngine.create_custom_selector("css", target_raw or elem_var_name, elem_var_name)
            desc = f"Fill '{target_raw}' with variable '{var_name}'" if var_name else f"Type '{val}' into '{target_raw}'"
            res = {
                "human_description": desc,
                "code": raw_call,
                "action": "fill",
                "value": str(val),
                "selector_info": sel_info
            }
            if var_name:
                res["variable_name"] = var_name
            return res
        if "press" in raw_call:
            func_name = getattr(call_node.func, "attr", "")
            target_raw = func_name.replace("press_", "").replace("_", " ") if func_name.startswith("press_") else "element"
            elem_var_name = func_name.replace("press_", "") if func_name.startswith("press_") else "element"
            arg_node = call_node.args[0] if call_node.args else None
            val, var_name = cls._extract_arg_and_variable(arg_node)
            sel_info = SelectorEngine.create_custom_selector("css", target_raw or elem_var_name, elem_var_name)
            res = {
                "human_description": f"Press key '{val or 'Enter'}' on '{target_raw}'" if target_raw else f"Press key '{val or 'Enter'}'",
                "code": raw_call,
                "action": "press",
                "value": str(val or "Enter"),
                "selector_info": sel_info
            }
            if var_name:
                res["variable_name"] = var_name
            return res
        if "assert" in raw_call or "expect" in raw_call:
            func_name = getattr(call_node.func, "attr", "")
            if "visible" in raw_call:
                target_raw = func_name.replace("assert_", "").replace("_visible", "").replace("_", " ")
                elem_var_name = SelectorEngine.clean_identifier(target_raw)
                sel_info = SelectorEngine.create_custom_selector("css", target_raw or elem_var_name, elem_var_name)
                return {
                    "human_description": f"Assert '{target_raw}' is visible",
                    "code": raw_call,
                    "action": "assert_visible",
                    "value": "",
                    "selector_info": sel_info
                }
            elif "text" in raw_call:
                target_raw = func_name.replace("assert_", "").replace("_contains_text", "").replace("_", " ")
                elem_var_name = SelectorEngine.clean_identifier(target_raw)
                arg_node = call_node.args[0] if call_node.args else None
                val, var_name = cls._extract_arg_and_variable(arg_node)
                sel_info = SelectorEngine.create_custom_selector("css", target_raw or elem_var_name, elem_var_name)
                desc = f"Assert '{target_raw}' contains variable '{var_name}'" if var_name else f"Assert '{target_raw}' contains text '{val}'"
                res = {
                    "human_description": desc,
                    "code": raw_call,
                    "action": "assert_text",
                    "value": str(val),
                    "selector_info": sel_info
                }
                if var_name:
                    res["variable_name"] = var_name
                return res
            elif "value" in raw_call:
                target_raw = func_name.replace("assert_", "").replace("_has_value", "").replace("_", " ")
                elem_var_name = SelectorEngine.clean_identifier(target_raw)
                arg_node = call_node.args[0] if call_node.args else None
                val, var_name = cls._extract_arg_and_variable(arg_node)
                sel_info = SelectorEngine.create_custom_selector("css", target_raw or elem_var_name, elem_var_name)
                desc = f"Assert '{target_raw}' equals variable '{var_name}'" if var_name else f"Assert '{target_raw}' has value '{val}'"
                res = {
                    "human_description": desc,
                    "code": raw_call,
                    "action": "assert_value",
                    "value": str(val),
                    "selector_info": sel_info
                }
                if var_name:
                    res["variable_name"] = var_name
                return res
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
