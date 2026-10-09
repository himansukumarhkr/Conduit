import json
import pytest
from unittest.mock import patch, MagicMock

from app.core.claude_engine import ClaudeEngine
from app.core.ast_normalizer import ASTNormalizer


def test_claude_engine_init():
    engine = ClaudeEngine()
    assert not engine.is_api_available()
    assert "claude" in engine.model

    engine.set_api_key("sk-ant-test-key-1234567890")
    assert engine.is_api_available()

    engine.set_model("claude-3-5-haiku-20241022")
    assert engine.model == "claude-3-5-haiku-20241022"


def test_claude_fallback_flow_generation():
    engine = ClaudeEngine()
    prompt = "Login to conduit portal with admin credentials and verify dashboard"
    res = engine.generate_flow_from_prompt(prompt, base_url="https://app.conduit.io/login")

    assert "scenario_name" in res
    assert len(res["steps"]) >= 4
    assert res["steps"][0]["action"] == "navigate"
    assert "https://app.conduit.io/login" in res["steps"][0]["value"]

    normalizer = ASTNormalizer()
    synth = normalizer.synthesize_pom_and_test(
        scenario_name=res["scenario_name"],
        tags=res["tags"],
        actions=res["steps"]
    )
    assert len(synth["steps"]) >= 4
    assert "test_" in synth["test_func_name"]


def test_claude_fallback_diagnose_failure():
    engine = ClaudeEngine()
    failed_step = {
        "action": "click",
        "value": "",
        "selector_info": {
            "strategy": "css",
            "locator_expr": "self.page.locator('.btn-broken')",
            "var_name": "broken_submit",
            "display": ".btn-broken"
        },
        "human_description": "Click 'broken_submit' button"
    }
    err = "Timeout 5000ms exceeded waiting for locator('.btn-broken')"
    diag = engine.diagnose_and_heal_failure("Checkout Flow", failed_step, err)

    assert "root_cause" in diag
    assert "healed_step" in diag
    assert diag["confidence"] > 0.8
    assert diag["healed_step"]["selector_info"]["strategy"] in ["role", "testid"]


def test_claude_fallback_optimize_and_data():
    engine = ClaudeEngine()
    code = "def test_example(page):\n    page.goto('url')\n"
    opt = engine.optimize_and_explain_code(code)
    assert "explanation" in opt
    assert len(opt["suggestions"]) >= 2

    data = engine.synthesize_test_data("eCommerce users with order IDs", count=3)
    assert len(data) == 3
    assert "username" in data[0]
    assert "account_id" in data[0]


def test_claude_mock_live_api():
    engine = ClaudeEngine(api_key="sk-ant-valid-mock-key-for-test")
    mock_claude_response = {
        "content": [
            {
                "type": "text",
                "text": json.dumps({
                    "scenario_name": "SauceDemo Purchase",
                    "tags": ["@smoke", "@claude"],
                    "steps": [
                        {
                            "action": "navigate",
                            "strategy": "css",
                            "selector": "",
                            "var_name": "",
                            "value": "https://www.saucedemo.com",
                            "human_description": "Navigate to SauceDemo"
                        },
                        {
                            "action": "fill",
                            "strategy": "id",
                            "selector": "user-name",
                            "var_name": "username_input",
                            "value": "standard_user",
                            "human_description": "Fill username with 'standard_user'"
                        },
                        {
                            "action": "click",
                            "strategy": "role",
                            "selector": "login-button",
                            "var_name": "login_btn",
                            "value": "",
                            "human_description": "Click login button"
                        }
                    ]
                })
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_claude_response).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = engine.generate_flow_from_prompt("Purchase flow on saucedemo")
        assert res["scenario_name"] == "SauceDemo Purchase"
        assert len(res["steps"]) == 3
        assert res["steps"][1]["action"] == "fill"
        assert res["steps"][1]["value"] == "standard_user"


def test_claude_test_connection():
    engine = ClaudeEngine()
    ok, msg = engine.test_connection()
    assert not ok
    assert "Anthropic API key is not configured" in msg

    engine.set_api_key("sk-ant-valid-mock-key")
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"content": [{"type": "text", "text": "PONG"}]}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        ok, msg = engine.test_connection()
        assert ok
        assert "Connected to Anthropic API" in msg
