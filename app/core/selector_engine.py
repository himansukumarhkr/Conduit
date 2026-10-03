from typing import Dict, Any, Tuple, Optional
import re


class SelectorEngine:

    @staticmethod
    def clean_identifier(text: str) -> str:
        if not text:
            return "element"
        s = re.sub(r'[\s\-]+', '_', text.strip())
        s = re.sub(r'[^a-zA-Z0-9_]', '', s)
        s = re.sub(r'_+', '_', s).strip('_').lower()
        if not s or s[0].isdigit():
            s = f"elem_{s}"
        return s[:30]

    @classmethod
    def rank_selector(cls, meta: Dict[str, Any]) -> Dict[str, Any]:
        tag = (meta.get("tag") or "element").lower()
        attrs = meta.get("attributes") or {}
        text = (meta.get("text") or "").strip()
        role = meta.get("role") or ""
        aria_label = meta.get("aria_label") or attrs.get("aria-label", "")
        placeholder = meta.get("placeholder") or attrs.get("placeholder", "")
        testid = (
            attrs.get("data-testid")
            or attrs.get("data-qa")
            or attrs.get("data-cy")
            or attrs.get("data-test")
            or ""
        )
        element_id = attrs.get("id") or ""
        name_attr = attrs.get("name") or ""

        candidates = []

        if testid:
            var_name = cls.clean_identifier(f"{testid}_{tag}")
            candidates.append({
                "rank": 100,
                "strategy": "testid",
                "code": f'page.locator("[data-testid=\'{testid}\']")' if "data-testid" in attrs else f'page.locator("[{list(attrs.keys())[0]}=\'{testid}\']")',
                "locator_expr": f'self.page.locator("[data-testid=\'{testid}\']")' if "data-testid" in attrs else f'self.page.locator("[data-qa=\'{testid}\']")',
                "var_name": var_name,
                "display": f"data-testid='{testid}'"
            })

        if role and (aria_label or text):
            accessible_name = aria_label or (text[:30] if len(text) <= 30 else text[:25] + "...")
            clean_name = cls.clean_identifier(accessible_name)
            var_name = f"{clean_name}_{role}" if clean_name else f"{role}_element"
            candidates.append({
                "rank": 90,
                "strategy": "role",
                "code": f'page.get_by_role("{role}", name="{accessible_name}")',
                "locator_expr": f'self.page.get_by_role("{role}", name="{accessible_name}")',
                "var_name": cls.clean_identifier(var_name),
                "display": f"role='{role}', name='{accessible_name}'"
            })

        if aria_label:
            var_name = f"{cls.clean_identifier(aria_label)}_{tag}"
            candidates.append({
                "rank": 80,
                "strategy": "label",
                "code": f'page.get_by_label("{aria_label}")',
                "locator_expr": f'self.page.get_by_label("{aria_label}")',
                "var_name": var_name,
                "display": f"label='{aria_label}'"
            })

        if placeholder:
            var_name = f"{cls.clean_identifier(placeholder)}_input"
            candidates.append({
                "rank": 75,
                "strategy": "placeholder",
                "code": f'page.get_by_placeholder("{placeholder}")',
                "locator_expr": f'self.page.get_by_placeholder("{placeholder}")',
                "var_name": var_name,
                "display": f"placeholder='{placeholder}'"
            })

        if text and len(text) < 40 and "\n" not in text:
            var_name = f"{cls.clean_identifier(text)}_{tag}"
            candidates.append({
                "rank": 65,
                "strategy": "text",
                "code": f'page.get_by_text("{text}", exact=True)',
                "locator_expr": f'self.page.get_by_text("{text}", exact=True)',
                "var_name": var_name,
                "display": f"text='{text}'"
            })

        if name_attr and not re.search(r'\d{5,}', name_attr):
            var_name = f"{cls.clean_identifier(name_attr)}_field"
            candidates.append({
                "rank": 55,
                "strategy": "name",
                "code": f'page.locator("[name=\'{name_attr}\']")',
                "locator_expr": f'self.page.locator("[name=\'{name_attr}\']")',
                "var_name": var_name,
                "display": f"name='{name_attr}'"
            })

        if element_id and not re.search(r'(:\w+:|[0-9a-f]{8,}|[0-9]{5,})', element_id):
            var_name = f"{cls.clean_identifier(element_id)}_{tag}"
            candidates.append({
                "rank": 50,
                "strategy": "id",
                "code": f'page.locator("#{element_id}")',
                "locator_expr": f'self.page.locator("#{element_id}")',
                "var_name": var_name,
                "display": f"#{element_id}"
            })

        css_selector = meta.get("css_selector") or tag
        var_name = f"{cls.clean_identifier(text or tag)}_{tag}"
        candidates.append({
            "rank": 20,
            "strategy": "css",
            "code": f'page.locator("{css_selector}")',
            "locator_expr": f'self.page.locator("{css_selector}")',
            "var_name": var_name,
            "display": css_selector
        })

        candidates.sort(key=lambda c: c["rank"], reverse=True)
        return candidates[0]

    @classmethod
    def generate_human_step(cls, action_type: str, selector_info: Dict[str, Any], value: str = "") -> str:
        display = selector_info.get("display", "element")
        var_name = selector_info.get("var_name", "element")
        friendly_target = f"'{var_name.replace('_', ' ')}'"

        if action_type == "navigate":
            return f"Navigate to {value}"
        elif action_type == "click":
            return f"Click {friendly_target}"
        elif action_type == "fill":
            masked_val = "••••••" if "password" in var_name else f"'{value}'"
            return f"Fill {friendly_target} with {masked_val}"
        elif action_type == "assert_visible":
            return f"Assert {friendly_target} is visible"
        elif action_type == "assert_text":
            return f"Assert {friendly_target} contains text '{value}'"
        elif action_type == "assert_value":
            return f"Assert {friendly_target} has value '{value}'"
        elif action_type == "press":
            return f"Press key '{value}' on {friendly_target}"
        return f"Perform {action_type} on {friendly_target}"
