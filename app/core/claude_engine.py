import os
import json
import re
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from app.core.selector_engine import SelectorEngine


class ClaudeEngine:
    API_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"
    DEFAULT_MODEL = "claude-3-5-sonnet-20241022"

    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model or os.environ.get("CONDUIT_CLAUDE_MODEL", self.DEFAULT_MODEL)

    def set_api_key(self, api_key: str):
        self.api_key = api_key.strip()

    def set_model(self, model: str):
        if model.strip():
            self.model = model.strip()

    def is_api_available(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 10)

    def test_connection(self):
        if not self.is_api_available():
            return False, "Anthropic API key is not configured. Running in Heuristic AI mode."
        try:
            res = self.send_message(
                system_prompt="You are a health check assistant. Respond with 'PONG' only.",
                user_prompt="PING",
                max_tokens=10
            )
            return True, f"Connected to Anthropic API ({self.model})"
        except Exception as e:
            return False, str(e)

    def send_message(self, system_prompt: str, user_prompt: str, max_tokens: int = 2048) -> str:
        if not self.is_api_available():
            raise ValueError("Anthropic API key is not configured.")

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "user", "content": user_prompt}
            ]
        }
        if system_prompt:
            payload["system"] = system_prompt

        data = json.dumps(payload).encode("utf-8")
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json"
        }

        req = urllib.request.Request(self.API_URL, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                content_blocks = res_json.get("content", [])
                text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
                return "".join(text_parts).strip()
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8")
            raise RuntimeError(f"Claude API HTTP Error {e.code}: {err_msg}")
        except Exception as e:
            raise RuntimeError(f"Claude API Request Failed: {str(e)}")

    def generate_flow_from_prompt(self, prompt: str, base_url: str = "") -> Dict[str, Any]:
        if not self.is_api_available():
            return self._fallback_generate_flow(prompt, base_url)

        system_prompt = (
            "You are an expert test automation architect in Conduit. "
            "Convert user natural language test scenario requirements into a structured JSON test flow. "
            "Return strictly valid JSON with this exact schema:\n"
            "{\n"
            '  "scenario_name": "String",\n'
            '  "tags": ["@tag1", "@tag2"],\n'
            '  "steps": [\n'
            '    {\n'
            '      "action": "navigate|click|fill|press|assert_visible|assert_text|assert_value|assert_title|assert_url|wait",\n'
            '      "strategy": "css|text|id|testid|role|xpath",\n'
            '      "selector": "selector string",\n'
            '      "var_name": "element_var_name",\n'
            '      "value": "parameter or text value",\n'
            '      "human_description": "Clear step description"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Do not include any markdown fences or explanatory text, only the raw JSON."
        )

        user_prompt = f"Create an automated test scenario for the following requirement:\n{prompt}\n"
        if base_url:
            user_prompt += f"Base URL context: {base_url}\n"

        try:
            raw_res = self.send_message(system_prompt, user_prompt)
            json_text = self._extract_json(raw_res)
            parsed = json.loads(json_text)
            return self._format_generated_flow(parsed, base_url)
        except Exception:
            return self._fallback_generate_flow(prompt, base_url)

    def diagnose_and_heal_failure(
        self, scenario_name: str, failed_step: Dict[str, Any], error_message: str, page_snippet: str = ""
    ) -> Dict[str, Any]:
        if not self.is_api_available():
            return self._fallback_diagnose_failure(scenario_name, failed_step, error_message)

        system_prompt = (
            "You are an autonomous AI self-healing test automation engineer in Conduit. "
            "Analyze the failure cause and provide a healed selector and step configuration. "
            "Return strictly valid JSON with this exact schema:\n"
            "{\n"
            '  "root_cause": "Detailed explanation of why the locator or assertion failed",\n'
            '  "healing_strategy": "Explanation of how to make the selector resilient",\n'
            '  "healed_step": {\n'
            '    "action": "action name",\n'
            '    "strategy": "css|text|id|testid|role|xpath",\n'
            '    "selector": "resilient selector string",\n'
            '    "var_name": "element_var_name",\n'
            '    "value": "step value",\n'
            '    "human_description": "Healed step description"\n'
            "  },\n"
            '  "confidence": 0.95\n'
            "}\n"
            "Do not include any markdown fences or explanatory text, only raw JSON."
        )

        user_prompt = (
            f"Scenario: {scenario_name}\n"
            f"Failed Step: {json.dumps(failed_step)}\n"
            f"Error Message: {error_message}\n"
        )
        if page_snippet:
            user_prompt += f"DOM Snippet: {page_snippet[:1500]}\n"

        try:
            raw_res = self.send_message(system_prompt, user_prompt)
            json_text = self._extract_json(raw_res)
            return json.loads(json_text)
        except Exception:
            return self._fallback_diagnose_failure(scenario_name, failed_step, error_message)

    def optimize_and_explain_code(self, code: str) -> Dict[str, Any]:
        if not self.is_api_available():
            return self._fallback_optimize_code(code)

        system_prompt = (
            "You are an expert test automation auditor in Conduit. "
            "Analyze the Python Playwright test spec and page objects. "
            "Provide step-by-step explanation, performance & resiliency tips, and refactored code. "
            "Return strictly valid JSON with schema:\n"
            "{\n"
            '  "explanation": "Markdown text explaining the flow",\n'
            '  "suggestions": ["Suggestion 1", "Suggestion 2"],\n'
            '  "improved_code": "Optimized Python code"\n'
            "}\n"
            "Return raw JSON only."
        )

        try:
            raw_res = self.send_message(system_prompt, f"Analyze this test code:\n```python\n{code}\n```")
            json_text = self._extract_json(raw_res)
            return json.loads(json_text)
        except Exception:
            return self._fallback_optimize_code(code)

    def synthesize_test_data(self, description: str, count: int = 5) -> List[Dict[str, Any]]:
        if not self.is_api_available():
            return self._fallback_synthesize_data(description, count)

        system_prompt = (
            "You are a synthetic test data generation AI in Conduit. "
            "Generate realistic, production-like test dataset rows based on the requested domain or schema. "
            "Return strictly valid JSON as an array of objects where each object represents one row of test data:\n"
            '[{"field1": "val1", "field2": "val2"}, ...]\n'
            "Return raw JSON array only."
        )

        user_prompt = f"Generate {count} distinct test data records for:\n{description}"
        try:
            raw_res = self.send_message(system_prompt, user_prompt)
            json_text = self._extract_json(raw_res)
            parsed = json.loads(json_text)
            if isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, dict) and "data" in parsed:
                return parsed["data"]
            return self._fallback_synthesize_data(description, count)
        except Exception:
            return self._fallback_synthesize_data(description, count)

    def _extract_json(self, raw_text: str) -> str:
        text = raw_text.strip()
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if fence_match:
            return fence_match.group(1).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start:end + 1]
        start_arr = text.find("[")
        end_arr = text.rfind("]")
        if start_arr != -1 and end_arr != -1 and end_arr > start_arr:
            return text[start_arr:end_arr + 1]
        return text

    def _format_generated_flow(self, data: Dict[str, Any], base_url: str = "") -> Dict[str, Any]:
        scenario_name = data.get("scenario_name", "AI Generated Flow")
        tags = data.get("tags", ["@ai-generated", "@smoke"])
        raw_steps = data.get("steps", [])

        processed_steps = []
        for s in raw_steps:
            act = s.get("action", "click")
            val = str(s.get("value", ""))
            strat = s.get("strategy", "css")
            query = s.get("selector", "")
            var_name = s.get("var_name", "") or SelectorEngine.clean_identifier(query or act)
            sel_info = SelectorEngine.create_custom_selector(strat, query, var_name)
            desc = s.get("human_description", "") or SelectorEngine.generate_human_step(act, sel_info, val)

            processed_steps.append({
                "action": act,
                "value": val,
                "selector_info": sel_info,
                "human_description": desc
            })

        return {
            "scenario_name": scenario_name,
            "tags": tags,
            "steps": processed_steps
        }

    def _fallback_generate_flow(self, prompt: str, base_url: str = "") -> Dict[str, Any]:
        clean_title = re.sub(r"[^\w\s]", "", prompt).strip()
        words = clean_title.split()[:5]
        sc_name = " ".join(words).title() if words else "AI Generated Flow"

        url_target = base_url or "https://demo.playwright.dev/todomvc/"
        url_match = re.search(r"https?://[^\s]+", prompt)
        if url_match:
            url_target = url_match.group(0)

        steps = [
            {
                "action": "navigate",
                "value": url_target,
                "selector_info": {},
                "human_description": f"Navigate to {url_target}"
            }
        ]

        p_lower = prompt.lower()
        if "login" in p_lower or "sign in" in p_lower:
            steps.extend([
                {
                    "action": "fill",
                    "value": "{{username}}",
                    "selector_info": SelectorEngine.create_custom_selector("testid", "username-input", "username_field"),
                    "human_description": "Fill 'username_field' with '{{username}}'"
                },
                {
                    "action": "fill",
                    "value": "{{password}}",
                    "selector_info": SelectorEngine.create_custom_selector("testid", "password-input", "password_field"),
                    "human_description": "Fill 'password_field' with '••••••'"
                },
                {
                    "action": "click",
                    "value": "",
                    "selector_info": SelectorEngine.create_custom_selector("role", "button", "login_button"),
                    "human_description": "Click 'login_button' button"
                },
                {
                    "action": "assert_visible",
                    "value": "",
                    "selector_info": SelectorEngine.create_custom_selector("css", ".dashboard-header, #app", "dashboard_view"),
                    "human_description": "Assert 'dashboard_view' is visible"
                }
            ])
        elif "search" in p_lower:
            steps.extend([
                {
                    "action": "fill",
                    "value": "automation test",
                    "selector_info": SelectorEngine.create_custom_selector("css", "input[type='search'], input[name='q']", "search_box"),
                    "human_description": "Fill 'search_box' with 'automation test'"
                },
                {
                    "action": "press",
                    "value": "Enter",
                    "selector_info": SelectorEngine.create_custom_selector("css", "input[type='search'], input[name='q']", "search_box"),
                    "human_description": "Press key 'Enter' on 'search_box'"
                },
                {
                    "action": "assert_visible",
                    "value": "",
                    "selector_info": SelectorEngine.create_custom_selector("css", "#results, .search-results", "results_list"),
                    "human_description": "Assert 'results_list' is visible"
                }
            ])
        else:
            steps.extend([
                {
                    "action": "assert_title",
                    "value": "Conduit",
                    "selector_info": {},
                    "human_description": "Assert page title equals 'Conduit'"
                },
                {
                    "action": "wait",
                    "value": "1000",
                    "selector_info": {},
                    "human_description": "Wait for 1000ms"
                }
            ])

        return {
            "scenario_name": sc_name,
            "tags": ["@ai-generated", "@smoke"],
            "steps": steps
        }

    def _fallback_diagnose_failure(
        self, scenario_name: str, failed_step: Dict[str, Any], error_message: str
    ) -> Dict[str, Any]:
        sel = failed_step.get("selector_info") or {}
        orig_strat = sel.get("strategy", "css")
        orig_query = sel.get("display") or sel.get("var_name", "element")
        var_name = sel.get("var_name", "element")
        act = failed_step.get("action", "click")

        root_cause = "Selector timeout: target element was not found in the DOM within 5000ms."
        if "strict mode" in error_message.lower():
            root_cause = "Strict mode violation: selector resolved to multiple elements in DOM."
        elif "text" in error_message.lower():
            root_cause = "Assertion mismatch: expected text was not present in element."

        healed_strat = "role" if orig_strat != "role" else "testid"
        healed_query = f"{var_name.replace('_', ' ')}" if healed_strat == "role" else f"data-testid='{var_name}'"

        healed_step = dict(failed_step)
        healed_step["selector_info"] = SelectorEngine.create_custom_selector(
            healed_strat, healed_query, var_name
        )
        healed_step["human_description"] = f"Healed {act} on '{var_name}' via resilient {healed_strat} strategy"

        return {
            "root_cause": root_cause,
            "healing_strategy": f"Switched strategy from {orig_strat} to resilient {healed_strat} with exact accessible role matching.",
            "healed_step": healed_step,
            "confidence": 0.92
        }

    def _fallback_optimize_code(self, code: str) -> Dict[str, Any]:
        return {
            "explanation": "This script uses the Page Object Model pattern with Playwright synchronization and automatic retry handling.",
            "suggestions": [
                "Replace brittle CSS selectors with user-facing get_by_role or data-testid attributes.",
                "Ensure asynchronous waits leverage Playwright auto-waiting instead of fixed sleep timeouts.",
                "Parameterize environment variables using Conduit test_data fixtures."
            ],
            "improved_code": code
        }

    def _fallback_synthesize_data(self, description: str, count: int) -> List[Dict[str, Any]]:
        rows = []
        for i in range(1, count + 1):
            rows.append({
                "username": f"user_{i:03d}@conduit.io",
                "password": f"PassKey{i:03d}*!",
                "first_name": f"Alex{i}",
                "last_name": f"Taylor{i}",
                "role": "QA_Engineer" if i % 2 == 0 else "Admin",
                "account_id": f"ACC-{1000 + i}"
            })
        return rows
