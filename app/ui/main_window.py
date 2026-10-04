import os
import sys
import re
import time
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
from app.core.recorder import BrowserRecorder
from app.core.runner import TestRunner
from app.core.test_data_manager import TestDataManager


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


class TestDataDialog(QDialog):
    def __init__(self, test_data_mgr: TestDataManager, current_env: str = "QA", parent=None):
        super().__init__(parent)
        self.mgr = test_data_mgr
        self.current_env = current_env
        self.scraped_data_cache = {}
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
            "evidence_format": "both"
        }

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
            self.set_environment(self.settings.get("env", "QA"))
            self.set_browser(self.settings.get("browser", "msedge"))
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
        dlg = TestDataDialog(self.test_data_mgr, self.current_env, self)
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
        search_box = QLineEdit()
        search_box.setPlaceholderText("Search flows, tags, pages...")
        search_box.setStyleSheet("""
            QLineEdit {
                background-color: #0b1120;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 6px 12px;
                color: #ffffff;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #38bdf8;
            }
        """)
        search_box.textChanged.connect(self.filter_table)
        filter_row.addWidget(search_box, 1)

        filter_row.addStretch()
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

    def filter_table(self, query: str):
        q = query.strip().lower()
        for r in range(self.table.rowCount()):
            name_item = self.table.item(r, 1)
            tags_item = self.table.item(r, 2)
            name_text = name_item.text().lower() if name_item else ""
            tags_text = tags_item.text().lower() if tags_item else ""
            matches = (q in name_text) or (q in tags_text)
            self.table.setRowHidden(r, not matches)

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

        self.steps_title_lbl = QLabel("Flow Steps: User Login Flow")
        self.steps_title_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #cbd5e1;")
        steps_layout.addWidget(self.steps_title_lbl)

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
            card_layout.setSpacing(10)

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

            desc_text = st.get("human_description", f"Step {idx + 1}")
            desc_lbl = QLabel(desc_text)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("color: #f8fafc; font-size: 12px; font-weight: 500; background: transparent; border: none;")
            card_layout.addWidget(desc_lbl, 1)

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
        if ev_dirs:
            self.last_evidence_dir = ev_dirs[-1]
            self.btn_open_evidence.setVisible(True)
            self.append_log("SUCCESS", f"Step Evidence recorded: {self.last_evidence_dir}")
        if reports:
            self.last_docx_report = reports[-1]
            self.append_log("SUCCESS", f"Word Evidence Report created: {self.last_docx_report}")

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

        self.runner.run_tests_async(
            test_file_paths=test_files,
            browser=self.selected_browser,
            headless=self.headless,
            env=self.current_env,
            capture_evidence=capture_ev,
            evidence_format=ev_fmt,
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
