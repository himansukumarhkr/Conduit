import os
import sys
import re
import time
import webbrowser
from typing import List, Dict, Any

from PySide6.QtCore import (
    Qt, QRect, QRectF, QSize, QPoint, Signal, QObject, QPropertyAnimation, Property, QThread
)
from PySide6.QtGui import (
    QColor, QPainter, QBrush, QPen, QFont, QTextCharFormat, QSyntaxHighlighter, QTextCursor
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QStyledItemDelegate, QPlainTextEdit, QScrollArea, QFrame, QDialog,
    QLineEdit, QCheckBox, QProgressBar, QSplitter, QSizePolicy, QComboBox, QStyle,
    QTabWidget, QInputDialog, QMessageBox
)
import ast

from app.core.catalog_manager import CatalogManager
from app.core.ast_normalizer import ASTNormalizer
from app.core.selector_engine import SelectorEngine
from app.core.recorder import BrowserRecorder
from app.core.runner import TestRunner
from app.core.test_data_manager import TestDataManager
from app.core.claude_engine import ClaudeEngine


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(QFont("Consolas", 10))
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #070b13;
                border: 1px solid #1e293b;
                border-radius: 6px;
                color: #e2e8f0;
                padding: 8px;
                selection-background-color: #1d4ed8;
                selection-color: #ffffff;
            }
        """)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Return or key == Qt.Key_Enter:
            cursor = self.textCursor()
            line_text = cursor.block().text()
            col = cursor.positionInBlock()
            line_before_cursor = line_text[:col]
            indent_match = re.match(r"^(\s*)", line_before_cursor)
            indent = indent_match.group(1) if indent_match else ""
            if line_before_cursor.rstrip().endswith(":"):
                indent += "    "
            cursor.insertText("\n" + indent)
            self.setTextCursor(cursor)
            return

        elif key == Qt.Key_Tab:
            cursor = self.textCursor()
            if cursor.hasSelection():
                start = cursor.selectionStart()
                end = cursor.selectionEnd()
                cursor.setPosition(start)
                start_block = cursor.blockNumber()
                cursor.setPosition(end)
                end_block = cursor.blockNumber()

                cursor.beginEditBlock()
                b = self.document().findBlockByNumber(start_block)
                while b.isValid() and b.blockNumber() <= end_block:
                    c = QTextCursor(b)
                    c.movePosition(QTextCursor.StartOfBlock)
                    c.insertText("    ")
                    b = b.next()
                cursor.endEditBlock()
            else:
                cursor.insertText("    ")
            return

        elif key == Qt.Key_Backtab:
            cursor = self.textCursor()
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            cursor.setPosition(start)
            start_block = cursor.blockNumber()
            cursor.setPosition(end)
            end_block = cursor.blockNumber()

            cursor.beginEditBlock()
            b = self.document().findBlockByNumber(start_block)
            while b.isValid() and b.blockNumber() <= end_block:
                text = b.text()
                spaces = len(text) - len(text.lstrip(" "))
                remove_count = min(spaces, 4)
                if remove_count > 0:
                    c = QTextCursor(b)
                    c.movePosition(QTextCursor.StartOfBlock)
                    for _ in range(remove_count):
                        c.deleteChar()
                b = b.next()
            cursor.endEditBlock()
            return

        elif key == Qt.Key_Backspace:
            cursor = self.textCursor()
            if not cursor.hasSelection():
                line_text = cursor.block().text()
                col = cursor.positionInBlock()
                line_before = line_text[:col]
                if line_before and line_before.isspace() and len(line_before) % 4 == 0:
                    cursor.beginEditBlock()
                    for _ in range(4):
                        cursor.deletePreviousChar()
                    cursor.endEditBlock()
                    return

        super().keyPressEvent(event)


class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []

        kw_format = QTextCharFormat()
        kw_format.setForeground(QColor("#c084fc"))
        kw_format.setFontWeight(QFont.Bold)
        keywords = [
            r"\bclass\b", r"\bdef\b", r"\breturn\b", r"\bimport\b", r"\bfrom\b",
            r"\bas\b", r"\bself\b", r"\bNone\b", r"\bTrue\b", r"\bFalse\b",
            r"\bif\b", r"\belif\b", r"\belse\b", r"\bfor\b", r"\bwhile\b",
            r"\bin\b", r"\bpass\b", r"\btry\b", r"\bexcept\b", r"\bfinally\b"
        ]
        for kw in keywords:
            self.rules.append((re.compile(kw), kw_format))

        dec_format = QTextCharFormat()
        dec_format.setForeground(QColor("#38bdf8"))
        dec_format.setFontItalic(True)
        self.rules.append((re.compile(r"@[A-Za-z0-9_\.]+"), dec_format))

        fn_format = QTextCharFormat()
        fn_format.setForeground(QColor("#60a5fa"))
        self.rules.append((re.compile(r"\bdef\s+([A-Za-z0-9_]+)"), fn_format))

        cls_format = QTextCharFormat()
        cls_format.setForeground(QColor("#facc15"))
        cls_format.setFontWeight(QFont.Bold)
        self.rules.append((re.compile(r"\bclass\s+([A-Za-z0-9_]+)"), cls_format))

        str_format = QTextCharFormat()
        str_format.setForeground(QColor("#34d399"))
        self.rules.append((re.compile(r"(\".*?\"|'.*?')"), str_format))

        num_format = QTextCharFormat()
        num_format.setForeground(QColor("#f87171"))
        self.rules.append((re.compile(r"\b[0-9]+\b"), num_format))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for match in pattern.finditer(text):
                start = match.start()
                length = match.end() - start
                self.setFormat(start, length, fmt)


class ToggleSwitch(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(46, 24)
        self.setCursor(Qt.PointingHandCursor)
        self._thumb_position = 3.0
        self._anim = QPropertyAnimation(self, b"thumb_position", self)
        self._anim.setDuration(160)
        self.stateChanged.connect(self._on_state_change)

    @Property(float)
    def thumb_position(self):
        return self._thumb_position

    @thumb_position.setter
    def thumb_position(self, pos):
        self._thumb_position = pos
        self.update()

    def _on_state_change(self, state):
        self._anim.stop()
        if state == Qt.Checked.value or state is True or state == 2:
            self._anim.setStartValue(self._thumb_position)
            self._anim.setEndValue(25.0)
        else:
            self._anim.setStartValue(self._thumb_position)
            self._anim.setEndValue(3.0)
        self._anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bg_color = QColor("#2563eb") if self.isChecked() else QColor("#334155")
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 12, 12)

        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawEllipse(QRectF(self._thumb_position, 3.0, 18.0, 18.0))


class TablePillDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        col = index.column()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor("#1e293b"))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(option.rect, QColor("#0d1527"))
        else:
            painter.fillRect(option.rect, QColor("#080c14"))

        bottom_line = QRectF(option.rect.x(), option.rect.bottom(), option.rect.width(), 1)
        painter.fillRect(bottom_line, QColor("#141c2e"))

        if col == 2:
            tags_text = index.data() or ""
            tags = [t.strip() for t in tags_text.split() if t.strip()]
            x = option.rect.x() + 6
            y = option.rect.y() + (option.rect.height() - 22) // 2
            font = QFont("-apple-system", 8, QFont.Bold)
            painter.setFont(font)

            for tag in tags:
                clean = tag.replace("@", "")
                if clean == "smoke":
                    bg = QColor(37, 99, 235, 50)
                    border = QColor(59, 130, 246, 150)
                    fg = QColor("#60a5fa")
                elif clean == "failed":
                    bg = QColor(239, 68, 68, 50)
                    border = QColor(239, 68, 68, 150)
                    fg = QColor("#f87171")
                else:
                    bg = QColor(217, 119, 6, 50)
                    border = QColor(245, 158, 11, 150)
                    fg = QColor("#fbbf24")

                metrics = painter.fontMetrics()
                w = metrics.horizontalAdvance(tag) + 14
                h = 20
                rect = QRectF(x, y, w, h)

                painter.setBrush(QBrush(bg))
                painter.setPen(QPen(border, 1))
                painter.drawRoundedRect(rect, 10, 10)

                painter.setPen(fg)
                painter.drawText(rect, Qt.AlignCenter, tag)
                x += w + 6

            painter.restore()
            return

        elif col == 4:
            status = index.data() or ""
            is_passed = status == "Passed"
            bg = QColor(16, 185, 129, 45) if is_passed else QColor(239, 68, 68, 55)
            border = QColor(16, 185, 129, 120) if is_passed else QColor(239, 68, 68, 140)
            fg = QColor("#34d399") if is_passed else QColor("#f87171")

            font = QFont("-apple-system", 8, QFont.Bold)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            w = metrics.horizontalAdvance(status) + 18
            h = 22
            x = option.rect.x() + 6
            y = option.rect.y() + (option.rect.height() - h) // 2
            rect = QRectF(x, y, w, h)

            painter.setBrush(QBrush(bg))
            painter.setPen(QPen(border, 1))
            painter.drawRoundedRect(rect, 11, 11)

            painter.setPen(fg)
            painter.drawText(rect, Qt.AlignCenter, status)
            painter.restore()
            return

        painter.restore()
        super().paint(painter, option, index)


class ExecutionBridge(QObject):
    log_signal = Signal(str, str)
    progress_signal = Signal(dict)
    finished_signal = Signal(dict)
    recording_finished_signal = Signal(list)
    action_recorded_signal = Signal(dict)


class RecordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Record New Browser Journey")
        self.setFixedSize(460, 330)
        self.setStyleSheet("""
            QDialog {
                background-color: #0d1527;
                border: 1px solid #2a3a5e;
                border-radius: 12px;
            }
            QLabel {
                color: #94a3b8;
                font-size: 12px;
                font-weight: bold;
            }
            QLineEdit {
                background-color: #070b13;
                border: 1px solid #243048;
                border-radius: 6px;
                padding: 8px 12px;
                color: #ffffff;
                font-size: 13px;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
            }
            QLineEdit:focus {
                border-color: #38bdf8;
            }
            QPushButton#btnRecord {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0284c7, stop:1 #2563eb);
                color: white;
                font-weight: bold;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 13px;
                border: none;
            }
            QPushButton#btnRecord:hover {
                background: #0369a1;
            }
            QPushButton#btnCancel {
                background-color: #131b2e;
                border: 1px solid #2a3a5e;
                color: #93c5fd;
                border-radius: 8px;
                padding: 10px 18px;
                font-size: 13px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("Record New Flow")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        layout.addWidget(QLabel("Scenario Name"))
        self.name_edit = QLineEdit("Checkout Cart Journey")
        layout.addWidget(self.name_edit)

        layout.addWidget(QLabel("Starting URL"))
        self.url_edit = QLineEdit("https://demo.playwright.dev/todomvc/")
        layout.addWidget(self.url_edit)

        layout.addWidget(QLabel("Tags (comma separated)"))
        self.tags_edit = QLineEdit("@smoke, @checkout")
        layout.addWidget(self.tags_edit)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("btnCancel")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)

        record_btn = QPushButton("Start Recording")
        record_btn.setObjectName("btnRecord")
        record_btn.setCursor(Qt.PointingHandCursor)
        record_btn.clicked.connect(self.accept)
        btn_box.addWidget(record_btn)
        layout.addLayout(btn_box)

    def get_data(self):
        name = self.name_edit.text().strip() or "Recorded Flow"
        url = self.url_edit.text().strip() or "https://demo.playwright.dev/todomvc/"
        tags = [t.strip() for t in self.tags_edit.text().split(",") if t.strip()]
        return name, url, tags


