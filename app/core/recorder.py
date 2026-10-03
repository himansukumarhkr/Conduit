"""
Conduit - Smart Browser Recorder
Wraps Playwright and intercepts browser interactions via CDP and injected scripts.
Provides real-time selector ranking and an on-screen Assertion Injection overlay.
"""
import threading
import time
from typing import List, Dict, Any, Callable, Optional
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
from app.core.selector_engine import SelectorEngine


RECORDER_INJECTED_SCRIPT = """
(() => {
    if (window.__CONDUIT_RECORDING_INITIALIZED__) return;
    window.__CONDUIT_RECORDING_INITIALIZED__ = true;

    // Build Floating Assertion Bar
    const overlay = document.createElement('div');
    overlay.id = '__conduit_overlay__';
    overlay.innerHTML = `
        <div style="position:fixed;bottom:20px;right:20px;z-index:2147483647;background:#0d1527;border:1px solid #2a3a5e;border-radius:10px;padding:8px 14px;box-shadow:0 8px 24px rgba(0,0,0,0.5);font-family:sans-serif;display:flex;align-items:center;gap:10px;color:#fff;font-size:12px;">
            <div style="display:flex;align-items:center;gap:6px;">
                <span style="display:inline-block;width:8px;height:8px;background:#ef4444;border-radius:50%;animation:pulse 1.5s infinite;"></span>
                <strong style="color:#38bdf8;">Conduit Recording</strong>
            </div>
            <div style="border-left:1px solid #334155;height:18px;"></div>
            <span style="color:#94a3b8;">Alt+Click any element to add Assertion</span>
        </div>
    `;
    document.documentElement.appendChild(overlay);

    function getElementMeta(el) {
        if (!el || el === document.body || el === document.documentElement) {
            return { tag: 'body', attributes: {}, text: '', role: '', aria_label: '', placeholder: '', css_selector: 'body' };
        }
        const attrs = {};
        for (let i = 0; i < el.attributes.length; i++) {
            attrs[el.attributes[i].name] = el.attributes[i].value;
        }
        return {
            tag: el.tagName.toLowerCase(),
            attributes: attrs,
            text: (el.innerText || el.textContent || '').trim().slice(0, 80),
            role: el.getAttribute('role') || el.tagName.toLowerCase(),
            aria_label: el.getAttribute('aria-label') || '',
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

    // Intercept clicks
    document.addEventListener('click', (e) => {
        if (e.target.closest('#__conduit_overlay__') || e.target.closest('#__conduit_context_menu__')) return;

        const meta = getElementMeta(e.target);

        // Check if Alt is held: Trigger Assertion Modal
        if (e.altKey) {
            e.preventDefault();
            e.stopPropagation();
            showAssertionMenu(e.clientX, e.clientY, meta, e.target);
            return;
        }

        // Standard user click
        (window.__conduit_record__ || window.__testflow_record__)({
            action: 'click',
            meta: meta,
            url: window.location.href,
            timestamp: Date.now()
        });
    }, true);

    // Intercept input changes
    document.addEventListener('change', (e) => {
        if (e.target.closest('#__conduit_overlay__')) return;
        const meta = getElementMeta(e.target);
        (window.__conduit_record__ || window.__testflow_record__)({
            action: 'fill',
            meta: meta,
            value: e.target.value || '',
            url: window.location.href,
            timestamp: Date.now()
        });
    }, true);

    // Assertion menu popup
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
        document.body.appendChild(menu);

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
    """
    Manages Playwright recording sessions with pre-installed Chrome or Edge.
    """

    def __init__(self, on_action_recorded: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.on_action_recorded = on_action_recorded
        self.recorded_actions: List[Dict[str, Any]] = []
        self._is_recording = False
        self._thread: Optional[threading.Thread] = None
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def start_recording(self, initial_url: str = "https://example.com", browser_channel: str = "msedge"):
        """
        Starts the browser recorder session in a dedicated background thread.
        """
        if self._is_recording:
            return

        self.recorded_actions = []
        self._is_recording = True

        def _run():
            try:
                self._playwright = sync_playwright().start()
                # Launch local Edge or Chrome
                launch_kwargs = {"headless": False}
                if browser_channel in ("msedge", "chrome"):
                    launch_kwargs["channel"] = browser_channel

                try:
                    self._browser = self._playwright.chromium.launch(**launch_kwargs)
                except Exception as ex:
                    # Fallback to standard chromium if channel fails
                    self._browser = self._playwright.chromium.launch(headless=False)

                self._context = self._browser.new_context(viewport={"width": 1280, "height": 760})

                # Expose Python binding
                self._context.expose_binding("__conduit_record__", self._handle_raw_event)
                self._context.expose_binding("__testflow_record__", self._handle_raw_event)
                # Inject script on every frame navigation
                self._context.add_init_script(RECORDER_INJECTED_SCRIPT)

                self._page = self._context.new_page()

                # Record navigation
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

                # Keep browser session alive until stopped
                while self._is_recording and self._context and self._context.pages:
                    time.sleep(0.3)

            except Exception as e:
                print(f"[Conduit Recorder Error]: {e}")
            finally:
                self.stop_recording()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def _handle_raw_event(self, source, event_data: Dict[str, Any]):
        """Callback executed whenever browser sends an interaction."""
        with self._lock:
            act_type = event_data.get("action")
            meta = event_data.get("meta", {})
            val = event_data.get("value", "")
            url = event_data.get("url", "")

            # Run Selector Ranking Engine
            selector_info = SelectorEngine.rank_selector(meta)
            human_desc = SelectorEngine.generate_human_step(act_type, selector_info, val)

            step_data = {
                "action": act_type,
                "url": url,
                "value": val,
                "meta": meta,
                "selector_info": selector_info,
                "human_description": human_desc,
                "timestamp": event_data.get("timestamp", time.time())
            }

            self._record_step(step_data)

    def _record_step(self, step_data: Dict[str, Any]):
        self.recorded_actions.append(step_data)
        if self.on_action_recorded:
            self.on_action_recorded(step_data)

    def stop_recording(self) -> List[Dict[str, Any]]:
        """Stops the recording session and cleans up resources."""
        self._is_recording = False
        try:
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

        return self.recorded_actions
