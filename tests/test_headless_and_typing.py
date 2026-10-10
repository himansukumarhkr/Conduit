import os
import sys
import tempfile
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from app.core.runner import TestRunner
from app.core.recorder import BrowserRecorder
from app.core.ast_normalizer import ASTNormalizer
from app.ui.main_window import CodeEditor

_app = QApplication.instance() or QApplication(sys.argv)


def test_runner_headless_flag_logic():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        runner = TestRunner(tmp)
        test_file = os.path.join(tmp, "dummy_test.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("def test_dummy(): pass\n")

        logs = []
        finished = []
        runner.run_tests_async(
            test_file_paths=[test_file],
            browser="chromium",
            headless=True,
            env="QA",
            on_log=lambda l, m: logs.append((l, m)),
            on_finished=lambda r: finished.append(r)
        )

        import time
        for _ in range(30):
            if finished:
                break
            time.sleep(0.2)

        assert len(finished) == 1
        assert finished[0]["status"] in ("Passed", "Failed")


def test_recorder_typing_consolidation():
    recorded = []
    recorder = BrowserRecorder(on_action_recorded=lambda a: recorded.append(a))

    event1 = {
        "action": "fill",
        "value": "h",
        "meta": {"tag": "input", "attributes": {"id": "todo_input"}},
        "url": "https://example.com"
    }
    recorder._handle_raw_event(None, event1)
    assert len(recorder.recorded_actions) == 1
    assert recorder.recorded_actions[0]["value"] == "h"

    event2 = {
        "action": "fill",
        "value": "hello world",
        "meta": {"tag": "input", "attributes": {"id": "todo_input"}},
        "url": "https://example.com"
    }
    recorder._handle_raw_event(None, event2)
    assert len(recorder.recorded_actions) == 1
    assert recorder.recorded_actions[0]["value"] == "hello world"

    event3 = {
        "action": "press",
        "value": "Enter",
        "meta": {"tag": "input", "attributes": {"id": "todo_input"}},
        "url": "https://example.com"
    }
    recorder._handle_raw_event(None, event3)
    assert len(recorder.recorded_actions) == 2
    assert recorder.recorded_actions[1]["action"] == "press"
    assert recorder.recorded_actions[1]["value"] == "Enter"


def test_recorder_username_password_multi_input():
    recorded = []
    recorder = BrowserRecorder(on_action_recorded=lambda a: recorded.append(a))

    user_event = {
        "action": "fill",
        "value": "admin_user",
        "meta": {
            "tag": "input",
            "attributes": {"type": "text", "name": "username"},
            "css_selector": "form > input:nth-of-type(1)"
        },
        "url": "https://example.com/login"
    }
    recorder._handle_raw_event(None, user_event)

    pass_event = {
        "action": "fill",
        "value": "SecretPassword123!",
        "meta": {
            "tag": "input",
            "attributes": {"type": "password", "name": "password"},
            "css_selector": "form > input:nth-of-type(2)"
        },
        "url": "https://example.com/login"
    }
    recorder._handle_raw_event(None, pass_event)

    assert len(recorder.recorded_actions) == 2
    assert recorder.recorded_actions[0]["value"] == "admin_user"
    assert recorder.recorded_actions[1]["value"] == "SecretPassword123!"
    assert recorder.recorded_actions[0]["action"] == "fill"
    assert recorder.recorded_actions[1]["action"] == "fill"


def test_code_editor_auto_indentation():
    editor = CodeEditor()
    editor.setPlainText("def sample_function():")
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.EndOfBlock)
    editor.setTextCursor(cursor)

    key_enter = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier, "\n")
    editor.keyPressEvent(key_enter)

    lines = editor.toPlainText().split("\n")
    assert len(lines) == 2
    assert lines[1] == "    "

    key_tab = QKeyEvent(QEvent.KeyPress, Qt.Key_Tab, Qt.NoModifier)
    editor.keyPressEvent(key_tab)
    lines = editor.toPlainText().split("\n")
    assert lines[1] == "        "

    key_bs = QKeyEvent(QEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier)
    editor.keyPressEvent(key_bs)
    lines = editor.toPlainText().split("\n")
    assert lines[1] == "    "