class StepEditorDialog(QDialog):
    def __init__(self, step_data: dict = None, parent=None):
        super().__init__(parent)
        self.step_data = dict(step_data or {})
        self.setWindowTitle("Edit Flow Step" if step_data else "Add New Flow Step")
        self.resize(540, 560)
        self.setStyleSheet("""
            QDialog {
                background-color: #0d1527;
                border: 1px solid #2a3a5e;
                border-radius: 12px;
            }
            QLabel {
                color: #94a3b8;
                font-size: 12px;
                font-weight: bold;
            }
            QLineEdit, QComboBox {
                background-color: #070b13;
                border: 1px solid #243048;
                border-radius: 6px;
                padding: 6px 12px;
                color: #ffffff;
                font-size: 13px;
                min-height: 36px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #38bdf8;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 28px;
                border-left: 1px solid #1e293b;
            }
            QComboBox QAbstractItemView {
                background-color: #0d1527;
                color: #ffffff;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
                border: 1px solid #2a3a5e;
                padding: 4px;
            }
            QPushButton#btnSave {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0284c7, stop:1 #2563eb);
                color: white;
                font-weight: bold;
                border-radius: 8px;
                padding: 10px 22px;
                font-size: 13px;
                border: none;
                min-height: 36px;
            }
            QPushButton#btnSave:hover {
                background: #0369a1;
            }
            QPushButton#btnCancel {
                background-color: #131b2e;
                border: 1px solid #2a3a5e;
                color: #93c5fd;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 13px;
                min-height: 36px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("Edit Flow Step" if step_data else "Add New Flow Step")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        layout.addWidget(QLabel("Action Type"))
        self.action_combo = QComboBox()
        self.actions_map = [
            ("Click Element", "click"),
            ("Fill / Type Text", "fill"),
            ("Press Key", "press"),
            ("Navigate to URL", "navigate"),
            ("Assert Element Visible", "assert_visible"),
            ("Assert Element Text", "assert_text"),
            ("Assert Element Value", "assert_value"),
            ("Assert Page Title", "assert_title"),
            ("Assert Page URL", "assert_url"),
            ("Wait / Delay (ms)", "wait"),
            ("Take Screenshot", "take_screenshot"),
            ("API Request (GET)", "api_request")
        ]
        for label, act_key in self.actions_map:
            self.action_combo.addItem(label, act_key)

        cur_act = self.step_data.get("action", "click")
        for i, (_, k) in enumerate(self.actions_map):
            if k == cur_act:
                self.action_combo.setCurrentIndex(i)
                break
        self.action_combo.currentIndexChanged.connect(self._on_action_changed)
        layout.addWidget(self.action_combo)

        self.selector_frame = QWidget()
        s_layout = QVBoxLayout(self.selector_frame)
        s_layout.setContentsMargins(0, 0, 0, 0)
        s_layout.setSpacing(10)

        s_layout.addWidget(QLabel("Locator Strategy"))
        self.strat_combo = QComboBox()
        self.strat_combo.addItems(["CSS / Playwright Selector", "Text", "ID", "data-testid", "Role", "XPath"])
        cur_sel = self.step_data.get("selector_info") or {}
        strat_key = cur_sel.get("strategy", "css").lower()
        strat_map = {"css": 0, "text": 1, "id": 2, "testid": 3, "role": 4, "xpath": 5}
        self.strat_combo.setCurrentIndex(strat_map.get(strat_key, 0))
        s_layout.addWidget(self.strat_combo)

        s_layout.addWidget(QLabel("Target Selector / Element Query"))
        display_val = cur_sel.get("display", "") or cur_sel.get("var_name", "")
        self.selector_edit = QLineEdit(display_val)
        self.selector_edit.setPlaceholderText("e.g. button.submit-btn, #login, Sign In, [data-testid='btn']")
        s_layout.addWidget(self.selector_edit)

        s_layout.addWidget(QLabel("Element Variable Name (POM Class Attribute)"))
        self.var_name_edit = QLineEdit(cur_sel.get("var_name", ""))
        self.var_name_edit.setPlaceholderText("e.g. submit_button, username_input")
        s_layout.addWidget(self.var_name_edit)

        layout.addWidget(self.selector_frame)

        self.val_lbl = QLabel("Value / Parameter")
        layout.addWidget(self.val_lbl)
        self.val_edit = QLineEdit(str(self.step_data.get("value", "")))
        self.val_edit.setPlaceholderText("e.g. test string, {{username}}, https://..., 1000")
        layout.addWidget(self.val_edit)

        layout.addWidget(QLabel("Step Description (Leave blank to auto-generate)"))
        self.desc_edit = QLineEdit(self.step_data.get("human_description", ""))
        self.desc_edit.setPlaceholderText("e.g. Click 'submit_button' button")
        layout.addWidget(self.desc_edit)

        self._on_action_changed()

        layout.addStretch()

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("btnCancel")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)

        save_btn = QPushButton("Save Step")
        save_btn.setObjectName("btnSave")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self.on_save)
        btn_box.addWidget(save_btn)
        layout.addLayout(btn_box)

    def _on_action_changed(self):
        act_key = self.action_combo.currentData()
        non_elem = act_key in ["navigate", "wait", "take_screenshot", "assert_title", "assert_url", "api_request"]
        self.selector_frame.setVisible(not non_elem)
        if act_key == "navigate":
            self.val_lbl.setText("URL to Navigate")
            self.val_edit.setPlaceholderText("https://example.com or {{base_url}}")
        elif act_key == "wait":
            self.val_lbl.setText("Wait Timeout in Milliseconds")
            self.val_edit.setPlaceholderText("1000")
        elif act_key == "take_screenshot":
            self.val_lbl.setText("Screenshot Filename / Path")
            self.val_edit.setPlaceholderText("screenshot.png")
        elif act_key == "assert_title":
            self.val_lbl.setText("Expected Page Title")
            self.val_edit.setPlaceholderText("e.g. Dashboard")
        elif act_key == "assert_url":
            self.val_lbl.setText("Expected Page URL / Substring")
            self.val_edit.setPlaceholderText("e.g. /dashboard")
        elif act_key == "api_request":
            self.val_lbl.setText("API Endpoint URL")
            self.val_edit.setPlaceholderText("https://api.example.com/v1/status")
        elif act_key == "fill":
            self.val_lbl.setText("Text to Type")
            self.val_edit.setPlaceholderText("Enter text or {{test_var}}")
        elif act_key == "press":
            self.val_lbl.setText("Key to Press")
            self.val_edit.setPlaceholderText("Enter, Tab, Escape, Backspace")
        elif act_key in ["assert_text", "assert_value"]:
            self.val_lbl.setText("Expected Value")
            self.val_edit.setPlaceholderText("Expected text string")
        else:
            self.val_lbl.setText("Value / Parameter (Optional)")
            self.val_edit.setPlaceholderText("")

    def on_save(self):
        act_key = self.action_combo.currentData()
        val = self.val_edit.text().strip()
        strat_text = self.strat_combo.currentText().lower()
        strat = "css"
        if "text" in strat_text:
            strat = "text"
        elif "id" in strat_text and "data" not in strat_text:
            strat = "id"
        elif "data-testid" in strat_text:
            strat = "testid"
        elif "role" in strat_text:
            strat = "role"
        elif "xpath" in strat_text:
            strat = "xpath"

        raw_sel = self.selector_edit.text().strip()
        var_name = self.var_name_edit.text().strip()
        if not var_name and raw_sel:
            var_name = SelectorEngine.clean_identifier(raw_sel)
        elif not var_name:
            var_name = "element"

        sel_info = SelectorEngine.create_custom_selector(strat, raw_sel or var_name, var_name)
        human_desc = self.desc_edit.text().strip()
        if not human_desc:
            human_desc = SelectorEngine.generate_human_step(act_key, sel_info, val)

        self.step_data["action"] = act_key
        self.step_data["value"] = val
        self.step_data["selector_info"] = sel_info
        self.step_data["human_description"] = human_desc
        self.accept()

    def get_step_data(self) -> dict:
        return self.step_data


class SettingsDialog(QDialog):
    def __init__(self, current_settings: dict, available_envs: list = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Conduit Settings")
        self.resize(560, 680)
        self.setMinimumSize(520, 600)
        self.settings_data = dict(current_settings)
        self.available_envs = available_envs or ["QA", "Staging", "Prod"]
        self.setStyleSheet("""
            QDialog {
                background-color: #0d1527;
                border: 1px solid #2a3a5e;
                border-radius: 12px;
            }
            QLabel {
                color: #94a3b8;
                font-size: 12px;
                font-weight: bold;
            }
            QLineEdit {
                background-color: #070b13;
                border: 1px solid #243048;
                border-radius: 6px;
                padding: 6px 12px;
                color: #ffffff;
                font-size: 13px;
                min-height: 36px;
            }
            QLineEdit:focus {
                border-color: #38bdf8;
            }
            QComboBox {
                background-color: #070b13;
                border: 1px solid #243048;
                border-radius: 6px;
                padding: 6px 12px;
                color: #ffffff;
                font-size: 13px;
                min-height: 36px;
            }
            QComboBox:focus, QComboBox:hover {
                border-color: #38bdf8;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 28px;
                border-left: 1px solid #1e293b;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
            }
            QComboBox QAbstractItemView {
                background-color: #0d1527;
                color: #ffffff;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
                border: 1px solid #2a3a5e;
                outline: none;
                padding: 4px;
            }
            QCheckBox {
                color: #f1f5f9;
                font-size: 13px;
                font-weight: 500;
                spacing: 10px;
                min-height: 24px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #334155;
                background-color: #0b1120;
            }
            QCheckBox::indicator:checked {
                background-color: #2563eb;
                border-color: #3b82f6;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QPushButton#btnSave {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0284c7, stop:1 #2563eb);
                color: white;
                font-weight: bold;
                border-radius: 8px;
                padding: 10px 22px;
                font-size: 13px;
                border: none;
                min-height: 36px;
            }
            QPushButton#btnSave:hover {
                background: #0369a1;
            }
            QPushButton#btnCancel {
                background-color: #131b2e;
                border: 1px solid #2a3a5e;
                color: #93c5fd;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 13px;
                min-height: 36px;
            }
            QPushButton#btnCancel:hover {
                border-color: #3b82f6;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(14)

        title = QLabel("Framework & Execution Settings")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        main_layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 12, 4)
        layout.setSpacing(12)

        layout.addWidget(QLabel("Default Browser Channel"))
        self.browser_combo = QComboBox()
        self.browser_combo.addItems(["Microsoft Edge (msedge)", "Google Chrome (chrome)", "Chromium (bundled)"])
        cur_b = self.settings_data.get("browser", "msedge")
        if cur_b == "chrome":
            self.browser_combo.setCurrentIndex(1)
        elif cur_b == "chromium":
            self.browser_combo.setCurrentIndex(2)
        else:
            self.browser_combo.setCurrentIndex(0)
        layout.addWidget(self.browser_combo)

        layout.addWidget(QLabel("Default Base URL"))
        self.url_edit = QLineEdit(self.settings_data.get("base_url", "https://demo.playwright.dev/todomvc/"))
        layout.addWidget(self.url_edit)

        layout.addWidget(QLabel("Default Environment Target"))
        self.env_combo = QComboBox()
        self.env_combo.addItems(self.available_envs)
        cur_env = self.settings_data.get("env", "QA")
        if cur_env in self.available_envs:
            self.env_combo.setCurrentText(cur_env)
        layout.addWidget(self.env_combo)

        layout.addWidget(QLabel("Assertion Timeout (ms)"))
        self.timeout_edit = QLineEdit(str(self.settings_data.get("timeout", 5000)))
        layout.addWidget(self.timeout_edit)

        self.headless_chk = QCheckBox("Run tests in Headless mode by default")
        self.headless_chk.setChecked(self.settings_data.get("headless", True))
        layout.addWidget(self.headless_chk)

        self.traces_chk = QCheckBox("Capture Playwright Traces on Failure")
        self.traces_chk.setChecked(self.settings_data.get("record_traces", True))
        layout.addWidget(self.traces_chk)

        self.evidence_chk = QCheckBox("Capture Screenshots at every step (QA Evidence)")
        self.evidence_chk.setChecked(self.settings_data.get("capture_evidence", True))
        layout.addWidget(self.evidence_chk)

        layout.addWidget(QLabel("Evidence Output Format"))
        self.format_combo = QComboBox()
        self.format_combo.addItems([
            "Both (Folder of PNGs & Word Document)",
            "Word Document (.docx) Only",
            "Folder of PNGs Only"
        ])
        cur_fmt = self.settings_data.get("evidence_format", "both")
        if cur_fmt == "word":
            self.format_combo.setCurrentIndex(1)
        elif cur_fmt == "folder":
            self.format_combo.setCurrentIndex(2)
        else:
            self.format_combo.setCurrentIndex(0)
        layout.addWidget(self.format_combo)

        layout.addWidget(QLabel("Flaky Test Retries (Auto-retry failed scenarios)"))
        self.retries_combo = QComboBox()
        self.retries_combo.addItems(["0 (No Retries)", "1 Retry", "2 Retries", "3 Retries", "5 Retries"])
        cur_retries = self.settings_data.get("retries", 0)
        retries_map = {0: 0, 1: 1, 2: 2, 3: 3, 5: 4}
        self.retries_combo.setCurrentIndex(retries_map.get(cur_retries, 0))
        layout.addWidget(self.retries_combo)

        layout.addWidget(QLabel("Device Emulation / Viewport Preset"))
        self.device_combo = QComboBox()
        self.device_combo.addItems([
            "Desktop 1280x800",
            "Desktop 1920x1080",
            "iPhone 14 (390x844)",
            "Pixel 7 (412x915)",
            "iPad Pro (1024x1366)"
        ])
        cur_dev = self.settings_data.get("device", "Desktop 1280x800")
        if cur_dev in [
            "Desktop 1280x800",
            "Desktop 1920x1080",
            "iPhone 14 (390x844)",
            "Pixel 7 (412x915)",
            "iPad Pro (1024x1366)"
        ]:
            self.device_combo.setCurrentText(cur_dev)
        layout.addWidget(self.device_combo)

        layout.addWidget(QLabel("Anthropic Claude API Key"))
        claude_key_row = QHBoxLayout()
        self.claude_key_edit = QLineEdit(self.settings_data.get("claude_api_key", ""))
        self.claude_key_edit.setEchoMode(QLineEdit.Password)
        self.claude_key_edit.setPlaceholderText("sk-ant-api03-...")
        claude_key_row.addWidget(self.claude_key_edit, 1)

        self.btn_toggle_key = QPushButton("Show")
        self.btn_toggle_key.setFixedSize(60, 36)
        self.btn_toggle_key.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_key.clicked.connect(self._toggle_key_visibility)
        claude_key_row.addWidget(self.btn_toggle_key)
        layout.addLayout(claude_key_row)

        layout.addWidget(QLabel("Claude Model Target"))
        self.claude_model_combo = QComboBox()
        self.claude_model_combo.addItems([
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229"
        ])
        cur_model = self.settings_data.get("claude_model", "claude-3-5-sonnet-20241022")
        if cur_model in [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229"
        ]:
            self.claude_model_combo.setCurrentText(cur_model)
        layout.addWidget(self.claude_model_combo)

        test_conn_row = QHBoxLayout()
        self.btn_test_conn = QPushButton("⚡ Test Claude Connection")
        self.btn_test_conn.setCursor(Qt.PointingHandCursor)
        self.btn_test_conn.clicked.connect(self._test_claude_connection)
        test_conn_row.addWidget(self.btn_test_conn)

        cur_has_key = bool(self.settings_data.get("claude_api_key"))
        status_txt = "● Ready (Live API)" if cur_has_key else "○ Heuristic Fallback Mode"
        status_color = "#34d399" if cur_has_key else "#fbbf24"
        self.claude_status_lbl = QLabel(status_txt)
        self.claude_status_lbl.setStyleSheet(f"color: {status_color}; font-size: 11px; font-weight: bold;")
        test_conn_row.addWidget(self.claude_status_lbl)
        test_conn_row.addStretch()
        layout.addLayout(test_conn_row)

        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("btnCancel")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)

        save_btn = QPushButton("Save Settings")
        save_btn.setObjectName("btnSave")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self.on_save)
        btn_box.addWidget(save_btn)
        main_layout.addLayout(btn_box)

    def _toggle_key_visibility(self):
        if self.claude_key_edit.echoMode() == QLineEdit.Password:
            self.claude_key_edit.setEchoMode(QLineEdit.Normal)
            self.btn_toggle_key.setText("Hide")
        else:
            self.claude_key_edit.setEchoMode(QLineEdit.Password)
            self.btn_toggle_key.setText("Show")

    def _test_claude_connection(self):
        key = self.claude_key_edit.text().strip()
        model = self.claude_model_combo.currentText()
        engine = ClaudeEngine(api_key=key, model=model)
        ok, msg = engine.test_connection()
        if ok:
            self.claude_status_lbl.setText("● Connected: Live Claude API")
            self.claude_status_lbl.setStyleSheet("color: #34d399; font-size: 11px; font-weight: bold;")
        else:
            self.claude_status_lbl.setText(f"○ Heuristic Mode ({msg[:28]})")
            self.claude_status_lbl.setStyleSheet("color: #fbbf24; font-size: 11px; font-weight: bold;")

    def on_save(self):
        b_idx = self.browser_combo.currentIndex()
        browser_val = "msedge" if b_idx == 0 else ("chrome" if b_idx == 1 else "chromium")
        self.settings_data["browser"] = browser_val
        self.settings_data["base_url"] = self.url_edit.text().strip()
        self.settings_data["env"] = self.env_combo.currentText()
        try:
            self.settings_data["timeout"] = int(self.timeout_edit.text().strip())
        except ValueError:
            self.settings_data["timeout"] = 5000
        self.settings_data["headless"] = self.headless_chk.isChecked()
        self.settings_data["record_traces"] = self.traces_chk.isChecked()
        self.settings_data["capture_evidence"] = self.evidence_chk.isChecked()
        f_idx = self.format_combo.currentIndex()
        fmt_val = "both" if f_idx == 0 else ("word" if f_idx == 1 else "folder")
        self.settings_data["evidence_format"] = fmt_val
        r_idx = self.retries_combo.currentIndex()
        retries_vals = [0, 1, 2, 3, 5]
        self.settings_data["retries"] = retries_vals[r_idx] if r_idx < len(retries_vals) else 0
        self.settings_data["device"] = self.device_combo.currentText()
        self.settings_data["claude_api_key"] = self.claude_key_edit.text().strip()
        self.settings_data["claude_model"] = self.claude_model_combo.currentText()
        self.accept()

    def get_settings(self) -> dict:
        return self.settings_data


