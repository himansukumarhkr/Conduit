import threading
import time
import json
from typing import List, Dict, Any, Callable, Optional
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
from app.core.selector_engine import SelectorEngine


RECORDER_INJECTED_SCRIPT = """
(() => {
    if (window.__CONDUIT_RECORDING_INITIALIZED__) return;
    window.__CONDUIT_RECORDING_INITIALIZED__ = true;

    let lastActiveElement = null;
    let lastTargetInput = null;
    let lastTypedValue = '';
    let debounceTimer = null;
    let isProgrammaticFill = false;

    function flushActiveInput() {
        if (debounceTimer) {
            clearTimeout(debounceTimer);
            debounceTimer = null;
        }
        if (!lastActiveElement && document.activeElement && (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA')) {
            lastActiveElement = document.activeElement;
            lastTypedValue = document.activeElement.value !== undefined ? document.activeElement.value : (document.activeElement.innerText || '');
        }
        if (lastActiveElement) {
            const currentVal = lastActiveElement.value !== undefined ? lastActiveElement.value : (lastActiveElement.innerText || '');
            const valToRecord = currentVal !== '' ? currentVal : lastTypedValue;
            if (valToRecord !== '') {
                const meta = getElementMeta(lastActiveElement);
                (window.__conduit_record__ || window.__testflow_record__)({
                    action: 'fill',
                    meta: meta,
                    value: valToRecord,
                    url: window.location.href,
                    timestamp: Date.now()
                });
            }
            lastActiveElement = null;
            lastTypedValue = '';
        }
    }
    window.__conduit_flush__ = flushActiveInput;

    function initOverlay() {
        if (document.getElementById('__conduit_overlay__')) return;
        const container = document.body || document.documentElement;
        if (!container) return;

        const overlay = document.createElement('div');
        overlay.id = '__conduit_overlay__';
        overlay.innerHTML = `
            <div style="position:fixed;bottom:20px;right:20px;z-index:2147483647;background:#0d1527;border:1px solid #2a3a5e;border-radius:10px;padding:8px 14px;box-shadow:0 8px 24px rgba(0,0,0,0.6);font-family:Segoe UI,sans-serif;display:flex;align-items:center;gap:10px;color:#fff;font-size:12px;">
                <div style="display:flex;align-items:center;gap:6px;">
                    <span style="display:inline-block;width:8px;height:8px;background:#ef4444;border-radius:50%;box-shadow:0 0 8px #ef4444;"></span>
                    <strong style="color:#38bdf8;font-size:12px;">Conduit</strong>
                </div>
                <div style="border-left:1px solid #334155;height:18px;"></div>
                <div style="position:relative;">
                    <button id="__conduit_vars_btn__" style="background:#1e293b;border:1px solid #38bdf8;color:#38bdf8;border-radius:6px;padding:4px 10px;font-size:11px;font-weight:bold;cursor:pointer;">📋 Variables ▾</button>
                    <div id="__conduit_vars_dropdown__" style="display:none;position:absolute;bottom:32px;left:0;background:#0f172a;border:1px solid #334155;border-radius:8px;padding:6px;min-width:210px;box-shadow:0 10px 25px rgba(0,0,0,0.7);max-height:220px;overflow-y:auto;z-index:2147483647;"></div>
                </div>
                <div style="border-left:1px solid #334155;height:18px;"></div>
                <span style="color:#94a3b8;font-size:11px;">Alt+Click: Assert</span>
                <div style="border-left:1px solid #334155;height:18px;"></div>
                <button id="__conduit_finish_btn__" style="background:#10b981;color:#fff;border:none;border-radius:6px;padding:5px 12px;font-size:11px;font-weight:bold;cursor:pointer;">Finish & Save</button>
            </div>
        `;
        container.appendChild(overlay);

        const varsBtn = document.getElementById('__conduit_vars_btn__');
        const varsDropdown = document.getElementById('__conduit_vars_dropdown__');
        if (varsBtn && varsDropdown) {
            varsBtn.onmousedown = (e) => {
                e.preventDefault();
            };
            varsBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                const isOpen = varsDropdown.style.display === 'block';
                if (isOpen) {
                    varsDropdown.style.display = 'none';
                } else {
                    renderVariablesList(varsDropdown);
                    varsDropdown.style.display = 'block';
                }
            };
        }

        const finishBtn = document.getElementById('__conduit_finish_btn__');
        if (finishBtn) {
            finishBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                flushActiveInput();
                (window.__conduit_record__ || window.__testflow_record__)({
                    action: 'finish',
                    timestamp: Date.now()
                });
            };
        }
    }

    function renderVariablesList(dropdown) {
        dropdown.innerHTML = '';
        const conduitVariables = window.__CONDUIT_VARIABLES__ || {};
        const keys = Object.keys(conduitVariables);
        if (keys.length === 0) {
            dropdown.innerHTML = '<div style="padding:6px 10px;color:#64748b;font-size:11px;">No environment variables found</div>';
            return;
        }
        dropdown.innerHTML = '<div style="padding:4px 8px;color:#94a3b8;font-size:10px;font-weight:bold;text-transform:uppercase;border-bottom:1px solid #1e293b;">Click to Insert:</div>';
        keys.forEach(k => {
            const val = conduitVariables[k];
            const item = document.createElement('div');
            item.style.cssText = 'padding:6px 10px;margin-top:2px;border-radius:4px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;color:#e2e8f0;font-size:11px;';
            item.onmouseover = () => { item.style.background = '#1e293b'; item.style.color = '#38bdf8'; };
            item.onmouseout = () => { item.style.background = 'transparent'; item.style.color = '#e2e8f0'; };

            const displayVal = (typeof val === 'string' && (k.toLowerCase().includes('pass') || k.toLowerCase().includes('secret'))) ? '********' : String(val);
            item.innerHTML = `<strong>${k}</strong><span style="color:#64748b;font-size:10px;max-width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-left:8px;">${displayVal}</span>`;

            item.onmousedown = (e) => {
                e.preventDefault();
            };
            item.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropdown.style.display = 'none';
                fillVariableIntoInput(k, String(val));
            };
            dropdown.appendChild(item);
        });
    }

    function fillVariableIntoInput(varName, value) {
        let target = lastTargetInput;
        if (!target || !document.contains(target) || (target.tagName !== 'INPUT' && target.tagName !== 'TEXTAREA')) {
            if (document.activeElement && (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA')) {
                target = document.activeElement;
            }
        }
        if (!target || !document.contains(target) || (target.tagName !== 'INPUT' && target.tagName !== 'TEXTAREA')) {
            const inputs = Array.from(document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]), textarea'));
            if (inputs.length > 0) {
                target = inputs[0];
            }
        }
        if (target) {
            target.focus();
            isProgrammaticFill = true;
            target.value = value;
            target.dispatchEvent(new Event('input', { bubbles: true }));
            target.dispatchEvent(new Event('change', { bubbles: true }));
            isProgrammaticFill = false;

            lastTargetInput = target;
            lastActiveElement = null;
            lastTypedValue = '';
            if (debounceTimer) {
                clearTimeout(debounceTimer);
                debounceTimer = null;
            }

            const meta = getElementMeta(target);
            (window.__conduit_record__ || window.__testflow_record__)({
                action: 'fill',
                meta: meta,
                value: value,
                variable_name: varName,
                url: window.location.href,
                timestamp: Date.now()
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initOverlay);
    } else {
        initOverlay();
    }

    setInterval(() => {
        if (!document.getElementById('__conduit_overlay__')) {
            initOverlay();
        }
    }, 1000);

    function getElementMeta(el) {
        if (!el || el === document.body || el === document.documentElement) {
            return { tag: 'body', attributes: {}, text: '', role: '', aria_label: '', placeholder: '', css_selector: 'body' };
        }
        const attrs = {};
        for (let i = 0; i < el.attributes.length; i++) {
            attrs[el.attributes[i].name] = el.attributes[i].value;
        }

        let labelText = '';
        if (el.labels && el.labels.length > 0) {
            labelText = (el.labels[0].innerText || el.labels[0].textContent || '').trim();
        } else if (el.id) {
            try {
                const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
                if (lbl) labelText = (lbl.innerText || lbl.textContent || '').trim();
            } catch (err) {}
        }
        if (!labelText && el.closest('label')) {
            labelText = (el.closest('label').innerText || el.closest('label').textContent || '').trim();
        }
        if (!labelText && el.parentElement) {
            const prev = el.previousElementSibling;
            if (prev && prev.tagName.toLowerCase() === 'label') {
                labelText = (prev.innerText || prev.textContent || '').trim();
            }
        }

        const ariaLabel = el.getAttribute('aria-label') || labelText || '';
        const role = el.getAttribute('role') || (el.tagName.toLowerCase() === 'input' ? (attrs.type === 'password' ? 'password' : 'textbox') : el.tagName.toLowerCase());

        return {
            tag: el.tagName.toLowerCase(),
            attributes: attrs,
            text: (el.innerText || el.textContent || '').trim().slice(0, 80),
            role: role,
            aria_label: ariaLabel,
            placeholder: el.getAttribute('placeholder') || '',
            css_selector: getUniqueCssSelector(el)
        };
    }

    function getUniqueCssSelector(el) {
        if (el.id) return `#${CSS.escape(el.id)}`;
        if (el.getAttribute('data-testid')) return `[data-testid="${CSS.escape(el.getAttribute('data-testid'))}"]`;
        let path = [];
        while (el && el.nodeType === Node.ELEMENT_NODE) {
            let selector = el.nodeName.toLowerCase();
            if (el.id) {
                selector += `#${CSS.escape(el.id)}`;
                path.unshift(selector);
                break;
            } else {
                let sibling = el, nth = 1;
                while (sibling = sibling.previousElementSibling) {
                    if (sibling.nodeName.toLowerCase() === selector) nth++;
                }
                if (nth !== 1) selector += `:nth-of-type(${nth})`;
            }
            path.unshift(selector);
            el = el.parentNode;
        }
        return path.join(' > ');
    }

    document.addEventListener('focusin', (e) => {
        if (e.target.closest('#__conduit_overlay__') || e.target.closest('#__conduit_context_menu__')) return;
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            lastTargetInput = e.target;
        }
    }, true);

    document.addEventListener('input', (e) => {
        if (isProgrammaticFill) return;
        if (e.target.closest('#__conduit_overlay__') || e.target.closest('#__conduit_context_menu__')) return;
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            lastTargetInput = e.target;
        }
        if (lastActiveElement && lastActiveElement !== e.target) {
            flushActiveInput();
        }
        lastActiveElement = e.target;
        lastTypedValue = e.target.value !== undefined ? e.target.value : (e.target.innerText || '');
        if (debounceTimer) clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            flushActiveInput();
        }, 300);
    }, true);

    document.addEventListener('keydown', (e) => {
        if (e.target.closest('#__conduit_overlay__') || e.target.closest('#__conduit_context_menu__')) return;
        if (e.key === 'Tab') {
            flushActiveInput();
        } else if (e.key === 'Enter') {
            flushActiveInput();
            const meta = getElementMeta(e.target);
            (window.__conduit_record__ || window.__testflow_record__)({
                action: 'press',
                meta: meta,
                value: 'Enter',
                url: window.location.href,
                timestamp: Date.now()
            });
        }
    }, true);

    document.addEventListener('click', (e) => {
        if (e.target.closest('#__conduit_overlay__') || e.target.closest('#__conduit_context_menu__')) return;

        flushActiveInput();

        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            lastTargetInput = e.target;
        }

        const meta = getElementMeta(e.target);

        if (e.altKey) {
            e.preventDefault();
            e.stopPropagation();
            showAssertionMenu(e.clientX, e.clientY, meta, e.target);
            return;
        }

        (window.__conduit_record__ || window.__testflow_record__)({
            action: 'click',
            meta: meta,
            url: window.location.href,
            timestamp: Date.now()
        });
    }, true);

    document.addEventListener('change', (e) => {
        if (isProgrammaticFill) return;
        if (e.target.closest('#__conduit_overlay__')) return;
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            lastTargetInput = e.target;
        }
        lastActiveElement = e.target;
        lastTypedValue = e.target.value !== undefined ? e.target.value : (e.target.innerText || '');
        flushActiveInput();
    }, true);

    document.addEventListener('focusout', (e) => {
        if (lastActiveElement === e.target) {
            flushActiveInput();
        }
    }, true);

    document.addEventListener('submit', (e) => {
        flushActiveInput();
    }, true);

    window.addEventListener('beforeunload', () => {
        flushActiveInput();
    });

    window.addEventListener('pagehide', () => {
        flushActiveInput();
    });

    function showAssertionMenu(x, y, meta, el) {
        const existing = document.getElementById('__conduit_context_menu__');
        if (existing) existing.remove();

        const menu = document.createElement('div');
        menu.id = '__conduit_context_menu__';
        menu.style.cssText = `position:fixed;top:${y}px;left:${x}px;z-index:2147483647;background:#1e293b;border:1px solid #38bdf8;border-radius:8px;padding:8px;box-shadow:0 10px 25px rgba(0,0,0,0.6);font-family:sans-serif;color:#fff;font-size:12px;min-width:180px;`;
        
        menu.innerHTML = `
            <div style="font-weight:bold;margin-bottom:6px;color:#38bdf8;border-bottom:1px solid #334155;padding-bottom:4px;">Inject Assertion</div>
            <div id="__tf_assert_visible" style="padding:6px 8px;cursor:pointer;border-radius:4px;display:flex;align-items:center;gap:6px;">👁️ Assert Visible</div>
            <div id="__tf_assert_text" style="padding:6px 8px;cursor:pointer;border-radius:4px;display:flex;align-items:center;gap:6px;">🔤 Assert Text</div>
            <div id="__tf_assert_val" style="padding:6px 8px;cursor:pointer;border-radius:4px;display:flex;align-items:center;gap:6px;">🔢 Assert Value</div>
            <div id="__tf_cancel" style="padding:4px 8px;cursor:pointer;color:#94a3b8;margin-top:4px;text-align:right;">Cancel</div>
        `;
        (document.body || document.documentElement).appendChild(menu);

        document.getElementById('__tf_assert_visible').onclick = () => {
            (window.__conduit_record__ || window.__testflow_record__)({
                action: 'assert_visible',
                meta: meta,
                url: window.location.href,
                timestamp: Date.now()
            });
            menu.remove();
        };

        document.getElementById('__tf_assert_text').onclick = () => {
            const textVal = prompt('Expected text content:', meta.text || '');
            if (textVal !== null) {
                (window.__conduit_record__ || window.__testflow_record__)({
                    action: 'assert_text',
                    meta: meta,
                    value: textVal,
                    url: window.location.href,
                    timestamp: Date.now()
                });
            }
            menu.remove();
        };

        document.getElementById('__tf_assert_val').onclick = () => {
            const val = prompt('Expected element value:', el.value || '');
            if (val !== null) {
                (window.__conduit_record__ || window.__testflow_record__)({
                    action: 'assert_value',
                    meta: meta,
                    value: val,
                    url: window.location.href,
                    timestamp: Date.now()
                });
            }
            menu.remove();
        };

        document.getElementById('__tf_cancel').onclick = () => menu.remove();
    }
})();
"""


