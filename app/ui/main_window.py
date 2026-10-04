import os
import sys
import re
import time
from typing import List, Dict, Any

from PySide6.QtCore import (
    Qt, QRect, QRectF, QSize, QPoint, Signal, QObject, QPropertyAnimation, Property
)
from PySide6.QtGui import (
    QColor, QPainter, QBrush, QPen, QFont, QTextCharFormat, QSyntaxHighlighter
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QStyledItemDelegate, QPlainTextEdit, QScrollArea, QFrame, QDialog,
    QLineEdit, QCheckBox, QProgressBar, QSplitter, QSizePolicy, QComboBox, QStyle
)

from app.core.catalog_manager import CatalogManager
from app.core.ast_normalizer import ASTNormalizer
from app.core.recorder import BrowserRecorder
from app.core.runner import TestRunner


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
    def __init__(self, current_settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Conduit Settings")
        self.setFixedSize(490, 460)
        self.settings_data = dict(current_settings)
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
                padding: 8px 12px;
                color: #ffffff;
                font-size: 13px;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #38bdf8;
            }
            QCheckBox {
                color: #f1f5f9;
                font-size: 13px;
                font-weight: 500;
                spacing: 8px;
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
            QPushButton#btnSave {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0284c7, stop:1 #2563eb);
                color: white;
                font-weight: bold;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 13px;
                border: none;
            }
            QPushButton#btnSave:hover {
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

        title = QLabel("Framework & Execution Settings")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

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
        self.env_combo.addItems(["QA", "Staging", "Prod"])
        self.env_combo.setCurrentText(self.settings_data.get("env", "QA"))
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

        layout.addStretch()

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
        layout.addLayout(btn_box)

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


class ConduitMainWindow(QMainWindow):
    def __init__(self, workspace_dir: str):
        super().__init__()
        self.workspace_dir = workspace_dir
        self.catalog = CatalogManager(workspace_dir)
        self.ast_engine = ASTNormalizer()
        self.runner = TestRunner(workspace_dir)
        self.recorder = None
        self._current_recording_meta = {}

        self.settings = {
            "browser": "msedge",
            "base_url": "https://demo.playwright.dev/todomvc/",
            "env": "QA",
            "timeout": 5000,
            "headless": True,
            "record_traces": True
        }

        self.current_env = "QA"
        self.selected_browser = "msedge"
        self.headless = True
        self.selected_scenario_id = "sc_001"

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
        dlg = SettingsDialog(self.settings, self)
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

        env_box = QHBoxLayout()
        env_box.setSpacing(6)
        self.env_qa_btn = self._make_env_pill("QA", active=True)
        self.env_stage_btn = self._make_env_pill("Staging")
        self.env_prod_btn = self._make_env_pill("Prod")

        env_box.addWidget(self.env_qa_btn)
        env_box.addWidget(self.env_stage_btn)
        env_box.addWidget(self.env_prod_btn)
        layout.addLayout(env_box)

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
        btn.clicked.connect(lambda: self.set_environment(env_name))
        return btn

    def set_environment(self, env_name):
        self.current_env = env_name
        for name, b in [("QA", self.env_qa_btn), ("Staging", self.env_stage_btn), ("Prod", self.env_prod_btn)]:
            if name == env_name:
                b.setStyleSheet("background-color: rgba(37, 99, 235, 0.2); border: 1px solid #2563eb; color: #60a5fa; font-size: 11px; font-weight: bold; border-radius: 14px; padding: 4px 12px;")
            else:
                b.setStyleSheet("background-color: transparent; border: 1px solid #1e293b; color: #64748b; font-size: 11px; font-weight: bold; border-radius: 14px; padding: 4px 12px;")
        self.append_log("INFO", f"Switched environment context to [{env_name}]")

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
        self.code_filename_lbl = QLabel("login_page.py")
        self.code_filename_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        code_hdr.addWidget(self.code_filename_lbl)
        code_hdr.addStretch()

        copy_btn = QPushButton("Copy")
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.setStyleSheet("background-color: #1e293b; color: #94a3b8; font-size: 10px; border-radius: 4px; padding: 2px 8px; border: none;")
        copy_btn.clicked.connect(self.copy_code)
        code_hdr.addWidget(copy_btn)
        code_layout.addLayout(code_hdr)

        self.code_edit = QPlainTextEdit()
        self.code_edit.setReadOnly(True)
        self.code_edit.setFont(QFont("Consolas", 10))
        self.code_edit.setStyleSheet("background-color: transparent; border: none; color: #93c5fd;")
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
        scenarios = self.catalog.get_all_scenarios()
        self.table.setRowCount(len(scenarios))
        self.status_lbl.setText(f"Ready - {len(scenarios)} scenario(s) loaded")

        for row, sc in enumerate(scenarios):
            self.table.setRowHeight(row, 44)

            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk_item.setCheckState(Qt.Checked if row < 3 else Qt.Unchecked)
            self.table.setItem(row, 0, chk_item)

            name_item = QTableWidgetItem(sc.get("name", ""))
            name_item.setData(Qt.UserRole, sc.get("id"))
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
            s_id = sc.get("id")
            play_btn.clicked.connect(lambda _, sid=s_id: self.run_single_test(sid))
            act_layout.addWidget(play_btn)

            more_lbl = QLabel("•••")
            more_lbl.setStyleSheet("color: #64748b; font-size: 10px;")
            act_layout.addWidget(more_lbl)
            act_layout.addStretch()

            self.table.setCellWidget(row, 6, actions_widget)

        if scenarios:
            self.select_scenario(scenarios[0].get("id"))

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

        self.code_filename_lbl.setText(sc.get("file_name", "test_spec.py"))
        self.code_edit.setPlainText(sc.get("code", ""))

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

        self.runner.run_tests_async(
            test_file_paths=test_files,
            browser=self.selected_browser,
            headless=self.headless,
            env=self.current_env,
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