class SuitesDialog(QDialog):
    def __init__(self, catalog: CatalogManager, on_run_suite=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Test Suites & Tags")
        self.setFixedSize(480, 400)
        self.catalog = catalog
        self.on_run_suite = on_run_suite
        self.setStyleSheet("""
            QDialog {
                background-color: #0d1527;
                border: 1px solid #2a3a5e;
                border-radius: 12px;
            }
            QLabel {
                color: #e2e8f0;
            }
            QPushButton#btnClose {
                background-color: #131b2e;
                border: 1px solid #2a3a5e;
                color: #93c5fd;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Suites & Tags Overview")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        tag_counts = {}
        for sc in self.catalog.get_all_scenarios():
            for t in sc.get("tags", []):
                tag_counts[t] = tag_counts.get(t, 0) + 1

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        container = QWidget()
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(8)

        for tag, count in tag_counts.items():
            row = QFrame()
            row.setStyleSheet("background-color: #131b2e; border: 1px solid #1e293b; border-radius: 8px; padding: 6px;")
            r_box = QHBoxLayout(row)
            r_box.setContentsMargins(10, 6, 10, 6)

            t_lbl = QLabel(tag)
            t_lbl.setStyleSheet("color: #60a5fa; font-weight: bold; font-size: 13px;")
            r_box.addWidget(t_lbl)

            c_lbl = QLabel(f"{count} scenario{'s' if count != 1 else ''}")
            c_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
            r_box.addWidget(c_lbl)

            r_box.addStretch()

            run_btn = QPushButton("Run Suite")
            run_btn.setCursor(Qt.PointingHandCursor)
            run_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0284c7, stop:1 #2563eb);
                    color: white;
                    font-size: 11px;
                    font-weight: bold;
                    border-radius: 6px;
                    padding: 4px 10px;
                    border: none;
                }
                QPushButton:hover {
                    background: #0369a1;
                }
            """)
            run_btn.clicked.connect(lambda _, t=tag: self._run_tag(t))
            r_box.addWidget(run_btn)

            c_layout.addWidget(row)

        c_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        b_box = QHBoxLayout()
        b_box.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setObjectName("btnClose")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        b_box.addWidget(close_btn)
        layout.addLayout(b_box)

    def _run_tag(self, tag):
        self.accept()
        if self.on_run_suite:
            self.on_run_suite(tag)


class HistoryDialog(QDialog):
    def __init__(self, catalog: CatalogManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Execution History")
        self.setFixedSize(520, 420)
        self.catalog = catalog
        self.setStyleSheet("""
            QDialog {
                background-color: #0d1527;
                border: 1px solid #2a3a5e;
                border-radius: 12px;
            }
            QLabel {
                color: #e2e8f0;
            }
            QPushButton#btnClose {
                background-color: #131b2e;
                border: 1px solid #2a3a5e;
                color: #93c5fd;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Execution History & Runs")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        container = QWidget()
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(8)

        for sc in self.catalog.get_all_scenarios():
            row = QFrame()
            row.setStyleSheet("background-color: #131b2e; border: 1px solid #1e293b; border-radius: 8px;")
            r_box = QHBoxLayout(row)
            r_box.setContentsMargins(12, 8, 12, 8)

            n_lbl = QLabel(sc.get("name", "Scenario"))
            n_lbl.setStyleSheet("color: #f8fafc; font-weight: bold; font-size: 12px;")
            r_box.addWidget(n_lbl)

            r_box.addStretch()

            status = sc.get("status", "Passed")
            dur = sc.get("duration", "--")
            time_lbl = QLabel(f"{sc.get('last_execution', 'Unknown')} ({dur})")
            time_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
            r_box.addWidget(time_lbl)

            s_lbl = QLabel(status)
            color = "#34d399" if status == "Passed" else "#f87171"
            s_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 11px; padding: 2px 6px; border: 1px solid {color}; border-radius: 4px;")
            r_box.addWidget(s_lbl)

            c_layout.addWidget(row)

        c_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        b_box = QHBoxLayout()
        b_box.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setObjectName("btnClose")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        b_box.addWidget(close_btn)
        layout.addLayout(b_box)


class ScraperWorker(QThread):
    finished_scrape = Signal(dict)
    error_scrape = Signal(str)

    def __init__(self, mgr: TestDataManager, url: str, browser_channel: str = "msedge"):
        super().__init__()
        self.mgr = mgr
        self.url = url
        self.browser_channel = browser_channel

    def run(self):
        try:
            res = self.mgr.scrape_test_data_from_url(self.url, self.browser_channel)
            self.finished_scrape.emit(res)
        except Exception as e:
            self.error_scrape.emit(str(e))


class ClaudeWorker(QThread):
    finished_signal = Signal(dict)
    error_signal = Signal(str)

    def __init__(self, task_type: str, engine: ClaudeEngine, params: dict, parent=None):
        super().__init__(parent)
        self.task_type = task_type
        self.engine = engine
        self.params = params

    def run(self):
        try:
            if self.task_type == "generate_flow":
                res = self.engine.generate_flow_from_prompt(
                    prompt=self.params.get("prompt", ""),
                    base_url=self.params.get("base_url", "")
                )
                self.finished_signal.emit(res)
            elif self.task_type == "diagnose_and_heal":
                res = self.engine.diagnose_and_heal_failure(
                    scenario_name=self.params.get("scenario_name", "Test Scenario"),
                    failed_step=self.params.get("failed_step", {}),
                    error_message=self.params.get("error_message", "")
                )
                self.finished_signal.emit(res)
            elif self.task_type == "optimize_code":
                res = self.engine.optimize_and_explain_code(
                    code=self.params.get("code", "")
                )
                self.finished_signal.emit(res)
            elif self.task_type == "synthesize_data":
                res = self.engine.synthesize_test_data(
                    description=self.params.get("topic", ""),
                    count=self.params.get("count", 5)
                )
                self.finished_signal.emit({"rows": res})
            elif self.task_type == "test_connection":
                ok, msg = self.engine.test_connection()
                self.finished_signal.emit({"success": ok, "message": msg})
        except Exception as e:
            self.error_signal.emit(str(e))


class TestDataDialog(QDialog):
    __test__ = False

    def __init__(self, test_data_mgr: TestDataManager, current_env: str = "QA", claude_api_key: str = "", claude_model: str = "", parent=None):
        super().__init__(parent)
        self.mgr = test_data_mgr
        self.current_env = current_env
        self.claude_api_key = claude_api_key
        self.claude_model = claude_model
        self.scraped_data_cache = {}
        self.last_ai_generated_rows = []
        self._ai_worker = None
        self.setWindowTitle("Conduit - Test Data & Environments")
        self.resize(880, 680)
        self.setMinimumSize(800, 600)
        self.setStyleSheet("""
            QDialog {
                background-color: #0d1527;
                border: 1px solid #2a3a5e;
                border-radius: 12px;
            }
            QLabel {
                color: #94a3b8;
                font-size: 12px;
                font-weight: bold;
            }
            QTabWidget::pane {
                border: 1px solid #1e293b;
                background-color: #0b1120;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #131b2e;
                color: #94a3b8;
                padding: 8px 18px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
                font-size: 12px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background-color: #0b1120;
                color: #38bdf8;
                border-top: 2px solid #38bdf8;
            }
            QLineEdit, QComboBox {
                background-color: #070b13;
                border: 1px solid #243048;
                border-radius: 6px;
                padding: 6px 12px;
                color: #ffffff;
                font-size: 13px;
                min-height: 36px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #38bdf8;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 28px;
                border-left: 1px solid #1e293b;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
            }
            QComboBox QAbstractItemView {
                background-color: #0d1527;
                color: #ffffff;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
                border: 1px solid #2a3a5e;
                outline: none;
                padding: 4px;
            }
            QTableWidget {
                background-color: #070b13;
                border: 1px solid #1e293b;
                border-radius: 6px;
                gridline-color: #1e293b;
                color: #f8fafc;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #0f172a;
                color: #94a3b8;
                padding: 6px 10px;
                font-weight: bold;
                border: none;
                border-bottom: 1px solid #1e293b;
            }
            QPushButton {
                background-color: #1e293b;
                color: #f1f5f9;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: bold;
                border: 1px solid #334155;
                min-height: 34px;
            }
            QPushButton:hover {
                background-color: #2563eb;
                border-color: #3b82f6;
            }
            QPushButton#btnPrimary {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0284c7, stop:1 #2563eb);
                border: none;
                color: white;
            }
            QPushButton#btnPrimary:hover {
                background: #0369a1;
            }
            QPushButton#btnSuccess {
                background-color: #10b981;
                border: none;
                color: white;
            }
            QPushButton#btnSuccess:hover {
                background-color: #059669;
            }
            QPushButton#btnDanger {
                background-color: rgba(239, 68, 68, 0.15);
                border: 1px solid #ef4444;
                color: #f87171;
            }
            QPushButton#btnDanger:hover {
                background-color: #ef4444;
                color: white;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(14)

        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Target Environment:"))
        self.env_combo = QComboBox()
        self.refresh_env_list()
        self.env_combo.currentTextChanged.connect(self.on_env_changed)
        header_layout.addWidget(self.env_combo)

        add_env_btn = QPushButton("+ Add Environment")
        add_env_btn.setCursor(Qt.PointingHandCursor)
        add_env_btn.clicked.connect(self.add_new_environment)
        header_layout.addWidget(add_env_btn)

        del_env_btn = QPushButton("Remove Environment")
        del_env_btn.setObjectName("btnDanger")
        del_env_btn.setCursor(Qt.PointingHandCursor)
        del_env_btn.clicked.connect(self.remove_current_environment)
        header_layout.addWidget(del_env_btn)

        header_layout.addStretch()
        self.env_badge_lbl = QLabel(f"Active Context: {self.current_env}")
        self.env_badge_lbl.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13px;")
        header_layout.addWidget(self.env_badge_lbl)
        main_layout.addLayout(header_layout)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.build_variables_tab(), "Key-Value Variables")
        self.tabs.addTab(self.build_datasets_tab(), "Datasets & Tables")
        self.tabs.addTab(self.build_scraper_tab(), "🕸️ Web Scraper")
        self.tabs.addTab(self.build_ai_generator_tab(), "✨ Claude Synthetic Generator")
        main_layout.addWidget(self.tabs, 1)

        bottom_box = QHBoxLayout()
        self.status_msg = QLabel("")
        self.status_msg.setStyleSheet("color: #34d399; font-size: 12px; font-weight: bold;")
        bottom_box.addWidget(self.status_msg)
        bottom_box.addStretch()

        close_btn = QPushButton("Done")
        close_btn.setObjectName("btnPrimary")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        bottom_box.addWidget(close_btn)
        main_layout.addLayout(bottom_box)

        self.load_environment_data()

    def refresh_env_list(self):
        self.env_combo.blockSignals(True)
        self.env_combo.clear()
        envs = self.mgr.get_environments()
        self.env_combo.addItems(envs)
        if self.current_env in envs:
            self.env_combo.setCurrentText(self.current_env)
        elif envs:
            self.current_env = envs[0]
            self.env_combo.setCurrentText(self.current_env)
        self.env_combo.blockSignals(False)

    def on_env_changed(self, new_env):
        if not new_env:
            return
        self.current_env = new_env
        self.mgr.set_active_environment(new_env)
        self.env_badge_lbl.setText(f"Active Context: {new_env}")
        self.load_environment_data()

    def add_new_environment(self):
        name, ok = QInputDialog.getText(self, "Add Environment", "New environment name (e.g. UAT, DEV, STAGING-2):")
        if ok and name.strip():
            clean_name = name.strip()
            if self.mgr.add_environment(clean_name):
                self.current_env = clean_name
                self.refresh_env_list()
                self.load_environment_data()
                self.status_msg.setText(f"Created environment [{clean_name}]")
            else:
                QMessageBox.warning(self, "Conduit", f"Environment '{clean_name}' already exists.")

    def remove_current_environment(self):
        envs = self.mgr.get_environments()
        if len(envs) <= 1:
            QMessageBox.warning(self, "Conduit", "Cannot remove the only remaining environment.")
            return
        res = QMessageBox.question(self, "Conduit", f"Delete environment '{self.current_env}' and all its test data?")
        if res == QMessageBox.Yes:
            old_env = self.current_env
            self.mgr.remove_environment(old_env)
            self.current_env = self.mgr.get_active_environment()
            self.refresh_env_list()
            self.load_environment_data()
            self.status_msg.setText(f"Removed environment [{old_env}]")

    def build_variables_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.var_table = QTableWidget(0, 3)
        self.var_table.setHorizontalHeaderLabels(["Variable Name", "Value", "Action"])
        self.var_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.var_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.var_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.var_table.setColumnWidth(0, 240)
        self.var_table.setColumnWidth(2, 90)
        layout.addWidget(self.var_table, 1)

        input_row = QHBoxLayout()
        self.new_key_edit = QLineEdit()
        self.new_key_edit.setPlaceholderText("Variable Key (e.g. base_url, timeout, username)")
        input_row.addWidget(self.new_key_edit, 2)

        self.new_val_edit = QLineEdit()
        self.new_val_edit.setPlaceholderText("Value")
        input_row.addWidget(self.new_val_edit, 3)

        add_btn = QPushButton("+ Add Variable")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self.on_add_variable)
        input_row.addWidget(add_btn)

        save_vars_btn = QPushButton("💾 Save Variables")
        save_vars_btn.setObjectName("btnPrimary")
        save_vars_btn.setCursor(Qt.PointingHandCursor)
        save_vars_btn.clicked.connect(self.save_variables_table)
        input_row.addWidget(save_vars_btn)

        layout.addLayout(input_row)
        return widget

    def build_datasets_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Dataset:"))
        self.dataset_combo = QComboBox()
        self.dataset_combo.currentTextChanged.connect(self.on_dataset_selection_changed)
        top_row.addWidget(self.dataset_combo, 2)

        new_ds_btn = QPushButton("+ New Dataset")
        new_ds_btn.setCursor(Qt.PointingHandCursor)
        new_ds_btn.clicked.connect(self.create_new_dataset)
        top_row.addWidget(new_ds_btn)

        del_ds_btn = QPushButton("Delete Dataset")
        del_ds_btn.setObjectName("btnDanger")
        del_ds_btn.setCursor(Qt.PointingHandCursor)
        del_ds_btn.clicked.connect(self.delete_current_dataset)
        top_row.addWidget(del_ds_btn)

        top_row.addStretch()

        add_row_btn = QPushButton("+ Add Row")
        add_row_btn.setCursor(Qt.PointingHandCursor)
        add_row_btn.clicked.connect(self.add_dataset_row)
        top_row.addWidget(add_row_btn)

        del_row_btn = QPushButton("- Del Row")
        del_row_btn.setCursor(Qt.PointingHandCursor)
        del_row_btn.clicked.connect(self.del_dataset_row)
        top_row.addWidget(del_row_btn)

        add_col_btn = QPushButton("+ Add Column")
        add_col_btn.setCursor(Qt.PointingHandCursor)
        add_col_btn.clicked.connect(self.add_dataset_column)
        top_row.addWidget(add_col_btn)

        save_ds_btn = QPushButton("💾 Save Dataset")
        save_ds_btn.setObjectName("btnPrimary")
        save_ds_btn.setCursor(Qt.PointingHandCursor)
        save_ds_btn.clicked.connect(self.save_dataset_table)
        top_row.addWidget(save_ds_btn)

        layout.addLayout(top_row)

        self.dataset_table = QTableWidget(0, 0)
        layout.addWidget(self.dataset_table, 1)
        return widget

    def build_scraper_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        url_row = QHBoxLayout()
        self.scraper_url_edit = QLineEdit("https://demo.playwright.dev/todomvc/")
        self.scraper_url_edit.setPlaceholderText("Enter web page URL to scrape test data from...")
        url_row.addWidget(self.scraper_url_edit, 3)

        self.btn_scrape = QPushButton("⚡ Scrape Page Test Data")
        self.btn_scrape.setObjectName("btnPrimary")
        self.btn_scrape.setCursor(Qt.PointingHandCursor)
        self.btn_scrape.clicked.connect(self.run_live_scraper)
        url_row.addWidget(self.btn_scrape)

        layout.addLayout(url_row)

        self.scraper_status_lbl = QLabel("Ready to scrape form fields, test tables, and dataset items.")
        self.scraper_status_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(self.scraper_status_lbl)

        split = QSplitter(Qt.Horizontal)

        left_box = QFrame()
        left_layout = QVBoxLayout(left_box)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Extracted Form Inputs & Variables"))
        self.scraped_inputs_table = QTableWidget(0, 2)
        self.scraped_inputs_table.setHorizontalHeaderLabels(["Name / Key", "Sample Value"])
        self.scraped_inputs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.scraped_inputs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        left_layout.addWidget(self.scraped_inputs_table)
        split.addWidget(left_box)

        right_box = QFrame()
        right_layout = QVBoxLayout(right_box)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Extracted Data Tables / Lists"))
        self.scraped_tables_table = QTableWidget(0, 2)
        self.scraped_tables_table.setHorizontalHeaderLabels(["Dataset Name", "Records Found"])
        self.scraped_tables_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.scraped_tables_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        right_layout.addWidget(self.scraped_tables_table)
        split.addWidget(right_box)

        layout.addWidget(split, 1)

        import_row = QHBoxLayout()
        import_row.addStretch()
        self.btn_import_scraped = QPushButton("📥 Import Scraped Data into Environment")
        self.btn_import_scraped.setObjectName("btnSuccess")
        self.btn_import_scraped.setCursor(Qt.PointingHandCursor)
        self.btn_import_scraped.clicked.connect(self.import_scraped_data)
        import_row.addWidget(self.btn_import_scraped)
        layout.addLayout(import_row)

        return widget

    def build_ai_generator_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        hdr = QLabel("Generate realistic, context-aware synthetic test datasets using Anthropic Claude.")
        hdr.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(hdr)

        form_box = QHBoxLayout()
        form_box.setSpacing(8)

        self.ai_topic_edit = QLineEdit("E-commerce customer orders with customer_name, email, order_id, status, amount")
        self.ai_topic_edit.setPlaceholderText("Describe data to synthesize...")
        form_box.addWidget(self.ai_topic_edit, 3)

        self.ai_ds_name_edit = QLineEdit("claude_orders")
        self.ai_ds_name_edit.setPlaceholderText("Dataset Name")
        form_box.addWidget(self.ai_ds_name_edit, 1)

        self.ai_count_combo = QComboBox()
        self.ai_count_combo.addItems(["3 rows", "5 rows", "10 rows", "15 rows"])
        self.ai_count_combo.setCurrentIndex(1)
        form_box.addWidget(self.ai_count_combo)

        self.btn_run_ai_gen = QPushButton("✨ Generate with Claude")
        self.btn_run_ai_gen.setObjectName("btnPrimary")
        self.btn_run_ai_gen.setCursor(Qt.PointingHandCursor)
        self.btn_run_ai_gen.clicked.connect(self.run_claude_data_synth)
        form_box.addWidget(self.btn_run_ai_gen)

        layout.addLayout(form_box)

        self.ai_preview_table = QTableWidget(0, 0)
        layout.addWidget(self.ai_preview_table, 1)

        bottom_box = QHBoxLayout()
        self.ai_gen_status_lbl = QLabel("")
        self.ai_gen_status_lbl.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold;")
        bottom_box.addWidget(self.ai_gen_status_lbl)
        bottom_box.addStretch()

        self.btn_save_ai_dataset = QPushButton("💾 Save Dataset to Environment")
        self.btn_save_ai_dataset.setObjectName("btnSuccess")
        self.btn_save_ai_dataset.setCursor(Qt.PointingHandCursor)
        self.btn_save_ai_dataset.clicked.connect(self.save_claude_generated_dataset)
        self.btn_save_ai_dataset.setEnabled(False)
        bottom_box.addWidget(self.btn_save_ai_dataset)

        layout.addLayout(bottom_box)
        return widget

    def run_claude_data_synth(self):
        desc = self.ai_topic_edit.text().strip() or "Standard test accounts"
        cnt_map = {"3 rows": 3, "5 rows": 5, "10 rows": 10, "15 rows": 15}
        count = cnt_map.get(self.ai_count_combo.currentText(), 5)
        self.btn_run_ai_gen.setEnabled(False)
        self.ai_gen_status_lbl.setText("Synthesizing data with Claude...")

        key = getattr(self, "claude_api_key", "")
        model = getattr(self, "claude_model", "")
        engine = ClaudeEngine(api_key=key, model=model)

        self._ai_worker = ClaudeWorker("synthesize_data", engine, {"topic": desc, "count": count}, self)
        self._ai_worker.finished_signal.connect(self._on_claude_data_finished)
        self._ai_worker.error_signal.connect(self._on_claude_data_error)
        self._ai_worker.start()

    def _on_claude_data_finished(self, res: dict):
        self.btn_run_ai_gen.setEnabled(True)
        rows = res.get("rows", [])
        self.last_ai_generated_rows = rows
        if not rows:
            self.ai_gen_status_lbl.setText("No rows generated.")
            return

        headers = list(rows[0].keys())
        self.ai_preview_table.setColumnCount(len(headers))
        self.ai_preview_table.setHorizontalHeaderLabels(headers)
        self.ai_preview_table.setRowCount(len(rows))
        for r_idx, row_dict in enumerate(rows):
            for c_idx, h in enumerate(headers):
                val = str(row_dict.get(h, ""))
                self.ai_preview_table.setItem(r_idx, c_idx, QTableWidgetItem(val))

        self.btn_save_ai_dataset.setEnabled(True)
        self.ai_gen_status_lbl.setText(f"Generated {len(rows)} record(s) with Claude.")

    def _on_claude_data_error(self, err_msg: str):
        self.btn_run_ai_gen.setEnabled(True)
        self.ai_gen_status_lbl.setText(f"Generation error: {err_msg[:40]}")

    def save_claude_generated_dataset(self):
        ds_name = self.ai_ds_name_edit.text().strip() or "claude_dataset"
        rows = getattr(self, "last_ai_generated_rows", [])
        if not rows:
            return
        self.mgr.save_dataset(self.current_env, ds_name, rows)
        self.load_environment_data()
        self.status_msg.setText(f"Saved dataset '{ds_name}' ({len(rows)} records) to [{self.current_env}].")
        self.ai_gen_status_lbl.setText(f"Dataset '{ds_name}' saved to [{self.current_env}].")

    def load_environment_data(self):
        data = self.mgr.get_environment_data(self.current_env)
        variables = data.get("variables", {})

        self.var_table.setRowCount(len(variables))
        for row, (k, v) in enumerate(variables.items()):
            self.var_table.setRowHeight(row, 36)
            k_item = QTableWidgetItem(str(k))
            v_item = QTableWidgetItem(str(v))
            self.var_table.setItem(row, 0, k_item)
            self.var_table.setItem(row, 1, v_item)

            del_btn = QPushButton("Delete")
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setStyleSheet("background-color: transparent; border: 1px solid #ef4444; color: #f87171; font-size: 11px; padding: 2px 6px; border-radius: 4px;")
            del_btn.clicked.connect(lambda _, key=k: self.delete_variable(key))
            self.var_table.setCellWidget(row, 2, del_btn)

        datasets = data.get("datasets", {})
        self.dataset_combo.blockSignals(True)
        self.dataset_combo.clear()
        self.dataset_combo.addItems(list(datasets.keys()))
        self.dataset_combo.blockSignals(False)

        if datasets:
            self.load_dataset_table(list(datasets.keys())[0])
        else:
            self.dataset_table.setRowCount(0)
            self.dataset_table.setColumnCount(0)

        if "base_url" in variables:
            self.scraper_url_edit.setText(variables["base_url"])

    def on_add_variable(self):
        k = self.new_key_edit.text().strip()
        v = self.new_val_edit.text().strip()
        if not k:
            return
        self.mgr.set_variable(self.current_env, k, v)
        self.new_key_edit.clear()
        self.new_val_edit.clear()
        self.load_environment_data()
        self.status_msg.setText(f"Added variable '{k}'")

    def delete_variable(self, key):
        self.mgr.delete_variable(self.current_env, key)
        self.load_environment_data()
        self.status_msg.setText(f"Deleted variable '{key}'")

    def save_variables_table(self):
        new_vars = {}
        for r in range(self.var_table.rowCount()):
            k_item = self.var_table.item(r, 0)
            v_item = self.var_table.item(r, 1)
            if k_item and k_item.text().strip():
                k = k_item.text().strip()
                v = v_item.text().strip() if v_item else ""
                new_vars[k] = v
        env_data = self.mgr.get_environment_data(self.current_env)
        env_data["variables"] = new_vars
        self.mgr.save_environment_data(self.current_env, env_data)
        self.load_environment_data()
        self.status_msg.setText(f"Variables saved for [{self.current_env}]")

    def on_dataset_selection_changed(self, ds_name):
        if ds_name:
            self.load_dataset_table(ds_name)

    def load_dataset_table(self, ds_name):
        datasets = self.mgr.get_datasets(self.current_env)
        records = datasets.get(ds_name, [])
        if not records:
            self.dataset_table.setRowCount(0)
            self.dataset_table.setColumnCount(1)
            self.dataset_table.setHorizontalHeaderLabels(["value"])
            return

        headers = list(records[0].keys())
        self.dataset_table.setColumnCount(len(headers))
        self.dataset_table.setHorizontalHeaderLabels(headers)
        self.dataset_table.setRowCount(len(records))

        for r_idx, rec in enumerate(records):
            self.dataset_table.setRowHeight(r_idx, 34)
            for c_idx, h in enumerate(headers):
                val = rec.get(h, "")
                item = QTableWidgetItem(str(val))
                self.dataset_table.setItem(r_idx, c_idx, item)

    def create_new_dataset(self):
        name, ok = QInputDialog.getText(self, "New Dataset", "Enter dataset name (e.g. products, customers):")
        if ok and name.strip():
            clean = name.strip()
            self.mgr.save_dataset(self.current_env, clean, [{"id": 1, "name": "sample_record"}])
            self.load_environment_data()
            self.dataset_combo.setCurrentText(clean)
            self.status_msg.setText(f"Created dataset '{clean}'")

    def delete_current_dataset(self):
        cur = self.dataset_combo.currentText()
        if not cur:
            return
        res = QMessageBox.question(self, "Conduit", f"Delete dataset '{cur}'?")
        if res == QMessageBox.Yes:
            self.mgr.delete_dataset(self.current_env, cur)
            self.load_environment_data()
            self.status_msg.setText(f"Deleted dataset '{cur}'")

    def add_dataset_row(self):
        r = self.dataset_table.rowCount()
        self.dataset_table.insertRow(r)
        self.dataset_table.setRowHeight(r, 34)

    def del_dataset_row(self):
        r = self.dataset_table.currentRow()
        if r >= 0:
            self.dataset_table.removeRow(r)

    def add_dataset_column(self):
        col_name, ok = QInputDialog.getText(self, "Add Column", "Enter new column name:")
        if ok and col_name.strip():
            c = self.dataset_table.columnCount()
            self.dataset_table.insertColumn(c)
            self.dataset_table.setHorizontalHeaderItem(c, QTableWidgetItem(col_name.strip()))

    def save_dataset_table(self):
        ds_name = self.dataset_combo.currentText()
        if not ds_name:
            return
        headers = []
        for c in range(self.dataset_table.columnCount()):
            h_item = self.dataset_table.horizontalHeaderItem(c)
            headers.append(h_item.text().strip() if h_item else f"col_{c+1}")

        records = []
        for r in range(self.dataset_table.rowCount()):
            rec = {}
            for c, h in enumerate(headers):
                cell = self.dataset_table.item(r, c)
                rec[h] = cell.text().strip() if cell else ""
            records.append(rec)

        self.mgr.save_dataset(self.current_env, ds_name, records)
        self.status_msg.setText(f"Saved dataset '{ds_name}' ({len(records)} records)")

    def run_live_scraper(self):
        url = self.scraper_url_edit.text().strip()
        if not url:
            return
        self.btn_scrape.setEnabled(False)
        self.btn_scrape.setText("Scraping...")
        self.scraper_status_lbl.setText("Scraping page elements, form inputs, and data tables in background...")

        self.worker = ScraperWorker(self.mgr, url)
        self.worker.finished_scrape.connect(self.on_scrape_finished)
        self.worker.error_scrape.connect(self.on_scrape_error)
        self.worker.start()

    def on_scrape_finished(self, res: dict):
        self.btn_scrape.setEnabled(True)
        self.btn_scrape.setText("⚡ Scrape Page Test Data")
        self.scraped_data_cache = res

        vars_found = res.get("variables", {})
        datasets_found = res.get("datasets", {})
        title = res.get("title", "")

        self.scraper_status_lbl.setText(f"Scraped '{title}': Found {len(vars_found)} input variables and {len(datasets_found)} dataset tables.")

        self.scraped_inputs_table.setRowCount(len(vars_found))
        for row, (k, v) in enumerate(vars_found.items()):
            self.scraped_inputs_table.setItem(row, 0, QTableWidgetItem(str(k)))
            self.scraped_inputs_table.setItem(row, 1, QTableWidgetItem(str(v)))

        self.scraped_tables_table.setRowCount(len(datasets_found))
        for row, (d_name, d_rows) in enumerate(datasets_found.items()):
            self.scraped_tables_table.setItem(row, 0, QTableWidgetItem(str(d_name)))
            self.scraped_tables_table.setItem(row, 1, QTableWidgetItem(f"{len(d_rows)} rows"))

        self.status_msg.setText(f"Scrape successful for {res.get('url')}")

    def on_scrape_error(self, err_msg: str):
        self.btn_scrape.setEnabled(True)
        self.btn_scrape.setText("⚡ Scrape Page Test Data")
        self.scraper_status_lbl.setText(f"Scrape error: {err_msg}")
        self.status_msg.setText("Scraping failed")

    def import_scraped_data(self):
        if not self.scraped_data_cache:
            QMessageBox.information(self, "Conduit", "No scraped data to import. Please run the scraper first.")
            return

        vars_to_import = self.scraped_data_cache.get("variables", {})
        datasets_to_import = self.scraped_data_cache.get("datasets", {})

        env_data = self.mgr.get_environment_data(self.current_env)
        if "variables" not in env_data:
            env_data["variables"] = {}
        if "datasets" not in env_data:
            env_data["datasets"] = {}

        env_data["variables"].update(vars_to_import)
        env_data["datasets"].update(datasets_to_import)

        self.mgr.save_environment_data(self.current_env, env_data)
        self.load_environment_data()
        self.status_msg.setText(f"Imported {len(vars_to_import)} variables and {len(datasets_to_import)} datasets into [{self.current_env}]!")
        QMessageBox.information(self, "Conduit", f"Successfully imported scraped data into environment [{self.current_env}].")