class BrowserRecorder:

    def __init__(
        self,
        on_action_recorded: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_recording_finished: Optional[Callable[[List[Dict[str, Any]]], None]] = None
    ):
        self.on_action_recorded = on_action_recorded
        self.on_recording_finished = on_recording_finished
        self.recorded_actions: List[Dict[str, Any]] = []
        self._is_recording = False
        self._finished_notified = False
        self._thread: Optional[threading.Thread] = None
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def start_recording(
        self,
        initial_url: str = "https://example.com",
        browser_channel: str = "msedge",
        variables: Optional[Dict[str, Any]] = None
    ):
        if self._is_recording:
            return

        self.recorded_actions = []
        self._finished_notified = False
        self._is_recording = True
        self.variables = variables or {}

        def _run():
            try:
                self._playwright = sync_playwright().start()
                channels_to_try = []
                if browser_channel in ("msedge", "chrome"):
                    channels_to_try.append(browser_channel)
                for ch in ("msedge", "chrome"):
                    if ch not in channels_to_try:
                        channels_to_try.append(ch)

                launched = False
                for ch in channels_to_try:
                    try:
                        self._browser = self._playwright.chromium.launch(channel=ch, headless=False)
                        launched = True
                        break
                    except Exception:
                        pass
                if not launched:
                    self._browser = self._playwright.chromium.launch(headless=False)

                self._context = self._browser.new_context(viewport={"width": 1280, "height": 760})

                vars_json = json.dumps(self.variables)
                self._context.add_init_script(f"window.__CONDUIT_VARIABLES__ = {vars_json};")
                self._context.expose_binding("__conduit_record__", self._handle_raw_event)
                self._context.expose_binding("__testflow_record__", self._handle_raw_event)
                self._context.add_init_script(RECORDER_INJECTED_SCRIPT)

                self._page = self._context.new_page()

                nav_action = {
                    "action": "navigate",
                    "url": initial_url,
                    "value": initial_url,
                    "selector_info": {"var_name": "page", "display": "page"},
                    "human_description": f"Navigate to {initial_url}",
                    "timestamp": time.time()
                }
                self._record_step(nav_action)

                self._page.goto(initial_url)

                while self._is_recording and self._context and self._context.pages:
                    time.sleep(0.3)

            except Exception as e:
                print(f"[Conduit Recorder Error]: {e}")
            finally:
                self.stop_recording()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def _handle_raw_event(self, source, event_data: Dict[str, Any]):
        act_type = event_data.get("action")
        if act_type == "finish":
            threading.Thread(target=self.stop_recording, daemon=True).start()
            return

        with self._lock:
            meta = event_data.get("meta", {})
            val = event_data.get("value", "")
            url = event_data.get("url", "")
            var_name = event_data.get("variable_name")

            selector_info = SelectorEngine.rank_selector(meta)
            human_desc = SelectorEngine.generate_human_step(act_type, selector_info, val)
            if var_name:
                human_desc = f"Fill '{selector_info.get('display')}' with variable '{var_name}'"

            if act_type == "fill" and self.recorded_actions:
                last_action = self.recorded_actions[-1]
                if last_action.get("action") == "click":
                    last_css = last_action.get("meta", {}).get("css_selector")
                    curr_css = meta.get("css_selector")
                    if (last_css and curr_css and last_css == curr_css) or (last_action.get("selector_info", {}).get("code") == selector_info.get("code") and last_action.get("selector_info", {}).get("var_name") == selector_info.get("var_name")):
                        self.recorded_actions.pop()

            if act_type == "fill" and self.recorded_actions:
                last_action = self.recorded_actions[-1]
                same_element = False
                if last_action.get("action") == "fill":
                    last_css = last_action.get("meta", {}).get("css_selector")
                    curr_css = meta.get("css_selector")
                    if last_css and curr_css and last_css == curr_css:
                        same_element = True
                    elif last_action.get("selector_info", {}).get("code") == selector_info.get("code") and last_action.get("selector_info", {}).get("var_name") == selector_info.get("var_name"):
                        same_element = True

                if same_element:
                    last_action["value"] = val
                    if var_name:
                        last_action["variable_name"] = var_name
                        last_action["human_description"] = human_desc
                    elif not last_action.get("variable_name"):
                        last_action["human_description"] = human_desc
                    last_action["timestamp"] = event_data.get("timestamp", time.time())
                    if self.on_action_recorded:
                        self.on_action_recorded(last_action)
                    return

            step_data = {
                "action": act_type,
                "url": url,
                "value": val,
                "meta": meta,
                "selector_info": selector_info,
                "human_description": human_desc,
                "timestamp": event_data.get("timestamp", time.time())
            }
            if var_name:
                step_data["variable_name"] = var_name

            self._record_step(step_data)

    def _record_step(self, step_data: Dict[str, Any]):
        self.recorded_actions.append(step_data)
        if self.on_action_recorded:
            self.on_action_recorded(step_data)

    def stop_recording(self) -> List[Dict[str, Any]]:
        self._is_recording = False
        try:
            if self._page and not self._page.is_closed():
                try:
                    self._page.evaluate("if (window.__conduit_flush__) window.__conduit_flush__();")
                    time.sleep(0.15)
                except Exception:
                    pass
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        finally:
            self._browser = None
            self._context = None
            self._page = None
            self._playwright = None

        with self._lock:
            if self.on_recording_finished and not self._finished_notified:
                self._finished_notified = True
                actions_snapshot = list(self.recorded_actions)
                self.on_recording_finished(actions_snapshot)

        return self.recorded_actions
