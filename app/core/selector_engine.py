from typing import Dict, Any, Tuple, Optional
import re


class SelectorEngine:

    VALID_ARIA_ROLES = {
        "alert", "alertdialog", "application", "article", "banner", "blockquote", "button",
        "caption", "cell", "checkbox", "code", "columnheader", "combobox", "complementary",
        "contentinfo", "definition", "deletion", "dialog", "directory", "document", "emphasis",
        "feed", "figure", "form", "generic", "grid", "gridcell", "group", "heading", "img",
        "insertion", "link", "list", "listbox", "listitem", "log", "main", "marquee", "math",
        "meter", "menu", "menubar", "menuitem", "menuitemcheckbox", "menuitemradio", "navigation",
        "none", "note", "option", "paragraph", "presentation", "progressbar", "radio", "radiogroup",
        "region", "row", "rowgroup", "rowheader", "scrollbar", "search", "searchbox", "separator",
        "slider", "spinbutton", "status", "strong", "subscript", "superscript", "switch", "tab",
        "table", "tablist", "tabpanel", "term", "textbox", "time", "timer", "toolbar", "tooltip",
        "tree", "treegrid", "treeitem"
    }

    COMMON_HTML_TAGS = {
        "a", "abbr", "address", "area", "article", "aside", "audio", "b", "base", "bdi",
        "bdo", "blockquote", "body", "br", "button", "canvas", "caption", "cite", "code",
        "col", "colgroup", "data", "datalist", "dd", "del", "details", "dfn", "dialog",
        "div", "dl", "dt", "em", "embed", "fieldset", "figcaption", "figure", "footer",
        "form", "h1", "h2", "h3", "h4", "h5", "h6", "head", "header", "hgroup", "hr",
        "html", "i", "iframe", "img", "input", "ins", "kbd", "label", "legend", "li",
        "link", "main", "map", "mark", "menu", "meta", "meter", "nav", "noscript",
        "object", "ol", "optgroup", "option", "output", "p", "picture", "pre", "progress",
        "q", "rp", "rt", "ruby", "s", "samp", "script", "search", "section", "select",
        "small", "source", "span", "strong", "style", "sub", "summary", "sup", "table",
        "tbody", "td", "template", "textarea", "tfoot", "th", "thead", "time", "title",
        "tr", "track", "u", "ul", "var", "video", "wbr"
    }

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

        if tag == "input" and attrs.get("type") == "password":
            var_name = "password_input" if not element_id else f"{cls.clean_identifier(element_id)}_input"
            candidates.append({
                "rank": 95,
                "strategy": "password_input",
                "code": 'page.locator("input[type=\'password\']")' if not element_id else f'page.locator("#{element_id}")',
                "locator_expr": 'self.page.locator("input[type=\'password\']")' if not element_id else f'self.page.locator("#{element_id}")',
                "var_name": var_name,
                "display": "input[type='password']" if not element_id else f"#{element_id}"
            })

        role_clean = role.lower().strip() if role else ""
        if role_clean and role_clean not in cls.VALID_ARIA_ROLES:
            role_clean = ""
        if not role_clean:
            if tag == "button" or attrs.get("type") in ("button", "submit"):
                role_clean = "button"
            elif tag in ("input", "textarea") and attrs.get("type") not in ("checkbox", "radio", "submit", "button"):
                role_clean = "textbox"

        if role_clean and (aria_label or text):
            accessible_name = aria_label or (text[:30] if len(text) <= 30 else text[:25] + "...")
            clean_name = cls.clean_identifier(accessible_name)
            var_name = f"{clean_name}_{role_clean}" if clean_name else f"{role_clean}_element"
            candidates.append({
                "rank": 90,
                "strategy": "role",
                "code": f'page.get_by_role("{role_clean}", name="{accessible_name}")',
                "locator_expr": f'self.page.get_by_role("{role_clean}", name="{accessible_name}")',
                "var_name": cls.clean_identifier(var_name),
                "display": f"role='{role_clean}', name='{accessible_name}'"
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

        if name_attr and not re.search(r'\d{5,}', name_attr):
            var_name = f"{cls.clean_identifier(name_attr)}_field"
            candidates.append({
                "rank": 60,
                "strategy": "name",
                "code": f'page.locator("[name=\'{name_attr}\']")',
                "locator_expr": f'self.page.locator("[name=\'{name_attr}\']")',
                "var_name": var_name,
                "display": f"name='{name_attr}'"
            })

        if text and len(text) < 40 and "\n" not in text:
            var_name = f"{cls.clean_identifier(text)}_{tag}"
            text_rank = 55 if tag not in ("input", "textarea") else 25
            candidates.append({
                "rank": text_rank,
                "strategy": "text",
                "code": f'page.get_by_text("{text}", exact=True)',
                "locator_expr": f'self.page.get_by_text("{text}", exact=True)',
                "var_name": var_name,
                "display": f"text='{text}'"
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
            "code": f'page.locator({repr(css_selector)})',
            "locator_expr": f'self.page.locator({repr(css_selector)})',
            "var_name": var_name,
            "display": css_selector
        })

        candidates.sort(key=lambda c: c["rank"], reverse=True)
        return candidates[0]

    @classmethod
    def create_custom_selector(cls, strategy: str, selector: str, var_name: str = "") -> Dict[str, Any]:
        s = selector.strip()
        strat = strategy.lower()
        if not var_name:
            var_name = cls.clean_identifier(s)

        if strat == "xpath" or s.startswith("//") or s.startswith("xpath="):
            clean_xp = s[6:] if s.startswith("xpath=") else s
            return {
                "strategy": "xpath",
                "code": f'page.locator({repr("xpath=" + clean_xp)})',
                "locator_expr": f'self.page.locator({repr("xpath=" + clean_xp)})',
                "var_name": var_name,
                "display": f"xpath={clean_xp}"
            }
        elif strat == "role" or s.startswith("role=") or s.startswith("role='") or s.startswith('role="'):
            role_m = re.match(r"^(?:role=)?['\"]?([a-zA-Z0-9_-]+)['\"]?(?:,\s*name=['\"]([^'\"]*)['\"])?", s)
            if role_m:
                role_type = role_m.group(1)
                if role_type.lower() in ("div", "span"):
                    role_type = "button" if "btn" in s.lower() or "button" in s.lower() or "login" in s.lower() or "log in" in s.lower() else "textbox"
                name_attr = role_m.group(2)
                if name_attr:
                    return {
                        "strategy": "role",
                        "code": f'page.get_by_role("{role_type}", name="{name_attr}")',
                        "locator_expr": f'self.page.get_by_role("{role_type}", name="{name_attr}")',
                        "var_name": var_name,
                        "display": f"role='{role_type}', name='{name_attr}'"
                    }
                else:
                    return {
                        "strategy": "role",
                        "code": f'page.get_by_role("{role_type}")',
                        "locator_expr": f'self.page.get_by_role("{role_type}")',
                        "var_name": var_name,
                        "display": f"role='{role_type}'"
                    }
            return {
                "strategy": "role",
                "code": f'page.get_by_role({repr(s)})',
                "locator_expr": f'self.page.get_by_role({repr(s)})',
                "var_name": var_name,
                "display": f"role='{s}'"
            }
        elif strat == "testid" or s.startswith("data-testid="):
            clean_id = s
            tid_m = re.match(r"^data-testid=['\"](.*)['\"]$", s)
            if tid_m:
                clean_id = tid_m.group(1)
            return {
                "strategy": "testid",
                "code": f'page.locator("[data-testid=\'{clean_id}\']")',
                "locator_expr": f'self.page.locator("[data-testid=\'{clean_id}\']")',
                "var_name": var_name,
                "display": f"data-testid='{clean_id}'"
            }
        elif strat == "text" or s.startswith("text=") or "text='" in s or 'text="' in s:
            clean_text = s
            tm = re.match(r"^text=['\"](.*)['\"]$", s)
            if tm:
                clean_text = tm.group(1)
            return {
                "strategy": "text",
                "code": f'page.get_by_text({repr(clean_text)}, exact=True)',
                "locator_expr": f'self.page.get_by_text({repr(clean_text)}, exact=True)',
                "var_name": var_name,
                "display": f"text='{clean_text}'"
            }
        elif strat == "id" or s.startswith("id="):
            clean_id = s.lstrip("#")
            id_m = re.match(r"^id=['\"](.*)['\"]$", clean_id)
            if id_m:
                clean_id = id_m.group(1)
            return {
                "strategy": "id",
                "code": f'page.locator("#{clean_id}")',
                "locator_expr": f'self.page.locator("#{clean_id}")',
                "var_name": var_name,
                "display": f"#{clean_id}"
            }
        elif strat == "label" or s.startswith("label=") or "label='" in s or 'label="' in s:
            clean_lbl = s
            lbl_m = re.match(r"^label=['\"](.*)['\"]$", s)
            if lbl_m:
                clean_lbl = lbl_m.group(1)
            return {
                "strategy": "label",
                "code": f'page.get_by_label({repr(clean_lbl)})',
                "locator_expr": f'self.page.get_by_label({repr(clean_lbl)})',
                "var_name": var_name,
                "display": f"label='{clean_lbl}'"
            }
        elif strat == "placeholder" or s.startswith("placeholder=") or "placeholder='" in s or 'placeholder="' in s:
            clean_ph = s
            ph_m = re.match(r"^placeholder=['\"](.*)['\"]$", s)
            if ph_m:
                clean_ph = ph_m.group(1)
            return {
                "strategy": "placeholder",
                "code": f'page.get_by_placeholder({repr(clean_ph)})',
                "locator_expr": f'self.page.get_by_placeholder({repr(clean_ph)})',
                "var_name": var_name,
                "display": f"placeholder='{clean_ph}'"
            }
        else:
            s_clean = s.strip()
            s_lower = s_clean.lower()
            has_css_meta = any(ch in s_clean for ch in ('#', '.', '[', ']', '>', '+', '~', ':', ','))
            words = s_clean.split()
            if not has_css_meta and len(words) > 1 and words[-1].lower() in ("div", "span", "button", "input", "a", "link", "p"):
                tag_suffix = words[-1].lower()
                front_text = " ".join(words[:-1]).strip()
                if tag_suffix in ("button", "div") or "login" in front_text.lower() or "continue" in front_text.lower():
                    expr = f'self.page.locator("button:has-text(\'{front_text}\'), [role=\'button\']:has-text(\'{front_text}\'), input[value=\'{front_text}\'], {tag_suffix}:has-text(\'{front_text}\')")'
                    code = f'page.locator("button:has-text(\'{front_text}\'), [role=\'button\']:has-text(\'{front_text}\'), input[value=\'{front_text}\'], {tag_suffix}:has-text(\'{front_text}\')")'
                else:
                    expr = f'self.page.locator("{tag_suffix}:has-text(\'{front_text}\')")'
                    code = f'page.locator("{tag_suffix}:has-text(\'{front_text}\')")'
                return {
                    "strategy": "css",
                    "code": code,
                    "locator_expr": expr,
                    "var_name": var_name,
                    "display": s_clean
                }
            elif not has_css_meta and s_lower not in cls.COMMON_HTML_TAGS:
                if any(k in s_lower for k in ("user", "login", "email", "phone")):
                    expr = f'self.page.locator("[name=\'{s_clean}\'], [name=\'email\'], #email, #{s_clean}, [data-testid=\'{s_clean}\'], input[autocomplete*=\'username\' i], input[placeholder*=\'{s_clean}\' i], input[placeholder*=\'email\' i], input[type=\'text\'], input[type=\'email\']")'
                    code = f'page.locator("[name=\'{s_clean}\'], [name=\'email\'], #email, #{s_clean}, [data-testid=\'{s_clean}\'], input[autocomplete*=\'username\' i], input[placeholder*=\'{s_clean}\' i], input[placeholder*=\'email\' i], input[type=\'text\'], input[type=\'email\']")'
                elif any(k in s_lower for k in ("pass", "pwd", "secret")):
                    expr = f'self.page.locator("input[type=\'password\'], [name=\'{s_clean}\'], #{s_clean}, [data-testid=\'{s_clean}\'], input[placeholder*=\'{s_clean}\' i]")'
                    code = f'page.locator("input[type=\'password\'], [name=\'{s_clean}\'], #{s_clean}, [data-testid=\'{s_clean}\'], input[placeholder*=\'{s_clean}\' i]")'
                else:
                    expr = f'self.page.locator("[name=\'{s_clean}\'], #{s_clean}, [data-testid=\'{s_clean}\'], [aria-label*=\'{s_clean}\' i], input[placeholder*=\'{s_clean}\' i]")'
                    code = f'page.locator("[name=\'{s_clean}\'], #{s_clean}, [data-testid=\'{s_clean}\'], [aria-label*=\'{s_clean}\' i], input[placeholder*=\'{s_clean}\' i]")'
                return {
                    "strategy": "css",
                    "code": code,
                    "locator_expr": expr,
                    "var_name": var_name,
                    "display": s_clean
                }
            return {
                "strategy": "css",
                "code": f'page.locator({repr(s)})',
                "locator_expr": f'self.page.locator({repr(s)})',
                "var_name": var_name,
                "display": s
            }

    @classmethod
    def generate_human_step(cls, action_type: str, selector_info: Dict[str, Any], value: str = "") -> str:
        display = selector_info.get("display", "element") if selector_info else "element"
        var_name = selector_info.get("var_name", "element") if selector_info else "element"
        friendly_target = f"'{var_name.replace('_', ' ')}'"
        str_val = str(value) if value is not None else ""
        is_var = str_val.startswith("{{") and str_val.endswith("}}")
        clean_var = str_val[2:-2].strip() if is_var else ""

        if action_type == "navigate":
            return f"Navigate to variable '{clean_var}'" if is_var else f"Navigate to {str_val}"
        elif action_type == "click":
            return f"Click {friendly_target}"
        elif action_type == "fill":
            if is_var:
                return f"Fill {friendly_target} with variable '{clean_var}'"
            elif str_val.startswith("variable '"):
                return f"Fill {friendly_target} with {str_val}"
            masked_val = "'********'" if "password" in var_name else f"'{str_val}'"
            return f"Fill {friendly_target} with {masked_val}"
        elif action_type == "assert_visible":
            return f"Assert {friendly_target} is visible"
        elif action_type == "assert_text":
            return f"Assert {friendly_target} contains variable '{clean_var}'" if is_var else f"Assert {friendly_target} contains text '{str_val}'"
        elif action_type == "assert_value":
            return f"Assert {friendly_target} equals variable '{clean_var}'" if is_var else f"Assert {friendly_target} has value '{str_val}'"
        elif action_type == "assert_title":
            return f"Assert page title equals variable '{clean_var}'" if is_var else f"Assert page title equals '{str_val}'"
        elif action_type == "assert_url":
            return f"Assert page URL matches variable '{clean_var}'" if is_var else f"Assert page URL matches '{str_val}'"
        elif action_type == "wait":
            return f"Wait for {str_val}ms"
        elif action_type == "take_screenshot":
            return f"Take screenshot '{str_val}'"
        elif action_type == "api_request":
            return f"API Request: {str_val}"
        elif action_type == "press":
            return f"Press key '{str_val}' on {friendly_target}"
        return f"Perform {action_type} on {friendly_target}"
