import os
import time
import pytest
from app.core.evidence_manager import EvidenceCollector

def pytest_configure(config):
    config.addinivalue_line("filterwarnings", "ignore::pytest.PytestUnknownMarkWarning")

@pytest.fixture
def test_data():
    from app.core.test_data_manager import TestDataManager
    workspace = os.environ.get("CONDUIT_WORKSPACE", os.getcwd())
    env = os.environ.get("CONDUIT_ENV", "QA")
    mgr = TestDataManager(workspace)
    return mgr.get_environment_data(env)

@pytest.fixture(autouse=True)
def conduit_step_evidence(request):
    has_page = "page" in request.fixturenames
    page = request.getfixturevalue("page") if has_page else None
    collector = None

    enabled = os.environ.get("CONDUIT_CAPTURE_EVIDENCE", "0") == "1"
    if enabled and page:
        workspace = os.environ.get("CONDUIT_WORKSPACE", os.getcwd())
        scenario_name = request.node.name
        format_mode = os.environ.get("CONDUIT_EVIDENCE_FORMAT", "both")
        env = os.environ.get("CONDUIT_ENV", "QA")
        browser = os.environ.get("CONDUIT_BROWSER", "msedge")

        collector = EvidenceCollector(
            workspace_dir=workspace,
            scenario_name=scenario_name,
            format_mode=format_mode,
            env=env,
            browser=browser
        )
        collector.attach(page)

    yield

    rep_setup = getattr(request.node, "rep_setup", None)
    rep_call = getattr(request.node, "rep_call", None)
    passed = True
    if rep_setup and not rep_setup.passed:
        passed = False
    elif rep_call and not rep_call.passed:
        passed = False

    if collector:
        collector.finalize(test_passed=passed)

    if page and os.environ.get("CONDUIT_HEADLESS", "0") != "1":
        try:
            hold_mode = os.environ.get("CONDUIT_HOLD_BROWSER", "").lower()
            if hold_mode in ("manual", "open", "keep_open", "inspect"):
                page.wait_for_event("close", timeout=600000)
            else:
                hold_secs = float(os.environ.get("CONDUIT_HOLD_BROWSER_SECS", "3"))
                if not passed:
                    hold_secs = max(hold_secs, float(os.environ.get("CONDUIT_HOLD_ON_FAILURE_SECS", "5")))
                if hold_secs > 0:
                    time.sleep(hold_secs)
        except Exception:
            pass

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    device = os.environ.get("CONDUIT_DEVICE", "Desktop 1280x800")
    context_args = dict(browser_context_args)
    if "1920x1080" in device:
        context_args["viewport"] = {"width": 1920, "height": 1080}
    elif "1280x800" in device:
        context_args["viewport"] = {"width": 1280, "height": 800}
    elif "iPhone" in device:
        context_args["viewport"] = {"width": 390, "height": 844}
        context_args["is_mobile"] = True
    elif "Pixel" in device:
        context_args["viewport"] = {"width": 412, "height": 915}
        context_args["is_mobile"] = True
    elif "iPad" in device:
        context_args["viewport"] = {"width": 1024, "height": 1366}
        context_args["is_mobile"] = True
    return context_args