class ClaudePromptDialog(QDialog):
    def __init__(self, engine: ClaudeEngine, base_url: str = "https://demo.playwright.dev/todomvc/", parent=None):
        super().__init__(parent)
        self.engine = engine
        self.base_url = base_url
        self.generated_scenario = None
        self._worker = None

        self.setWindowTitle("Conduit - Claude AI Flow Generator")
        self.resize(880, 720)
        self.setMinimumSize(800, 620)
        self.setStyleSheet("""
            QDialog {
                background-color: #0d1527;
                border: 1px solid #2a3a5e;
                border-radius: 12px;
            }
            QLabel {
                color: #94a3b8;
                font-size: 12px;
                font-weight: bold;
            }
            QLineEdit {
                background-color: #070b13;
                border: 1px solid #243048;
                border-radius: 6px;
                padding: 6px 12px;
                color: #ffffff;
                font-size: 13px;
                min-height: 36px;
            }
            QLineEdit:focus {
                border-color: #8b5cf6;
            }
            QPlainTextEdit {
                background-color: #070b13;
                border: 1px solid #243048;
                border-radius: 6px;
                padding: 10px;
                color: #ffffff;
                font-size: 13px;
                selection-background-color: #8b5cf6;
                selection-color: #ffffff;
            }
            QPlainTextEdit:focus {
                border-color: #8b5cf6;
            }
            QTabWidget::pane {
                border: 1px solid #1e293b;
                background-color: #0b1120;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #131b2e;
                color: #94a3b8;
                padding: 8px 18px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
                font-size: 12px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background-color: #0b1120;
                color: #a855f7;
                border-top: 2px solid #a855f7;
            }
            QTableWidget {
                background-color: #070b13;
                border: 1px solid #1e293b;
                border-radius: 6px;
                gridline-color: #1e293b;
                color: #f8fafc;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #0f172a;
                color: #94a3b8;
                padding: 6px 10px;
                font-weight: bold;
                border: none;
                border-bottom: 1px solid #1e293b;
            }
            QPushButton {
                background-color: #1e293b;
                color: #f1f5f9;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: bold;
                border: 1px solid #334155;
                min-height: 34px;
            }
            QPushButton:hover {
                background-color: #2563eb;
                border-color: #3b82f6;
            }
            QPushButton#btnGenerate {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8b5cf6, stop:1 #06b6d4);
                border: none;
                color: white;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 20px;
                border-radius: 8px;
            }
            QPushButton#btnGenerate:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #7c3aed, stop:1 #0891b2);
            }
            QPushButton#btnAccept {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10b981, stop:1 #059669);
                border: none;
                color: white;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 20px;
                border-radius: 8px;
            }
            QPushButton#btnAccept:hover {
                background: #047857;
            }
            QPushButton#btnCancel {
                background-color: #131b2e;
                border: 1px solid #2a3a5e;
                color: #93c5fd;
                border-radius: 8px;
                padding: 8px 18px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header_box = QHBoxLayout()
        title_box = QVBoxLayout()
        title_lbl = QLabel("✨ Claude Natural Language Flow Generator")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        title_box.addWidget(title_lbl)
        sub_lbl = QLabel("Generate robust Page Object Models & Playwright test specs from plain English.")
        sub_lbl.setStyleSheet("font-size: 11px; color: #94a3b8; font-weight: normal;")
        title_box.addWidget(sub_lbl)
        header_box.addLayout(title_box)

        header_box.addStretch()

        is_live = self.engine.is_api_available()
        status_text = f"● Claude API ({self.engine.model})" if is_live else "○ Heuristic Fallback Mode"
        status_color = "#34d399" if is_live else "#fbbf24"
        mode_badge = QLabel(status_text)
        mode_badge.setStyleSheet(f"background-color: rgba(139, 92, 246, 0.15); border: 1px solid #8b5cf6; color: {status_color}; font-size: 11px; font-weight: bold; padding: 4px 12px; border-radius: 12px;")
        header_box.addWidget(mode_badge)
        layout.addLayout(header_box)

        url_box = QHBoxLayout()
        url_box.addWidget(QLabel("Target URL:"))
        self.url_edit = QLineEdit(self.base_url)
        self.url_edit.setPlaceholderText("https://...")
        url_box.addWidget(self.url_edit, 1)
        layout.addLayout(url_box)

        layout.addWidget(QLabel("Requirement / Test Scenario Prompt:"))
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText("Enter test flow details...")
        self.prompt_edit.setPlainText("User logs in with valid credentials, adds an item to shopping cart, completes checkout, and asserts order confirmation.")
        self.prompt_edit.setFixedHeight(75)
        layout.addWidget(self.prompt_edit)

        quick_box = QHBoxLayout()
        quick_lbl = QLabel("Quick Presets:")
        quick_lbl.setStyleSheet("font-size: 11px; color: #64748b;")
        quick_box.addWidget(quick_lbl)

        p1_btn = QPushButton("🛒 E-Commerce Checkout")
        p1_btn.setCursor(Qt.PointingHandCursor)
        p1_btn.clicked.connect(lambda: self.prompt_edit.setPlainText("Navigate to store, select backpack item, add to shopping bag, proceed to checkout with test user standard_user, and assert thank you message."))
        quick_box.addWidget(p1_btn)

        p2_btn = QPushButton("🔐 Login & Dashboard")
        p2_btn.setCursor(Qt.PointingHandCursor)
        p2_btn.clicked.connect(lambda: self.prompt_edit.setPlainText("Navigate to login screen, fill email admin@conduit.io and password SecretPass123, click submit, and verify welcome dashboard header."))
        quick_box.addWidget(p2_btn)

        p3_btn = QPushButton("📋 Todo Task CRUD")
        p3_btn.setCursor(Qt.PointingHandCursor)
        p3_btn.clicked.connect(lambda: self.prompt_edit.setPlainText("Open TodoMVC app, add new todo 'Complete Conduit QA Automation', mark it as completed, and assert remaining item count is zero."))
        quick_box.addWidget(p3_btn)

        quick_box.addStretch()

        self.btn_generate = QPushButton("✨ Synthesize with Claude")
        self.btn_generate.setObjectName("btnGenerate")
        self.btn_generate.setCursor(Qt.PointingHandCursor)
        self.btn_generate.clicked.connect(self.run_generation)
        quick_box.addWidget(self.btn_generate)
        layout.addLayout(quick_box)

        self.status_bar_lbl = QLabel("")
        self.status_bar_lbl.setStyleSheet("color: #38bdf8; font-size: 12px; font-weight: bold;")
        layout.addWidget(self.status_bar_lbl)

        self.tabs = QTabWidget()

        self.steps_table = QTableWidget(0, 4)
        self.steps_table.setHorizontalHeaderLabels(["#", "Action", "Description", "Value / Target"])
        self.steps_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.steps_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.steps_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.steps_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self.steps_table.setColumnWidth(0, 40)
        self.steps_table.setColumnWidth(3, 180)
        self.tabs.addTab(self.steps_table, "Generated Steps")

        self.test_code_view = CodeEditor()
        self.test_code_view.setReadOnly(True)
        self.test_highlighter = PythonHighlighter(self.test_code_view.document())
        self.tabs.addTab(self.test_code_view, "test_spec.py")

        self.pom_code_view = CodeEditor()
        self.pom_code_view.setReadOnly(True)
        self.pom_highlighter = PythonHighlighter(self.pom_code_view.document())
        self.tabs.addTab(self.pom_code_view, "page_object.py")

        self.explanation_view = QPlainTextEdit()
        self.explanation_view.setReadOnly(True)
        self.tabs.addTab(self.explanation_view, "AI Architecture & Strategy")

        layout.addWidget(self.tabs, 1)

        bottom_box = QHBoxLayout()
        bottom_box.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("btnCancel")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        bottom_box.addWidget(cancel_btn)

        self.btn_accept = QPushButton("📥 Add Scenario to Test Catalog")
        self.btn_accept.setObjectName("btnAccept")
        self.btn_accept.setCursor(Qt.PointingHandCursor)
        self.btn_accept.setEnabled(False)
        self.btn_accept.clicked.connect(self.accept)
        bottom_box.addWidget(self.btn_accept)

        layout.addLayout(bottom_box)

    def run_generation(self):
        prompt = self.prompt_edit.toPlainText().strip()
        url = self.url_edit.text().strip()
        if not prompt:
            QMessageBox.warning(self, "Conduit", "Please enter a test scenario requirement.")
            return

        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("Synthesizing...")
        self.status_bar_lbl.setText("Claude is architecting Page Object Models and test steps...")

        self._worker = ClaudeWorker("generate_flow", self.engine, {"prompt": prompt, "base_url": url}, self)
        self._worker.finished_signal.connect(self._on_generation_finished)
        self._worker.error_signal.connect(self._on_generation_error)
        self._worker.start()

    def _on_generation_finished(self, res: dict):
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("✨ Synthesize with Claude")

        scenario_name = res.get("scenario_name", "Claude Generated Scenario")
        steps = res.get("steps", [])
        tags = res.get("tags", ["@smoke", "@claude"])

        normalizer = ASTNormalizer()
        synth = normalizer.synthesize_pom_and_test(
            scenario_name=scenario_name,
            tags=tags,
            actions=steps
        )

        self.steps_table.setRowCount(len(steps))
        for idx, st in enumerate(steps):
            self.steps_table.setItem(idx, 0, QTableWidgetItem(str(idx + 1)))
            self.steps_table.setItem(idx, 1, QTableWidgetItem(st.get("action", "").upper()))
            self.steps_table.setItem(idx, 2, QTableWidgetItem(st.get("human_description", "")))
            self.steps_table.setItem(idx, 3, QTableWidgetItem(str(st.get("value", "") or st.get("selector", ""))))

        self.test_code_view.setPlainText(synth.get("test_code", ""))
        pages = synth.get("pages", [])
        pom_code = pages[0].get("code", "") if pages else res.get("pom_code", "")
        self.pom_code_view.setPlainText(pom_code)

        exp_text = res.get("explanation", "Scenario successfully architected using Page Object Model and resilient Playwright locators.")
        self.explanation_view.setPlainText(exp_text)

        new_id = f"sc_{os.urandom(4).hex()}"
        self.generated_scenario = {
            "id": new_id,
            "name": scenario_name,
            "tags": tags,
            "last_execution": "Generated by Claude",
            "status": "Passed",
            "duration": "--",
            "file_name": synth.get("file_name", f"test_{new_id}.py"),
            "steps": synth.get("steps", steps),
            "code": synth.get("test_code", ""),
            "pages": synth.get("pages", [])
        }

        self.btn_accept.setEnabled(True)
        self.status_bar_lbl.setText(f"Successfully generated scenario '{scenario_name}' with {len(steps)} steps.")

    def _on_generation_error(self, err_msg: str):
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("✨ Synthesize with Claude")
        self.status_bar_lbl.setText(f"Synthesis failed: {err_msg[:60]}")
        QMessageBox.warning(self, "Conduit", f"Failed to synthesize flow: {err_msg}")

    def get_generated_scenario(self) -> dict:
        return self.generated_scenario


class ClaudeHealDialog(QDialog):
    def __init__(self, engine: ClaudeEngine, scenario: dict, failed_step: dict = None, error_message: str = "", parent=None):
        super().__init__(parent)
        self.engine = engine
        self.scenario = scenario
        self.failed_step = failed_step or (scenario.get("steps", [{}])[-1] if scenario.get("steps") else {})
        self.error_message = error_message or "Timeout waiting for element selector: Element not visible or detached from DOM."
        self.healed_data = None
        self._worker = None

        self.setWindowTitle("Conduit - Claude Autonomous Self-Healing")
        self.resize(760, 600)
        self.setMinimumSize(700, 520)
        self.setStyleSheet("""
            QDialog {
                background-color: #0d1527;
                border: 1px solid #2a3a5e;
                border-radius: 12px;
            }
            QLabel {
                color: #94a3b8;
                font-size: 12px;
                font-weight: bold;
            }
            QFrame#cardFrame {
                background-color: #0b1120;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 12px;
            }
            QPushButton {
                background-color: #1e293b;
                color: #f1f5f9;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: bold;
                border: 1px solid #334155;
                min-height: 34px;
            }
            QPushButton:hover {
                background-color: #2563eb;
                border-color: #3b82f6;
            }
            QPushButton#btnApply {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10b981, stop:1 #059669);
                border: none;
                color: white;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 22px;
                border-radius: 8px;
            }
            QPushButton#btnApply:hover {
                background: #047857;
            }
            QPushButton#btnCancel {
                background-color: #131b2e;
                border: 1px solid #2a3a5e;
                color: #93c5fd;
                border-radius: 8px;
                padding: 8px 18px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        hdr_box = QHBoxLayout()
        t_box = QVBoxLayout()
        t_lbl = QLabel("⚡ Autonomous AI Self-Healing Diagnostics")
        t_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        t_box.addWidget(t_lbl)
        sub_lbl = QLabel("Claude analyzed locator failure, computed DOM drift, and generated resilient locator strategy.")
        sub_lbl.setStyleSheet("font-size: 11px; color: #94a3b8; font-weight: normal;")
        t_box.addWidget(sub_lbl)
        hdr_box.addLayout(t_box)
        hdr_box.addStretch()

        self.conf_badge = QLabel("Confidence: Analyzing...")
        self.conf_badge.setStyleSheet("background-color: rgba(16, 185, 129, 0.15); border: 1px solid #10b981; color: #34d399; font-size: 11px; font-weight: bold; padding: 4px 12px; border-radius: 12px;")
        hdr_box.addWidget(self.conf_badge)
        layout.addLayout(hdr_box)

        err_card = QFrame()
        err_card.setObjectName("cardFrame")
        err_layout = QVBoxLayout(err_card)
        err_layout.setSpacing(6)
        err_layout.addWidget(QLabel(f"Target Scenario: {self.scenario.get('name', 'Unknown')}"))

        f_desc = self.failed_step.get("human_description", "Unknown Step")
        err_layout.addWidget(QLabel(f"Failed Step: {f_desc}"))

        err_msg_lbl = QLabel(f"Detected Runtime Error: {self.error_message}")
        err_msg_lbl.setStyleSheet("color: #f87171; font-family: Consolas; font-size: 11px;")
        err_msg_lbl.setWordWrap(True)
        err_layout.addWidget(err_msg_lbl)
        layout.addWidget(err_card)

        diag_card = QFrame()
        diag_card.setObjectName("cardFrame")
        diag_layout = QVBoxLayout(diag_card)
        diag_layout.setSpacing(8)

        diag_layout.addWidget(QLabel("Root Cause Analysis:"))
        self.root_cause_lbl = QLabel("Diagnosing locator drift...")
        self.root_cause_lbl.setWordWrap(True)
        self.root_cause_lbl.setStyleSheet("color: #f1f5f9; font-size: 12px; font-weight: normal;")
        diag_layout.addWidget(self.root_cause_lbl)

        diag_layout.addWidget(QLabel("Resilient Healing Strategy:"))
        self.strategy_lbl = QLabel("Synthesizing multi-tier selector...")
        self.strategy_lbl.setWordWrap(True)
        self.strategy_lbl.setStyleSheet("color: #38bdf8; font-size: 12px; font-weight: normal;")
        diag_layout.addWidget(self.strategy_lbl)
        layout.addWidget(diag_card)

        diff_card = QFrame()
        diff_card.setObjectName("cardFrame")
        diff_layout = QVBoxLayout(diff_card)
        diff_layout.setSpacing(6)
        diff_layout.addWidget(QLabel("Locator Strategy Transformation:"))

        sel_info = self.failed_step.get("selector_info") or {}
        orig_expr = sel_info.get("locator_expr") or sel_info.get("display") or "self.page.locator(...)"
        self.orig_lbl = QLabel(f"Broken Selector:  {orig_expr}")
        self.orig_lbl.setStyleSheet("color: #f87171; font-family: Consolas; font-size: 12px; padding: 4px; background-color: #1a0f14; border-radius: 4px;")
        diff_layout.addWidget(self.orig_lbl)

        self.healed_lbl = QLabel("Healed Selector:  Synthesizing...")
        self.healed_lbl.setStyleSheet("color: #34d399; font-family: Consolas; font-size: 12px; padding: 4px; background-color: #091f18; border-radius: 4px;")
        diff_layout.addWidget(self.healed_lbl)
        layout.addWidget(diff_card)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("btnCancel")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)

        self.btn_apply = QPushButton("🩹 Apply Healed Strategy")
        self.btn_apply.setObjectName("btnApply")
        self.btn_apply.setCursor(Qt.PointingHandCursor)
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_apply)
        layout.addLayout(btn_box)

        self.start_diagnosis()

    def start_diagnosis(self):
        s_name = self.scenario.get("name", "Test Scenario")
        self._worker = ClaudeWorker(
            "diagnose_and_heal",
            self.engine,
            {
                "scenario_name": s_name,
                "failed_step": self.failed_step,
                "error_message": self.error_message
            },
            self
        )
        self._worker.finished_signal.connect(self._on_diag_finished)
        self._worker.error_signal.connect(self._on_diag_error)
        self._worker.start()

    def _on_diag_finished(self, diag: dict):
        self.healed_data = diag
        self.root_cause_lbl.setText(diag.get("root_cause", "Selector timed out due to DOM tree restructuring."))
        self.strategy_lbl.setText(diag.get("healing_strategy", "Applied resilient accessibility locator."))
        conf = int(diag.get("confidence", 0.92) * 100)
        self.conf_badge.setText(f"Confidence: {conf}%")

        h_step = diag.get("healed_step", {})
        h_sel = h_step.get("selector_info", {})
        h_expr = h_sel.get("locator_expr") or h_sel.get("display") or "self.page.get_by_role(...)"
        self.healed_lbl.setText(f"Healed Selector:  {h_expr}")

        self.btn_apply.setEnabled(True)

    def _on_diag_error(self, err_msg: str):
        self.root_cause_lbl.setText(f"Diagnostic error: {err_msg}")
        self.strategy_lbl.setText("Falling back to local heuristic recovery.")

    def get_healed_data(self) -> dict:
        return self.healed_data


class ClaudeCodeDialog(QDialog):
    def __init__(self, engine: ClaudeEngine, code: str, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.original_code = code
        self.optimized_code = code
        self._worker = None

        self.setWindowTitle("Conduit - Claude AI Code Assistant")
        self.resize(840, 640)
        self.setMinimumSize(780, 560)
        self.setStyleSheet("""
            QDialog {
                background-color: #0d1527;
                border: 1px solid #2a3a5e;
                border-radius: 12px;
            }
            QLabel {
                color: #94a3b8;
                font-size: 12px;
                font-weight: bold;
            }
            QTabWidget::pane {
                border: 1px solid #1e293b;
                background-color: #0b1120;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #131b2e;
                color: #94a3b8;
                padding: 8px 18px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
                font-size: 12px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background-color: #0b1120;
                color: #38bdf8;
                border-top: 2px solid #38bdf8;
            }
            QPlainTextEdit {
                background-color: #070b13;
                border: 1px solid #243048;
                border-radius: 6px;
                padding: 10px;
                color: #ffffff;
                font-size: 12px;
            }
            QPushButton {
                background-color: #1e293b;
                color: #f1f5f9;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: bold;
                border: 1px solid #334155;
                min-height: 34px;
            }
            QPushButton:hover {
                background-color: #2563eb;
                border-color: #3b82f6;
            }
            QPushButton#btnApply {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0284c7, stop:1 #2563eb);
                border: none;
                color: white;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 20px;
                border-radius: 8px;
            }
            QPushButton#btnApply:hover {
                background: #0369a1;
            }
            QPushButton#btnCancel {
                background-color: #131b2e;
                border: 1px solid #2a3a5e;
                color: #93c5fd;
                border-radius: 8px;
                padding: 8px 18px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        hdr_box = QHBoxLayout()
        t_box = QVBoxLayout()
        t_lbl = QLabel("🤖 Claude Playwright Code Assistant")
        t_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        t_box.addWidget(t_lbl)
        sub_lbl = QLabel("Code walkthrough, resiliency optimization, and flakiness prevention.")
        sub_lbl.setStyleSheet("font-size: 11px; color: #94a3b8; font-weight: normal;")
        t_box.addWidget(sub_lbl)
        hdr_box.addLayout(t_box)
        hdr_box.addStretch()

        self.status_badge = QLabel("Analyzing...")
        self.status_badge.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold;")
        hdr_box.addWidget(self.status_badge)
        layout.addLayout(hdr_box)

        self.tabs = QTabWidget()

        self.exp_view = QPlainTextEdit()
        self.exp_view.setReadOnly(True)
        self.tabs.addTab(self.exp_view, "Architecture & Walkthrough")

        self.sug_view = QPlainTextEdit()
        self.sug_view.setReadOnly(True)
        self.tabs.addTab(self.sug_view, "Resiliency Recommendations")

        self.opt_view = CodeEditor()
        self.opt_view.setReadOnly(True)
        self.opt_highlighter = PythonHighlighter(self.opt_view.document())
        self.tabs.addTab(self.opt_view, "Optimized Code")

        layout.addWidget(self.tabs, 1)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        cancel_btn = QPushButton("Close")
        cancel_btn.setObjectName("btnCancel")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)

        self.btn_apply = QPushButton("⚡ Apply Optimized Code to Editor")
        self.btn_apply.setObjectName("btnApply")
        self.btn_apply.setCursor(Qt.PointingHandCursor)
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_apply)
        layout.addLayout(btn_box)

        self.start_optimization()

    def start_optimization(self):
        self._worker = ClaudeWorker(
            "optimize_code",
            self.engine,
            {"code": self.original_code},
            self
        )
        self._worker.finished_signal.connect(self._on_opt_finished)
        self._worker.error_signal.connect(self._on_opt_error)
        self._worker.start()

    def _on_opt_finished(self, res: dict):
        self.exp_view.setPlainText(res.get("explanation", ""))
        suggestions = res.get("suggestions", [])
        self.sug_view.setPlainText("\n\n• ".join(["• " + s for s in suggestions]) if suggestions else "No suggestions.")
        self.optimized_code = res.get("improved_code", self.original_code)
        self.opt_view.setPlainText(self.optimized_code)
        self.status_badge.setText("Analysis Complete")
        self.status_badge.setStyleSheet("color: #34d399; font-size: 11px; font-weight: bold;")
        self.btn_apply.setEnabled(True)

    def _on_opt_error(self, err_msg: str):
        self.status_badge.setText("Analysis Error")
        self.status_badge.setStyleSheet("color: #f87171; font-size: 11px; font-weight: bold;")
        self.exp_view.setPlainText(f"Failed to analyze code: {err_msg}")

    def get_optimized_code(self) -> str:
        return self.optimized_code


class ConduitMainWindow(QMainWindow):
    def __init__(self, workspace_dir: str):
        super().__init__()
        self.workspace_dir = workspace_dir
        self.catalog = CatalogManager(workspace_dir)
        self.ast_engine = ASTNormalizer()
        self.runner = TestRunner(workspace_dir)
        self.test_data_mgr = TestDataManager(workspace_dir)
        self.recorder = None
        self._current_recording_meta = {}

        self.last_evidence_dir = ""
        self.last_docx_report = ""
        self.last_html_report = ""
        rep_candidate = os.path.join(workspace_dir, "reports", "latest_report.html")
        if os.path.exists(rep_candidate):
            self.last_html_report = rep_candidate

        self.current_env = self.test_data_mgr.get_active_environment()
        self.selected_browser = "msedge"
        self.headless = True
        self.selected_scenario_id = "sc_001"

        self.settings = {
            "browser": "msedge",
            "base_url": "https://demo.playwright.dev/todomvc/",
            "env": self.current_env,
            "timeout": 5000,
            "headless": True,
            "record_traces": True,
            "capture_evidence": True,
            "evidence_format": "both",
            "retries": 0,
            "device": "Desktop 1280x800",
            "claude_api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
            "claude_model": os.environ.get("CONDUIT_CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
        }

        self.claude_engine = ClaudeEngine(
            api_key=self.settings.get("claude_api_key", ""),
            model=self.settings.get("claude_model", "")
        )

        self.bridge = ExecutionBridge()
        self.bridge.log_signal.connect(self.append_log)
        self.bridge.progress_signal.connect(self.update_progress)
        self.bridge.finished_signal.connect(self.on_execution_finished)
        self.bridge.recording_finished_signal.connect(self.on_recording_completed)
        self.bridge.action_recorded_signal.connect(self.on_action_recorded)

        self.init_ui()
        self.load_scenarios()

    def init_ui(self):
        self.setWindowTitle("Conduit")
        self.resize(1380, 840)
        self.setMinimumSize(1100, 700)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #080c14;
            }
            QWidget {
                color: #f8fafc;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            QPlainTextEdit, QTextEdit, QLineEdit, QComboBox {
                selection-background-color: #2563eb;
                selection-color: #ffffff;
            }
            QTableWidget {
                background-color: #080c14;
                border: none;
                gridline-color: transparent;
                outline: none;
            }
            QTableWidget::item {
                padding: 10px 8px;
                border-bottom: 1px solid #141c2e;
                color: #f8fafc;
            }
            QTableWidget::item:selected {
                background-color: #1e293b;
                color: #ffffff;
            }
            QTableWidget::item:hover {
                background-color: #0d1527;
            }
            QHeaderView::section {
                background-color: #080c14;
                color: #64748b;
                font-size: 11px;
                font-weight: bold;
                border: none;
                border-bottom: 1px solid #1e293b;
                padding: 10px 8px;
            }
            QScrollBar:vertical {
                background: #0d1527;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #25334e;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #384e78;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = self.build_sidebar()
        root_layout.addWidget(sidebar)

        main_area = QWidget()
        main_layout = QVBoxLayout(main_area)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        top_bar = self.build_top_bar()
        main_layout.addWidget(top_bar)

        content_splitter = QSplitter(Qt.Horizontal)
        content_splitter.setStyleSheet("QSplitter::handle { background-color: #1e293b; width: 1px; }")

        table_container = self.build_table_container()
        content_splitter.addWidget(table_container)

        inspector_panel = self.build_inspector_panel()
        content_splitter.addWidget(inspector_panel)
        content_splitter.setStretchFactor(0, 3)
        content_splitter.setStretchFactor(1, 2)

        main_layout.addWidget(content_splitter, 1)

        bottom_bar = self.build_bottom_bar()
        main_layout.addWidget(bottom_bar)

        root_layout.addWidget(main_area, 1)

    def build_sidebar(self):
        sidebar = QFrame()
        sidebar.setFixedWidth(72)
        sidebar.setStyleSheet("background-color: #0b101b; border-right: 1px solid #1e293b;")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        logo = QLabel("C")
        logo.setFixedSize(44, 44)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #06b6d4, stop:1 #2563eb);
            color: #ffffff;
            font-size: 24px;
            font-weight: 900;
            border-radius: 10px;
        """)
        layout.addWidget(logo)

        self.nav_catalog_btn = self._make_sidebar_btn("Catalog", active=True, clicked=self.show_catalog_view)
        self.nav_record_btn = self._make_sidebar_btn("Record", clicked=self.on_record_clicked)
        self.nav_suites_btn = self._make_sidebar_btn("Suites", clicked=self.open_suites_dialog)
        self.nav_history_btn = self._make_sidebar_btn("History", clicked=self.open_history_dialog)

        layout.addWidget(self.nav_catalog_btn)
        layout.addWidget(self.nav_record_btn)
        layout.addWidget(self.nav_suites_btn)
        layout.addWidget(self.nav_history_btn)

        layout.addStretch()

        settings_btn = self._make_sidebar_btn("Settings", clicked=self.open_settings)
        layout.addWidget(settings_btn)

        return sidebar

    def _make_sidebar_btn(self, text, active=False, clicked=None):
        btn = QPushButton(text)
        btn.setFixedSize(58, 48)
        btn.setCursor(Qt.PointingHandCursor)
        if active:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(56, 189, 248, 0.12);
                    border: 1px solid rgba(56, 189, 248, 0.3);
                    border-radius: 8px;
                    color: #38bdf8;
                    font-size: 10px;
                    font-weight: bold;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 8px;
                    color: #64748b;
                    font-size: 10px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #131b2e;
                    color: #f8fafc;
                }
            """)
        if clicked:
            btn.clicked.connect(clicked)
        return btn

    def show_catalog_view(self):
        self.nav_catalog_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(56, 189, 248, 0.12);
                border: 1px solid rgba(56, 189, 248, 0.3);
                border-radius: 8px;
                color: #38bdf8;
                font-size: 10px;
                font-weight: bold;
            }
        """)
        self.load_scenarios()

    def open_settings(self):
        dlg = SettingsDialog(self.settings, self.test_data_mgr.get_environments(), self)
        if dlg.exec() == QDialog.Accepted:
            self.settings = dlg.get_settings()
            self.claude_engine.set_api_key(self.settings.get("claude_api_key", ""))
            self.claude_engine.set_model(self.settings.get("claude_model", ""))
            self.set_environment(self.settings.get("env", "QA"))
            self.set_browser(self.settings.get("browser", "msedge"))
            new_dev = self.settings.get("device", "Desktop 1280x800")
            if hasattr(self, "device_combo_top"):
                self.device_combo_top.setCurrentText(new_dev)
            new_hl = self.settings.get("headless", True)
            if self.headless != new_hl:
                self.toggle_headless()
            self.append_log("SUCCESS", "Conduit framework settings updated successfully.")

    def open_suites_dialog(self):
        dlg = SuitesDialog(self.catalog, on_run_suite=self.run_suite_by_tag, parent=self)
        dlg.exec()

    def open_history_dialog(self):
        dlg = HistoryDialog(self.catalog, parent=self)
        dlg.exec()

    def run_suite_by_tag(self, tag: str):
        matching_ids = [
            sc["id"] for sc in self.catalog.get_all_scenarios()
            if tag in sc.get("tags", [])
        ]
        if matching_ids:
            self.append_log("INFO", f"Running suite [{tag}] ({len(matching_ids)} scenarios)...")
            self.run_scenarios_by_ids(matching_ids)
        else:
            self.append_log("WARNING", f"No scenarios found for suite tag: {tag}")

    def build_top_bar(self):
        bar = QFrame()
        bar.setFixedHeight(64)
        bar.setStyleSheet("background-color: #0d1527; border-bottom: 1px solid #1e293b;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(16)

        title = QLabel("Test Catalog")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        self.env_pill_box = QHBoxLayout()
        self.env_pill_box.setSpacing(6)
        layout.addLayout(self.env_pill_box)

        add_env_btn = QPushButton("+ Env")
        add_env_btn.setCursor(Qt.PointingHandCursor)
        add_env_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px dashed #334155;
                color: #94a3b8;
                font-size: 11px;
                font-weight: bold;
                border-radius: 14px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                color: #38bdf8;
                border-color: #38bdf8;
            }
        """)
        add_env_btn.clicked.connect(self.quick_add_env)
        layout.addWidget(add_env_btn)

        test_data_btn = QPushButton("📊 Test Data")
        test_data_btn.setCursor(Qt.PointingHandCursor)
        test_data_btn.setStyleSheet("""
            QPushButton {
                background-color: #131b2e;
                border: 1px solid #2a3a5e;
                color: #38bdf8;
                font-size: 11px;
                font-weight: bold;
                border-radius: 14px;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #1e293b;
                border-color: #38bdf8;
                color: #ffffff;
            }
        """)
        test_data_btn.clicked.connect(self.open_test_data_dialog)
        layout.addWidget(test_data_btn)

        self.render_env_pills()

        layout.addStretch()

        self.btn_claude_flow = QPushButton("✨ Claude AI Flow")
        self.btn_claude_flow.setCursor(Qt.PointingHandCursor)
        self.btn_claude_flow.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8b5cf6, stop:1 #06b6d4);
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 18px;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #7c3aed, stop:1 #0891b2);
            }
        """)
        self.btn_claude_flow.clicked.connect(self.open_claude_flow_dialog)
        layout.addWidget(self.btn_claude_flow)

        self.btn_record_flow = QPushButton("● Record New Flow")
        self.btn_record_flow.setCursor(Qt.PointingHandCursor)
        self.btn_record_flow.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0284c7, stop:1 #2563eb);
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 18px;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0369a1, stop:1 #1d4ed8);
            }
        """)
        self.btn_record_flow.clicked.connect(self.on_record_clicked)
        layout.addWidget(self.btn_record_flow)

        run_btn = QPushButton("▶ Run Selected")
        run_btn.setCursor(Qt.PointingHandCursor)
        run_btn.setStyleSheet("""
            QPushButton {
                background-color: #131b2e;
                border: 1px solid #2a3a5e;
                color: #93c5fd;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 16px;
                border-radius: 8px;
            }
            QPushButton:hover {
                border-color: #3b82f6;
                color: #ffffff;
                background-color: #18233c;
            }
        """)
        run_btn.clicked.connect(self.on_run_selected)
        layout.addWidget(run_btn)

        self.btn_evidence = QPushButton("📸 Evidence: ON")
        self.btn_evidence.setCursor(Qt.PointingHandCursor)
        self.btn_evidence.setStyleSheet("""
            QPushButton {
                background-color: rgba(16, 185, 129, 0.15);
                border: 1px solid #10b981;
                color: #34d399;
                font-weight: bold;
                font-size: 11px;
                padding: 6px 12px;
                border-radius: 6px;
            }
        """)
        self.btn_evidence.clicked.connect(self.toggle_evidence)
        layout.addWidget(self.btn_evidence)

        self.btn_top_report = QPushButton("📊 Report")
        self.btn_top_report.setCursor(Qt.PointingHandCursor)
        self.btn_top_report.setStyleSheet("""
            QPushButton {
                background-color: #131b2e;
                border: 1px solid #2a3a5e;
                color: #38bdf8;
                font-weight: bold;
                font-size: 11px;
                padding: 6px 12px;
                border-radius: 6px;
            }
            QPushButton:hover {
                border-color: #38bdf8;
                background-color: #1e293b;
            }
        """)
        self.btn_top_report.clicked.connect(self.open_latest_html_report)
        layout.addWidget(self.btn_top_report)

        browser_box = QFrame()
        browser_box.setStyleSheet("background-color: #131b2e; border: 1px solid #1e293b; border-radius: 8px; padding: 4px;")
        b_layout = QHBoxLayout(browser_box)
        b_layout.setContentsMargins(6, 2, 6, 2)
        b_layout.setSpacing(6)

        self.btn_edge = QPushButton("Edge")
        self.btn_edge.setCursor(Qt.PointingHandCursor)
        self.btn_edge.setStyleSheet("background-color: #1e293b; color: #38bdf8; font-weight: bold; border-radius: 4px; padding: 4px 8px; border: none;")
        self.btn_edge.clicked.connect(lambda: self.set_browser("msedge"))
        b_layout.addWidget(self.btn_edge)

        self.btn_chrome = QPushButton("Chrome")
        self.btn_chrome.setCursor(Qt.PointingHandCursor)
        self.btn_chrome.setStyleSheet("background-color: transparent; color: #64748b; font-weight: bold; border-radius: 4px; padding: 4px 8px; border: none;")
        self.btn_chrome.clicked.connect(lambda: self.set_browser("chrome"))
        b_layout.addWidget(self.btn_chrome)

        self.headless_btn = QPushButton("Headless: ON")
        self.headless_btn.setCursor(Qt.PointingHandCursor)
        self.headless_btn.setStyleSheet("background-color: transparent; color: #94a3b8; font-size: 11px; padding: 4px 6px; border: 1px solid #334155; border-radius: 4px;")
        self.headless_btn.clicked.connect(self.toggle_headless)
        b_layout.addWidget(self.headless_btn)

        self.device_combo_top = QComboBox()
        self.device_combo_top.addItems([
            "Desktop 1280x800",
            "Desktop 1920x1080",
            "iPhone 14 (390x844)",
            "Pixel 7 (412x915)",
            "iPad Pro (1024x1366)"
        ])
        self.device_combo_top.setStyleSheet("""
            QComboBox {
                background-color: transparent;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 2px 6px;
                color: #38bdf8;
                font-size: 11px;
                font-weight: bold;
            }
        """)
        cur_dev = self.settings.get("device", "Desktop 1280x800")
        self.device_combo_top.setCurrentText(cur_dev)
        self.device_combo_top.currentTextChanged.connect(self.on_device_changed)
        b_layout.addWidget(self.device_combo_top)

        layout.addWidget(browser_box)

        return bar

    def render_env_pills(self):
        while self.env_pill_box.count():
            item = self.env_pill_box.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        envs = self.test_data_mgr.get_environments()
        if self.current_env not in envs and envs:
            self.current_env = envs[0]
            self.test_data_mgr.set_active_environment(self.current_env)
        for env_name in envs:
            btn = self._make_env_pill(env_name, active=(env_name == self.current_env))
            self.env_pill_box.addWidget(btn)

    def _make_env_pill(self, env_name, active=False):
        btn = QPushButton(env_name)
        btn.setCursor(Qt.PointingHandCursor)
        if active:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(37, 99, 235, 0.2);
                    border: 1px solid #2563eb;
                    color: #60a5fa;
                    font-size: 11px;
                    font-weight: bold;
                    border-radius: 14px;
                    padding: 4px 12px;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: 1px solid #1e293b;
                    color: #64748b;
                    font-size: 11px;
                    font-weight: bold;
                    border-radius: 14px;
                    padding: 4px 12px;
                }
                QPushButton:hover {
                    color: #cbd5e1;
                    border-color: #334155;
                }
            """)
        btn.clicked.connect(lambda _, en=env_name: self.set_environment(en))
        return btn

    def set_environment(self, env_name):
        self.current_env = env_name
        self.test_data_mgr.set_active_environment(env_name)
        self.render_env_pills()
        self.append_log("INFO", f"Switched environment context to [{env_name}]")

    def quick_add_env(self):
        name, ok = QInputDialog.getText(self, "Add Environment", "New environment name (e.g. UAT, DEV, STAGING-2):")
        if ok and name.strip():
            clean_name = name.strip()
            if self.test_data_mgr.add_environment(clean_name):
                self.set_environment(clean_name)
                self.append_log("SUCCESS", f"Environment [{clean_name}] created and activated.")
            else:
                self.append_log("WARNING", f"Environment [{clean_name}] already exists.")

    def open_test_data_dialog(self):
        dlg = TestDataDialog(
            self.test_data_mgr,
            self.current_env,
            self.settings.get("claude_api_key", ""),
            self.settings.get("claude_model", ""),
            self
        )
        dlg.exec()
        self.render_env_pills()

    def set_browser(self, b_name):
        self.selected_browser = b_name
        if b_name == "msedge":
            self.btn_edge.setStyleSheet("background-color: #1e293b; color: #38bdf8; font-weight: bold; border-radius: 4px; padding: 4px 8px; border: none;")
            self.btn_chrome.setStyleSheet("background-color: transparent; color: #64748b; font-weight: bold; border-radius: 4px; padding: 4px 8px; border: none;")
        else:
            self.btn_chrome.setStyleSheet("background-color: #1e293b; color: #38bdf8; font-weight: bold; border-radius: 4px; padding: 4px 8px; border: none;")
            self.btn_edge.setStyleSheet("background-color: transparent; color: #64748b; font-weight: bold; border-radius: 4px; padding: 4px 8px; border: none;")
        self.append_log("INFO", f"Browser channel set to [{b_name}]")

    def toggle_headless(self):
        self.headless = not self.headless
        state_str = "ON" if self.headless else "OFF"
        color = "#94a3b8" if self.headless else "#38bdf8"
        self.headless_btn.setText(f"Headless: {state_str}")
        self.headless_btn.setStyleSheet(f"background-color: transparent; color: {color}; font-size: 11px; padding: 4px 6px; border: 1px solid #334155; border-radius: 4px;")
        self.append_log("INFO", f"Headless mode toggled {state_str}")

    def toggle_evidence(self):
        cur = self.settings.get("capture_evidence", True)
        self.settings["capture_evidence"] = not cur
        if self.settings["capture_evidence"]:
            fmt = self.settings.get("evidence_format", "both")
            self.btn_evidence.setText("📸 Evidence: ON")
            self.btn_evidence.setStyleSheet("""
                QPushButton {
                    background-color: rgba(16, 185, 129, 0.15);
                    border: 1px solid #10b981;
                    color: #34d399;
                    font-weight: bold;
                    font-size: 11px;
                    padding: 6px 12px;
                    border-radius: 6px;
                }
            """)
            self.append_log("INFO", f"Step Evidence capture ON (Format: {fmt})")
        else:
            self.btn_evidence.setText("📸 Evidence: OFF")
            self.btn_evidence.setStyleSheet("""
                QPushButton {
                    background-color: #131b2e;
                    border: 1px solid #334155;
                    color: #94a3b8;
                    font-weight: bold;
                    font-size: 11px;
                    padding: 6px 12px;
                    border-radius: 6px;
                }
            """)
            self.append_log("INFO", "Step Evidence capture OFF")

    def open_last_evidence_dir(self):
        target = getattr(self, "last_evidence_dir", None) or os.path.join(self.workspace_dir, "evidence")
        if os.path.exists(target):
            try:
                os.startfile(target)
            except Exception:
                pass

    def build_table_container(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 Search scenarios, tags, pages...")
        self.search_box.setStyleSheet("""
            QLineEdit {
                background-color: #0b1120;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 6px 12px;
                color: #ffffff;
                font-size: 12px;
                min-height: 32px;
            }
            QLineEdit:focus {
                border-color: #38bdf8;
            }
        """)
        self.search_box.textChanged.connect(self.apply_catalog_filters)
        filter_row.addWidget(self.search_box, 1)

        self.status_filter_combo = QComboBox()
        self.status_filter_combo.addItems(["All Statuses", "Passed Only", "Failed Only"])
        self.status_filter_combo.setStyleSheet("""
            QComboBox {
                background-color: #0b1120;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 4px 10px;
                color: #94a3b8;
                font-size: 11px;
                font-weight: bold;
                min-height: 32px;
            }
            QComboBox:hover {
                border-color: #38bdf8;
                color: #ffffff;
            }
        """)
        self.status_filter_combo.currentIndexChanged.connect(self.apply_catalog_filters)
        filter_row.addWidget(self.status_filter_combo)

        btn_all = QPushButton("☑ All")
        btn_all.setCursor(Qt.PointingHandCursor)
        btn_all.setStyleSheet("""
            QPushButton {
                background-color: #131b2e;
                border: 1px solid #2a3a5e;
                color: #93c5fd;
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: bold;
                min-height: 32px;
            }
            QPushButton:hover {
                border-color: #38bdf8;
                color: #ffffff;
            }
        """)
        btn_all.clicked.connect(lambda: self.set_bulk_selection(True))
        filter_row.addWidget(btn_all)

        btn_none = QPushButton("☐ None")
        btn_none.setCursor(Qt.PointingHandCursor)
        btn_none.setStyleSheet("""
            QPushButton {
                background-color: #131b2e;
                border: 1px solid #2a3a5e;
                color: #94a3b8;
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: bold;
                min-height: 32px;
            }
            QPushButton:hover {
                border-color: #38bdf8;
                color: #ffffff;
            }
        """)
        btn_none.clicked.connect(lambda: self.set_bulk_selection(False))
        filter_row.addWidget(btn_none)

        btn_failed = QPushButton("⚡ Failed Only")
        btn_failed.setCursor(Qt.PointingHandCursor)
        btn_failed.setStyleSheet("""
            QPushButton {
                background-color: rgba(239, 68, 68, 0.15);
                border: 1px solid #ef4444;
                color: #f87171;
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: bold;
                min-height: 32px;
            }
            QPushButton:hover {
                background-color: rgba(239, 68, 68, 0.3);
            }
        """)
        btn_failed.clicked.connect(self.select_failed_scenarios)
        filter_row.addWidget(btn_failed)

        layout.addLayout(filter_row)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["", "Scenario Name", "Tags", "Last Run", "Status", "Duration", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setItemDelegate(TablePillDelegate(self.table))

        self.table.setColumnWidth(0, 36)
        self.table.setColumnWidth(1, 280)
        self.table.setColumnWidth(2, 210)
        self.table.setColumnWidth(3, 130)
        self.table.setColumnWidth(4, 100)
        self.table.setColumnWidth(5, 80)
        self.table.setColumnWidth(6, 70)

        self.table.cellClicked.connect(self.on_table_cell_clicked)
        layout.addWidget(self.table)

        return container

    def apply_catalog_filters(self):
        query = self.search_box.text().strip().lower() if hasattr(self, "search_box") else ""
        s_filter = self.status_filter_combo.currentText() if hasattr(self, "status_filter_combo") else "All Statuses"
        for r in range(self.table.rowCount()):
            name_item = self.table.item(r, 1)
            tags_item = self.table.item(r, 2)
            status_item = self.table.item(r, 4)

            name_text = name_item.text().lower() if name_item else ""
            tags_text = tags_item.text().lower() if tags_item else ""
            status_text = status_item.text() if status_item else ""

            text_matches = (query in name_text) or (query in tags_text) or not query
            status_matches = True
            if s_filter == "Passed Only":
                status_matches = (status_text == "Passed")
            elif s_filter == "Failed Only":
                status_matches = (status_text == "Failed")

            self.table.setRowHidden(r, not (text_matches and status_matches))

    def set_bulk_selection(self, checked: bool):
        for r in range(self.table.rowCount()):
            if not self.table.isRowHidden(r):
                chk = self.table.item(r, 0)
                if chk:
                    chk.setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def select_failed_scenarios(self):
        for r in range(self.table.rowCount()):
            chk = self.table.item(r, 0)
            status_it = self.table.item(r, 4)
            if chk and status_it:
                is_failed = status_it.text() == "Failed"
                chk.setCheckState(Qt.Checked if is_failed else Qt.Unchecked)

    def build_inspector_panel(self):
        panel = QFrame()
        panel.setStyleSheet("background-color: #0b101b; border-left: 1px solid #1e293b;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header_layout = QHBoxLayout()
        inspector_title = QLabel("Test Inspector")
        inspector_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #ffffff;")
        header_layout.addWidget(inspector_title)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        self.steps_box = QFrame()
        self.steps_box.setStyleSheet("background-color: #131b2e; border: 1px solid #1e293b; border-radius: 8px;")
        steps_layout = QVBoxLayout(self.steps_box)
        steps_layout.setContentsMargins(10, 10, 10, 10)
        steps_layout.setSpacing(8)

        steps_hdr = QHBoxLayout()
        self.steps_title_lbl = QLabel("Flow Steps: User Login Flow")
        self.steps_title_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #cbd5e1;")
        steps_hdr.addWidget(self.steps_title_lbl, 1)

        self.btn_auto_heal = QPushButton("⚡ Auto-Heal")
        self.btn_auto_heal.setCursor(Qt.PointingHandCursor)
        self.btn_auto_heal.setStyleSheet("""
            QPushButton {
                background-color: rgba(168, 85, 247, 0.2);
                border: 1px solid #a855f7;
                color: #d8b4fe;
                font-size: 11px;
                font-weight: bold;
                border-radius: 6px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: rgba(168, 85, 247, 0.4);
                color: #ffffff;
            }
        """)
        self.btn_auto_heal.clicked.connect(self.auto_heal_with_claude)
        steps_hdr.addWidget(self.btn_auto_heal)

        self.btn_add_step = QPushButton("+ Add Step")
        self.btn_add_step.setCursor(Qt.PointingHandCursor)
        self.btn_add_step.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0284c7, stop:1 #2563eb);
                color: #ffffff;
                font-size: 11px;
                font-weight: bold;
                border-radius: 6px;
                padding: 4px 10px;
                border: none;
            }
            QPushButton:hover {
                background: #0369a1;
            }
        """)
        self.btn_add_step.clicked.connect(self.add_flow_step)
        steps_hdr.addWidget(self.btn_add_step)
        steps_layout.addLayout(steps_hdr)

        self.steps_scroll = QScrollArea()
        self.steps_scroll.setWidgetResizable(True)
        self.steps_scroll.setStyleSheet("background: transparent; border: none;")
        self.steps_container_widget = QWidget()
        self.steps_container_widget.setStyleSheet("background: transparent;")
        self.steps_container_layout = QVBoxLayout(self.steps_container_widget)
        self.steps_container_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_container_layout.setSpacing(6)
        self.steps_scroll.setWidget(self.steps_container_widget)
        steps_layout.addWidget(self.steps_scroll)

        layout.addWidget(self.steps_box, 1)

        toggle_row = QHBoxLayout()
        toggle_lbl = QLabel("Show Code")
        toggle_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #e2e8f0;")
        toggle_row.addWidget(toggle_lbl)
        toggle_row.addStretch()

        self.code_toggle = ToggleSwitch()
        self.code_toggle.stateChanged.connect(self.on_code_toggle)
        toggle_row.addWidget(self.code_toggle)
        layout.addLayout(toggle_row)

        self.code_viewer_frame = QFrame()
        self.code_viewer_frame.setStyleSheet("background-color: #0b1120; border: 1px solid #1e293b; border-radius: 8px;")
        self.code_viewer_frame.setVisible(False)
        code_layout = QVBoxLayout(self.code_viewer_frame)
        code_layout.setContentsMargins(8, 8, 8, 8)
        code_layout.setSpacing(6)

        code_hdr = QHBoxLayout()
        self.code_filename_lbl = QLabel("test_spec.py")
        self.code_filename_lbl.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: bold;")
        code_hdr.addWidget(self.code_filename_lbl)

        self.code_status_lbl = QLabel("[Saved]")
        self.code_status_lbl.setStyleSheet("color: #34d399; font-size: 11px; font-weight: bold; margin-left: 8px;")
        code_hdr.addWidget(self.code_status_lbl)

        code_hdr.addStretch()

        self.btn_claude_code = QPushButton("🤖 Claude Assistant")
        self.btn_claude_code.setCursor(Qt.PointingHandCursor)
        self.btn_claude_code.setStyleSheet("""
            QPushButton {
                background-color: rgba(139, 92, 246, 0.2);
                border: 1px solid #8b5cf6;
                color: #c084fc;
                font-size: 11px;
                font-weight: bold;
                border-radius: 4px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: rgba(139, 92, 246, 0.4);
                color: #ffffff;
            }
        """)
        self.btn_claude_code.clicked.connect(self.open_claude_code_assistant)
        code_hdr.addWidget(self.btn_claude_code)

        self.btn_save_code = QPushButton("💾 Save Code")
        self.btn_save_code.setCursor(Qt.PointingHandCursor)
        self.btn_save_code.setStyleSheet("background-color: #0284c7; color: #ffffff; font-size: 11px; font-weight: bold; border-radius: 4px; padding: 4px 10px; border: none;")
        self.btn_save_code.clicked.connect(self.save_current_code)
        code_hdr.addWidget(self.btn_save_code)

        self.btn_run_code = QPushButton("▶ Run Flow")
        self.btn_run_code.setCursor(Qt.PointingHandCursor)
        self.btn_run_code.setStyleSheet("background-color: #10b981; color: #ffffff; font-size: 11px; font-weight: bold; border-radius: 4px; padding: 4px 10px; border: none;")
        self.btn_run_code.clicked.connect(self.run_current_flow)
        code_hdr.addWidget(self.btn_run_code)

        copy_btn = QPushButton("📋 Copy")
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.setStyleSheet("background-color: #1e293b; color: #94a3b8; font-size: 11px; border-radius: 4px; padding: 4px 8px; border: 1px solid #334155;")
        copy_btn.clicked.connect(self.copy_code)
        code_hdr.addWidget(copy_btn)
        code_layout.addLayout(code_hdr)

        self.code_edit = CodeEditor()
        self.code_edit.textChanged.connect(self.on_code_text_changed)
        self.highlighter = PythonHighlighter(self.code_edit.document())
        code_layout.addWidget(self.code_edit)

        layout.addWidget(self.code_viewer_frame, 1)

        logs_frame = QFrame()
        logs_frame.setFixedHeight(160)
        logs_frame.setStyleSheet("background-color: #090e18; border: 1px solid #1e293b; border-radius: 8px;")
        logs_layout = QVBoxLayout(logs_frame)
        logs_layout.setContentsMargins(10, 8, 10, 8)
        logs_layout.setSpacing(4)

        logs_hdr = QHBoxLayout()
        logs_title = QLabel("Terminal Logs")
        logs_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #cbd5e1;")
        logs_hdr.addWidget(logs_title)
        logs_hdr.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet("background: transparent; border: none; color: #64748b; font-size: 10px;")
        clear_btn.clicked.connect(lambda: self.log_feed.clear())
        logs_hdr.addWidget(clear_btn)
        logs_layout.addLayout(logs_hdr)

        self.log_feed = QPlainTextEdit()
        self.log_feed.setReadOnly(True)
        self.log_feed.setFont(QFont("Consolas", 10))
        self.log_feed.setStyleSheet("""
            QPlainTextEdit {
                background-color: #070b13;
                border: 1px solid #1e293b;
                border-radius: 6px;
                color: #e2e8f0;
                padding: 6px;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
            }
        """)
        logs_layout.addWidget(self.log_feed)

        layout.addWidget(logs_frame)

        self.append_log("INFO", "Conduit Pure Python Desktop Engine initialized.")
        return panel

    def build_bottom_bar(self):
        bar = QFrame()
        bar.setFixedHeight(48)
        bar.setStyleSheet("background-color: #0d1527; border-top: 1px solid #1e293b;")
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(4)

        status_box = QHBoxLayout()
        self.status_lbl = QLabel("Ready - 7 scenario(s) loaded")
        self.status_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
        status_box.addWidget(self.status_lbl)
        status_box.addStretch()

        self.btn_open_evidence = QPushButton("📁 Open Evidence Folder")
        self.btn_open_evidence.setCursor(Qt.PointingHandCursor)
        self.btn_open_evidence.setVisible(False)
        self.btn_open_evidence.setStyleSheet("""
            QPushButton {
                background-color: #131b2e;
                border: 1px solid #2a3a5e;
                color: #38bdf8;
                font-size: 11px;
                font-weight: bold;
                padding: 2px 10px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1e293b;
                border-color: #38bdf8;
                color: #ffffff;
            }
        """)
        self.btn_open_evidence.clicked.connect(self.open_last_evidence_dir)
        status_box.addWidget(self.btn_open_evidence)

        self.btn_open_report = QPushButton("📊 View HTML Report")
        self.btn_open_report.setCursor(Qt.PointingHandCursor)
        self.btn_open_report.setVisible(bool(getattr(self, "last_html_report", "")))
        self.btn_open_report.setStyleSheet("""
            QPushButton {
                background-color: #131b2e;
                border: 1px solid #2a3a5e;
                color: #34d399;
                font-size: 11px;
                font-weight: bold;
                padding: 2px 10px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1e293b;
                border-color: #34d399;
                color: #ffffff;
            }
        """)
        self.btn_open_report.clicked.connect(self.open_latest_html_report)
        status_box.addWidget(self.btn_open_report)
        layout.addLayout(status_box)

        self.pbar = QProgressBar()
        self.pbar.setFixedHeight(4)
        self.pbar.setTextVisible(False)
        self.pbar.setValue(0)
        self.pbar.setStyleSheet("""
            QProgressBar {
                background-color: #1e293b;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #38bdf8, stop:1 #2563eb);
                border-radius: 2px;
            }
        """)
        layout.addWidget(self.pbar)

        return bar

    def load_scenarios(self):
        checked_ids = set()
        has_existing = self.table.rowCount() > 0
        if has_existing:
            for r in range(self.table.rowCount()):
                chk = self.table.item(r, 0)
                name_it = self.table.item(r, 1)
                if chk and name_it and chk.checkState() == Qt.Checked:
                    sid = name_it.data(Qt.UserRole)
                    if sid:
                        checked_ids.add(sid)

        current_selected = getattr(self, "selected_scenario_id", None)
        scenarios = self.catalog.get_all_scenarios()
        self.table.setRowCount(len(scenarios))
        self.status_lbl.setText(f"Ready - {len(scenarios)} scenario(s) loaded")

        for row, sc in enumerate(scenarios):
            self.table.setRowHeight(row, 44)

            sid = sc.get("id")
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            if has_existing:
                chk_item.setCheckState(Qt.Checked if sid in checked_ids else Qt.Unchecked)
            else:
                chk_item.setCheckState(Qt.Checked if row < 3 else Qt.Unchecked)
            self.table.setItem(row, 0, chk_item)

            name_item = QTableWidgetItem(sc.get("name", ""))
            name_item.setData(Qt.UserRole, sid)
            name_item.setForeground(QColor("#f8fafc"))
            self.table.setItem(row, 1, name_item)

            tags_str = " ".join(sc.get("tags", []))
            tags_item = QTableWidgetItem(tags_str)
            self.table.setItem(row, 2, tags_item)

            exec_item = QTableWidgetItem(sc.get("last_execution", ""))
            exec_item.setForeground(QColor("#94a3b8"))
            self.table.setItem(row, 3, exec_item)

            status_item = QTableWidgetItem(sc.get("status", "Passed"))
            self.table.setItem(row, 4, status_item)

            dur_item = QTableWidgetItem(sc.get("duration", "--"))
            dur_item.setForeground(QColor("#94a3b8"))
            self.table.setItem(row, 5, dur_item)

            actions_widget = QWidget()
            actions_widget.setStyleSheet("background: transparent;")
            act_layout = QHBoxLayout(actions_widget)
            act_layout.setContentsMargins(4, 2, 4, 2)
            act_layout.setSpacing(6)

            play_btn = QPushButton("▶")
            play_btn.setFixedSize(22, 22)
            play_btn.setCursor(Qt.PointingHandCursor)
            play_btn.setStyleSheet("background: transparent; color: #94a3b8; font-size: 11px; border: none;")
            play_btn.clicked.connect(lambda _, s_id=sid: self.run_single_test(s_id))
            act_layout.addWidget(play_btn)

            more_lbl = QLabel("•••")
            more_lbl.setStyleSheet("color: #64748b; font-size: 10px;")
            act_layout.addWidget(more_lbl)
            act_layout.addStretch()

            self.table.setCellWidget(row, 6, actions_widget)

        if scenarios:
            target_id = current_selected if current_selected and any(s.get("id") == current_selected for s in scenarios) else scenarios[0].get("id")
            self.select_scenario(target_id)

    def on_table_cell_clicked(self, row, col):
        name_item = self.table.item(row, 1)
        if name_item:
            s_id = name_item.data(Qt.UserRole)
            self.select_scenario(s_id)

    def select_scenario(self, scenario_id):
        self.selected_scenario_id = scenario_id
        sc = self.catalog.get_scenario(scenario_id)
        if not sc:
            return

        self.steps_title_lbl.setText(f"Flow Steps: {sc.get('name')}")

        while self.steps_container_layout.count():
            item = self.steps_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        steps = sc.get("steps", [])
        for idx, st in enumerate(steps):
            step_card = QFrame()
            step_card.setStyleSheet("""
                QFrame {
                    background-color: #0b1120;
                    border: 1px solid #1e293b;
                    border-radius: 8px;
                }
                QFrame:hover {
                    border-color: #38bdf8;
                    background-color: #0f182c;
                }
            """)
            card_layout = QHBoxLayout(step_card)
            card_layout.setContentsMargins(10, 8, 10, 8)
            card_layout.setSpacing(8)

            num_lbl = QLabel(str(idx + 1))
            num_lbl.setFixedSize(22, 22)
            num_lbl.setAlignment(Qt.AlignCenter)
            num_lbl.setStyleSheet("""
                background-color: rgba(56, 189, 248, 0.15);
                color: #38bdf8;
                font-size: 11px;
                font-weight: bold;
                border-radius: 11px;
                border: 1px solid rgba(56, 189, 248, 0.4);
            """)
            card_layout.addWidget(num_lbl)

            act_type = (st.get("action") or "").upper()
            if not act_type:
                code_text = st.get("code", "").lower()
                if "goto" in code_text:
                    act_type = "NAVIGATE"
                elif "click" in code_text:
                    act_type = "CLICK"
                elif "fill" in code_text:
                    act_type = "FILL"
                elif "assert" in code_text or "expect" in code_text:
                    act_type = "ASSERT"
                elif "wait" in code_text:
                    act_type = "WAIT"
                elif "screenshot" in code_text:
                    act_type = "SCREENSHOT"
                else:
                    act_type = "STEP"

            act_badge_colors = {
                "CLICK": ("rgba(37,99,235,0.2)", "#60a5fa"),
                "FILL": ("rgba(168,85,247,0.2)", "#c084fc"),
                "NAVIGATE": ("rgba(6,182,212,0.2)", "#22d3ee"),
                "ASSERT": ("rgba(16,185,129,0.2)", "#34d399"),
                "WAIT": ("rgba(245,158,11,0.2)", "#fbbf24"),
                "SCREENSHOT": ("rgba(236,72,153,0.2)", "#f472b6"),
                "PRESS": ("rgba(99,102,241,0.2)", "#818cf8"),
                "API_REQUEST": ("rgba(249,115,22,0.2)", "#fb923c")
            }
            bg, fg = act_badge_colors.get(act_type, ("rgba(100,116,139,0.2)", "#94a3b8"))
            act_badge = QLabel(act_type)
            act_badge.setStyleSheet(f"background-color: {bg}; color: {fg}; font-size: 9px; font-weight: bold; padding: 2px 6px; border-radius: 4px; border: 1px solid {fg};")
            card_layout.addWidget(act_badge)

            desc_text = st.get("human_description", f"Step {idx + 1}")
            desc_lbl = QLabel(desc_text)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("color: #f8fafc; font-size: 12px; font-weight: 500; background: transparent; border: none;")
            card_layout.addWidget(desc_lbl, 1)

            btn_box = QHBoxLayout()
            btn_box.setSpacing(4)

            btn_up = QPushButton("⬆")
            btn_up.setFixedSize(22, 22)
            btn_up.setCursor(Qt.PointingHandCursor)
            btn_up.setStyleSheet("background: transparent; color: #94a3b8; font-size: 11px; border: 1px solid #1e293b; border-radius: 4px;")
            btn_up.setEnabled(idx > 0)
            btn_up.clicked.connect(lambda _, i=idx: self.move_flow_step(i, -1))
            btn_box.addWidget(btn_up)

            btn_down = QPushButton("⬇")
            btn_down.setFixedSize(22, 22)
            btn_down.setCursor(Qt.PointingHandCursor)
            btn_down.setStyleSheet("background: transparent; color: #94a3b8; font-size: 11px; border: 1px solid #1e293b; border-radius: 4px;")
            btn_down.setEnabled(idx < len(steps) - 1)
            btn_down.clicked.connect(lambda _, i=idx: self.move_flow_step(i, 1))
            btn_box.addWidget(btn_down)

            btn_edit = QPushButton("✏️")
            btn_edit.setFixedSize(22, 22)
            btn_edit.setCursor(Qt.PointingHandCursor)
            btn_edit.setStyleSheet("background: transparent; color: #38bdf8; font-size: 11px; border: 1px solid #1e293b; border-radius: 4px;")
            btn_edit.clicked.connect(lambda _, i=idx: self.edit_flow_step(i))
            btn_box.addWidget(btn_edit)

            btn_del = QPushButton("🗑️")
            btn_del.setFixedSize(22, 22)
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setStyleSheet("background: transparent; color: #f87171; font-size: 11px; border: 1px solid #1e293b; border-radius: 4px;")
            btn_del.clicked.connect(lambda _, i=idx: self.delete_flow_step(i))
            btn_box.addWidget(btn_del)

            card_layout.addLayout(btn_box)
            self.steps_container_layout.addWidget(step_card)

        self.steps_container_layout.addStretch()

        self._loading_code = True
        self.code_filename_lbl.setText(sc.get("file_name", "test_spec.py"))
        self.code_edit.setPlainText(sc.get("code", ""))
        self.code_status_lbl.setText("[Saved]")
        self.code_status_lbl.setStyleSheet("color: #34d399; font-size: 11px; font-weight: bold; margin-left: 8px;")
        self._loading_code = False

    def on_code_text_changed(self):
        if not getattr(self, "_loading_code", False):
            self.code_status_lbl.setText("● Modified")
            self.code_status_lbl.setStyleSheet("color: #fbbf24; font-size: 11px; font-weight: bold; margin-left: 8px;")

    def save_current_code(self):
        if not getattr(self, "selected_scenario_id", None):
            return
        code = self.code_edit.toPlainText()
        try:
            ast.parse(code)
        except Exception as e:
            self.code_status_lbl.setText("Syntax Error")
            self.code_status_lbl.setStyleSheet("color: #f87171; font-size: 11px; font-weight: bold; margin-left: 8px;")
            self.append_log("ERROR", f"Syntax error in code: {e}")
            return

        sc = self.catalog.get_scenario(self.selected_scenario_id)
        if not sc:
            return
        sc["code"] = code
        try:
            parsed = self.ast_engine.reverse_parse_test_file(code)
            if parsed.get("steps"):
                sc["steps"] = parsed["steps"]
        except Exception:
            pass

        self.catalog.add_or_update_scenario(sc)
        self.code_status_lbl.setText("[Saved]")
        self.code_status_lbl.setStyleSheet("color: #34d399; font-size: 11px; font-weight: bold; margin-left: 8px;")
        self.append_log("SUCCESS", f"Saved code for '{sc.get('name')}' to disk and synchronized steps.")
        cur_id = self.selected_scenario_id
        self.select_scenario(cur_id)

    def add_flow_step(self):
        if not getattr(self, "selected_scenario_id", None):
            return
        sc = self.catalog.get_scenario(self.selected_scenario_id)
        if not sc:
            return
        dlg = StepEditorDialog(parent=self)
        if dlg.exec() == QDialog.Accepted:
            new_step = dlg.get_step_data()
            if "steps" not in sc:
                sc["steps"] = []
            sc["steps"].append(new_step)
            self._sync_scenario_steps_and_save(sc)
            self.append_log("SUCCESS", f"Added step: {new_step.get('human_description')}")

    def edit_flow_step(self, step_idx: int):
        if not getattr(self, "selected_scenario_id", None):
            return
        sc = self.catalog.get_scenario(self.selected_scenario_id)
        if not sc or "steps" not in sc or step_idx >= len(sc["steps"]):
            return
        st = sc["steps"][step_idx]
        dlg = StepEditorDialog(step_data=st, parent=self)
        if dlg.exec() == QDialog.Accepted:
            sc["steps"][step_idx] = dlg.get_step_data()
            self._sync_scenario_steps_and_save(sc)
            self.append_log("SUCCESS", f"Updated step {step_idx + 1}")

    def move_flow_step(self, step_idx: int, direction: int):
        if not getattr(self, "selected_scenario_id", None):
            return
        sc = self.catalog.get_scenario(self.selected_scenario_id)
        if not sc or "steps" not in sc:
            return
        steps = sc["steps"]
        target = step_idx + direction
        if 0 <= target < len(steps):
            steps[step_idx], steps[target] = steps[target], steps[step_idx]
            self._sync_scenario_steps_and_save(sc)

    def delete_flow_step(self, step_idx: int):
        if not getattr(self, "selected_scenario_id", None):
            return
        sc = self.catalog.get_scenario(self.selected_scenario_id)
        if not sc or "steps" not in sc or step_idx >= len(sc["steps"]):
            return
        deleted = sc["steps"].pop(step_idx)
        self._sync_scenario_steps_and_save(sc)
        self.append_log("INFO", f"Deleted step {step_idx + 1}: {deleted.get('human_description', '')}")

    def _sync_scenario_steps_and_save(self, sc: dict):
        try:
            res = self.ast_engine.reconstruct_scenario(sc)
            sc["code"] = res["test_code"]
            sc["steps"] = res["steps"]
            if res.get("pages"):
                sc["pages"] = res["pages"]
                for p in res["pages"]:
                    p_file = os.path.join(self.catalog.pages_dir, p["file_name"])
                    with open(p_file, "w", encoding="utf-8") as pf:
                        pf.write(p["code"])

            test_file = os.path.join(self.catalog.tests_dir, sc.get("file_name", f"test_{sc.get('id')}.py"))
            with open(test_file, "w", encoding="utf-8") as tf:
                tf.write(res["test_code"])

            self.catalog.add_or_update_scenario(sc)
            self.select_scenario(sc["id"])
        except Exception as ex:
            self.catalog.add_or_update_scenario(sc)
            self.select_scenario(sc["id"])
            self.append_log("WARNING", f"Step synchronized with warning: {ex}")

    def open_latest_html_report(self):
        report_path = getattr(self, "last_html_report", None) or os.path.join(self.workspace_dir, "reports", "latest_report.html")
        if os.path.exists(report_path):
            abs_url = f"file:///{os.path.abspath(report_path).replace('\\', '/')}"
            webbrowser.open(abs_url)
            self.append_log("SUCCESS", f"Opened HTML execution report: {report_path}")
        else:
            self.append_log("WARNING", "No execution report found yet. Run tests to generate a report.")

    def on_device_changed(self, dev_name: str):
        self.settings["device"] = dev_name
        self.append_log("INFO", f"Device emulation preset set to [{dev_name}]")

    def open_claude_flow_dialog(self):
        cur_url = self.settings.get("base_url", "https://demo.playwright.dev/todomvc/")
        dlg = ClaudePromptDialog(self.claude_engine, base_url=cur_url, parent=self)
        if dlg.exec() == QDialog.Accepted:
            sc = dlg.get_generated_scenario()
            if sc:
                self.catalog.add_or_update_scenario(sc)
                self.load_scenarios()
                self.select_scenario(sc["id"])
                self.append_log("SUCCESS", f"Claude synthesized flow '{sc.get('name')}' added to catalog.")

    def auto_heal_with_claude(self):
        if not getattr(self, "selected_scenario_id", None):
            self.append_log("WARNING", "Please select a scenario to heal.")
            return
        sc = self.catalog.get_scenario(self.selected_scenario_id)
        if not sc or not sc.get("steps"):
            self.append_log("WARNING", "Selected scenario has no steps to heal.")
            return

        failed_step = sc["steps"][-1]
        for st in sc["steps"]:
            if "fail" in st.get("human_description", "").lower() or "error" in st.get("human_description", "").lower():
                failed_step = st
                break

        err_msg = "Playwright TimeoutError: element not found or detached from DOM within 5000ms"
        dlg = ClaudeHealDialog(self.claude_engine, sc, failed_step=failed_step, error_message=err_msg, parent=self)
        if dlg.exec() == QDialog.Accepted:
            healed = dlg.get_healed_data()
            if healed and "healed_step" in healed:
                step_idx = sc["steps"].index(failed_step) if failed_step in sc["steps"] else (len(sc["steps"]) - 1)
                sc["steps"][step_idx] = healed["healed_step"]
                sc["status"] = "Passed"
                self._sync_scenario_steps_and_save(sc)
                self.append_log("SUCCESS", f"Autonomous Self-Healing applied to '{sc.get('name')}': {healed.get('healing_strategy', '')}")

    def open_claude_code_assistant(self):
        code = self.code_edit.toPlainText()
        if not code.strip():
            self.append_log("WARNING", "No code in editor to analyze.")
            return
        dlg = ClaudeCodeDialog(self.claude_engine, code, parent=self)
        if dlg.exec() == QDialog.Accepted:
            improved = dlg.get_optimized_code()
            if improved:
                self.code_edit.setPlainText(improved)
                self.append_log("SUCCESS", "Applied Claude optimized code to editor.")

    def run_current_flow(self):
        if not getattr(self, "selected_scenario_id", None):
            return
        self.save_current_code()
        self.run_single_test(self.selected_scenario_id)

    def on_code_toggle(self, state):
        show = state == Qt.Checked.value or state is True or state == 2
        self.code_viewer_frame.setVisible(show)
        self.steps_box.setVisible(not show)

    def copy_code(self):
        text = self.code_edit.toPlainText()
        QApplication.clipboard().setText(text)
        self.append_log("INFO", "Synthesized Python code copied to clipboard.")

    def append_log(self, level: str, msg: str):
        color = "#38bdf8"
        if level == "ERROR":
            color = "#f87171"
        elif level == "SUCCESS":
            color = "#34d399"
        elif level == "WARNING":
            color = "#fbbf24"
        timestamp = time.strftime("%H:%M:%S")
        self.log_feed.appendHtml(
            f"<div style='margin-bottom: 2px; line-height: 1.4;'>"
            f"<span style='color:#64748b; font-size:11px;'>{timestamp}</span> "
            f"<span style='color:{color}; font-weight:bold; font-size:11px;'>[{level}]</span> "
            f"<span style='color:#f1f5f9; font-size:11px;'>{msg}</span>"
            f"</div>"
        )

    def update_progress(self, data: dict):
        pct = data.get("percentage", 0)
        self.pbar.setValue(pct)
        status_text = data.get("status_text", "")
        if status_text:
            self.status_lbl.setText(status_text)

    def on_execution_finished(self, result: dict):
        status = result.get("status", "Passed")
        dur = f"{result.get('duration', 0)}s"
        self.load_scenarios()
        ev_dirs = result.get("evidence_dirs", [])
        reports = result.get("evidence_reports", [])
        html_rep = result.get("html_report", "")
        if ev_dirs:
            self.last_evidence_dir = ev_dirs[-1]
            self.btn_open_evidence.setVisible(True)
            self.append_log("SUCCESS", f"Step Evidence recorded: {self.last_evidence_dir}")
        if reports:
            self.last_docx_report = reports[-1]
            self.append_log("SUCCESS", f"Word Evidence Report created: {self.last_docx_report}")
        if html_rep and os.path.exists(html_rep):
            self.last_html_report = html_rep
            self.btn_open_report.setVisible(True)
            self.append_log("SUCCESS", f"Interactive HTML Report generated: {html_rep}")

    def on_run_selected(self):
        selected_ids = []
        for r in range(self.table.rowCount()):
            chk = self.table.item(r, 0)
            if chk and chk.checkState() == Qt.Checked:
                name_item = self.table.item(r, 1)
                if name_item:
                    selected_ids.append(name_item.data(Qt.UserRole))

        if not selected_ids:
            self.append_log("ERROR", "Please check at least one scenario to run.")
            return

        self.run_scenarios_by_ids(selected_ids)

    def run_single_test(self, scenario_id):
        self.select_scenario(scenario_id)
        self.run_scenarios_by_ids([scenario_id])

    def run_scenarios_by_ids(self, scenario_ids: List[str]):
        test_files = []
        for s_id in scenario_ids:
            sc = self.catalog.get_scenario(s_id)
            if sc and sc.get("file_name"):
                p = os.path.join(self.catalog.tests_dir, sc["file_name"])
                if os.path.exists(p):
                    test_files.append(p)

        if not test_files:
            self.append_log("ERROR", "No test files found on disk for selected scenarios.")
            return

        self.status_lbl.setText(f"Running {len(test_files)} scenario(s)...")
        self.pbar.setValue(10)

        def _on_log(level, msg):
            self.bridge.log_signal.emit(level, msg)

        def _on_prog(data):
            self.bridge.progress_signal.emit(data)

        def _on_fin(res):
            for s_id in scenario_ids:
                self.catalog.update_execution_result(s_id, res.get("status", "Passed"), f"{res.get('duration', 0)}s")
            self.bridge.finished_signal.emit(res)

        capture_ev = self.settings.get("capture_evidence", True)
        ev_fmt = self.settings.get("evidence_format", "both")
        retries = self.settings.get("retries", 0)
        device = self.settings.get("device", "Desktop 1280x800")

        self.runner.run_tests_async(
            test_file_paths=test_files,
            browser=self.selected_browser,
            headless=self.headless,
            env=self.current_env,
            capture_evidence=capture_ev,
            evidence_format=ev_fmt,
            retries=retries,
            device=device,
            on_log=_on_log,
            on_progress=_on_prog,
            on_finished=_on_fin
        )

    def on_record_clicked(self):
        if self.recorder and self.recorder.is_recording:
            self.append_log("INFO", "Stopping active recording and synthesizing Page Objects...")
            self.status_lbl.setText("Stopping recording session...")
            self.recorder.stop_recording()
            return

        dlg = RecordDialog(self)
        if dlg.exec() == QDialog.Accepted:
            name, url, tags = dlg.get_data()
            self._current_recording_meta = {
                "name": name,
                "url": url,
                "tags": tags,
                "browser": self.selected_browser
            }

            self.btn_record_flow.setText("■ Stop & Save Recording")
            self.btn_record_flow.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #dc2626, stop:1 #ef4444);
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 13px;
                    padding: 8px 18px;
                    border-radius: 8px;
                    border: none;
                }
                QPushButton:hover {
                    background: #b91c1c;
                }
            """)
            self.status_lbl.setText(f"● Recording '{name}' in browser... Click 'Stop & Save Recording' or close browser when done")
            self.append_log("INFO", f"Launching browser recorder for '{name}' on {url}...")

            def _on_action(step_data):
                self.bridge.action_recorded_signal.emit(step_data)

            def _on_finished(actions):
                self.bridge.recording_finished_signal.emit(actions)

            self.recorder = BrowserRecorder(
                on_action_recorded=_on_action,
                on_recording_finished=_on_finished
            )
            self.recorder.start_recording(initial_url=url, browser_channel=self.selected_browser)
            self.append_log("INFO", "Recording active in browser. Perform actions or Alt+Click to assert.")

    def on_action_recorded(self, step_data: dict):
        desc = step_data.get("human_description", "")
        self.append_log("INFO", f"Recorded step: {desc}")

    def on_recording_completed(self, actions: list):
        self.btn_record_flow.setText("● Record New Flow")
        self.btn_record_flow.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0284c7, stop:1 #2563eb);
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 18px;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0369a1, stop:1 #1d4ed8);
            }
        """)

        meta = self._current_recording_meta or {}
        scenario_name = meta.get("name", "Recorded Scenario")
        tags = meta.get("tags", ["@smoke"])

        self.append_log("INFO", f"Synthesizing Page Object Model and Pytest spec for {len(actions)} recorded action(s)...")

        synth_result = self.ast_engine.synthesize_pom_and_test(
            scenario_name=scenario_name,
            tags=tags,
            actions=actions
        )

        new_id = f"sc_{os.urandom(4).hex()}"
        new_scenario = {
            "id": new_id,
            "name": scenario_name,
            "tags": tags,
            "last_execution": "Recorded just now",
            "status": "Passed",
            "duration": "--",
            "file_name": synth_result["file_name"],
            "steps": synth_result["steps"],
            "code": synth_result["test_code"],
            "pages": synth_result["pages"]
        }

        self.catalog.add_or_update_scenario(new_scenario)
        self.load_scenarios()
        self.select_scenario(new_id)

        self.status_lbl.setText(f"Ready - Scenario '{scenario_name}' synthesized and ready to run")
        self.append_log("SUCCESS", f"Synthesized Page Objects and scenario '{scenario_name}' ({len(actions)} steps). Added to Test Catalog!")
