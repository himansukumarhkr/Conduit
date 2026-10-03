import os
import sys
import re
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
    QLineEdit, QCheckBox, QProgressBar, QSplitter, QSizePolicy
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

        if col == 2:
            tags_text = index.data() or ""
            tags = [t.strip() for t in tags_text.split() if t.strip()]
            x = option.rect.x() + 4
            y = option.rect.y() + (option.rect.height() - 22) // 2
            font = QFont("-apple-system", 8, QFont.Bold)
            painter.setFont(font)

            for tag in tags:
                clean = tag.replace("@", "")
                if clean == "smoke":
                    bg = QColor(37, 99, 235, 45)
                    border = QColor(59, 130, 246, 120)
                    fg = QColor("#60a5fa")
                elif clean == "failed":
                    bg = QColor(239, 68, 68, 45)
                    border = QColor(239, 68, 68, 120)
                    fg = QColor("#f87171")
                else:
                    bg = QColor(217, 119, 6, 45)
                    border = QColor(245, 158, 11, 120)
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
            bg = QColor(16, 185, 129, 35) if is_passed else QColor(239, 68, 68, 45)
            border = QColor(16, 185, 129, 90) if is_passed else QColor(239, 68, 68, 110)
            fg = QColor("#34d399") if is_passed else QColor("#f87171")

            font = QFont("-apple-system", 8, QFont.Bold)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            w = metrics.horizontalAdvance(status) + 18
            h = 22
            x = option.rect.x() + 4
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


class RecordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Record New Browser Journey")
        self.setFixedSize(450, 320)
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
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)

        record_btn = QPushButton("Start Recording")
        record_btn.setObjectName("btnRecord")
        record_btn.clicked.connect(self.accept)
        btn_box.addWidget(record_btn)
        layout.addLayout(btn_box)

    def get_data(self):
        name = self.name_edit.text().strip() or "Recorded Flow"
        url = self.url_edit.text().strip() or "https://demo.playwright.dev/todomvc/"
        tags = [t.strip() for t in self.tags_edit.text().split(",") if t.strip()]
        return name, url, tags


class ConduitMainWindow(QMainWindow):
    def __init__(self, workspace_dir: str):
        super().__init__()
        self.workspace_dir = workspace_dir
        self.catalog = CatalogManager(workspace_dir)
        self.ast_engine = ASTNormalizer()
        self.runner = TestRunner(workspace_dir)
        self.recorder = None
        self._current_recording_meta = {}

        self.current_env = "QA"
        self.selected_browser = "msedge"
        self.headless = True
        self.selected_scenario_id = "sc_001"

        self.bridge = ExecutionBridge()
        self.bridge.log_signal.connect(self.append_log)
        self.bridge.progress_signal.connect(self.update_progress)
        self.bridge.finished_signal.connect(self.on_execution_finished)

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
            QTableWidget {
                background-color: #080c14;
                border: none;
                gridline-color: transparent;
                selection-background-color: rgba(37, 99, 235, 0.15);
                selection-color: #ffffff;
            }
            QTableWidget::item {
                padding: 10px 8px;
                border-bottom: 1px solid #141c2e;
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

        self.nav_catalog_btn = self._make_sidebar_btn("Catalog", active=True)
        self.nav_record_btn = self._make_sidebar_btn("Record", clicked=self.on_record_clicked)
        self.nav_suites_btn = self._make_sidebar_btn("Suites")
        self.nav_history_btn = self._make_sidebar_btn("History")

        layout.addWidget(self.nav_catalog_btn)
        layout.addWidget(self.nav_record_btn)
        layout.addWidget(self.nav_suites_btn)
        layout.addWidget(self.nav_history_btn)

        layout.addStretch()

        settings_btn = self._make_sidebar_btn("Settings")
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

        record_btn = QPushButton("● Record New Flow")
        record_btn.setCursor(Qt.PointingHandCursor)
        record_btn.setStyleSheet("""
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
        record_btn.clicked.connect(self.on_record_clicked)
        layout.addWidget(record_btn)

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
        self.append_log("INFO", f"Selected target browser: [{b_name}]")

    def toggle_headless(self):
        self.headless = not self.headless
        state_str = "ON" if self.headless else "OFF"
        self.headless_btn.setText(f"Headless: {state_str}")
        self.append_log("INFO", f"Headless execution mode: {state_str}")

    def build_table_container(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(0)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "", "Scenario Name", "Tags", "Last Execution", "Status", "Duration", "Actions"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Fixed)

        self.table.setColumnWidth(0, 36)
        self.table.setColumnWidth(6, 100)

        self.pill_delegate = TablePillDelegate(self.table)
        self.table.setItemDelegateForColumn(2, self.pill_delegate)
        self.table.setItemDelegateForColumn(4, self.pill_delegate)

        self.table.cellClicked.connect(self.on_table_cell_clicked)
        layout.addWidget(self.table)

        return container

    def build_inspector_panel(self):
        panel = QFrame()
        panel.setStyleSheet("background-color: #0d1527; border-left: 1px solid #1e293b;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

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
        self.log_feed.setFont(QFont("Consolas", 9))
        self.log_feed.setStyleSheet("background: transparent; border: none; color: #38bdf8;")
        logs_layout.addWidget(self.log_feed)

        layout.addWidget(logs_frame)

        self.append_log("INFO", "Conduit 100% Python Desktop App initialized.")
        return panel

    def build_bottom_bar(self):
        bar = QFrame()
        bar.setFixedHeight(48)
        bar.setStyleSheet("background-color: #0d1527; border-top: 1px solid #1e293b;")
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(24, 6, 24, 8)
        layout.setSpacing(4)

        meta_row = QHBoxLayout()
        title = QLabel("Execution Status")
        title.setStyleSheet("font-size: 11px; font-weight: bold; color: #cbd5e1;")
        meta_row.addWidget(title)
        meta_row.addStretch()

        self.status_lbl = QLabel("Idle — Ready")
        self.status_lbl.setStyleSheet("font-size: 11px; color: #64748b;")
        meta_row.addWidget(self.status_lbl)
        layout.addLayout(meta_row)

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
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #06b6d4, stop:1 #3b82f6);
                border-radius: 2px;
            }
        """)
        layout.addWidget(self.pbar)

        return bar

    def load_scenarios(self):
        scenarios = self.catalog.get_all_scenarios()
        self.table.setRowCount(0)

        for row, sc in enumerate(scenarios):
            self.table.insertRow(row)

            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk_item.setCheckState(Qt.Checked if row < 3 else Qt.Unchecked)
            self.table.setItem(row, 0, chk_item)

            name_item = QTableWidgetItem(sc.get("name", ""))
            name_item.setData(Qt.UserRole, sc.get("id"))
            self.table.setItem(row, 1, name_item)

            tags_str = " ".join(sc.get("tags", []))
            tags_item = QTableWidgetItem(tags_str)
            self.table.setItem(row, 2, tags_item)

            exec_item = QTableWidgetItem(sc.get("last_execution", ""))
            exec_item.setForeground(QColor("#64748b"))
            self.table.setItem(row, 3, exec_item)

            status_item = QTableWidgetItem(sc.get("status", "Passed"))
            self.table.setItem(row, 4, status_item)

            dur_item = QTableWidgetItem(sc.get("duration", "--"))
            dur_item.setForeground(QColor("#64748b"))
            self.table.setItem(row, 5, dur_item)

            actions_widget = QWidget()
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
            card = QLabel(st.get("human_description", f"{idx + 1}. Step"))
            card.setWordWrap(True)
            if idx == 0:
                card.setStyleSheet("""
                    background-color: rgba(56, 189, 248, 0.08);
                    border: 1px solid #38bdf8;
                    border-radius: 6px;
                    padding: 8px 10px;
                    color: #ffffff;
                    font-size: 12px;
                """)
            else:
                card.setStyleSheet("""
                    background-color: rgba(15, 23, 42, 0.6);
                    border: 1px solid rgba(51, 65, 85, 0.4);
                    border-radius: 6px;
                    padding: 8px 10px;
                    color: #cbd5e1;
                    font-size: 12px;
                """)
            self.steps_container_layout.addWidget(card)

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
        self.log_feed.appendHtml(f"<span style='color:{color}; font-weight:bold;'>[{level}]</span> <span style='color:#e2e8f0;'>{msg}</span>")

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
        dlg = RecordDialog(self)
        if dlg.exec() == QDialog.Accepted:
            name, url, tags = dlg.get_data()
            self.append_log("INFO", f"Launching browser recorder for '{name}' on {url}...")
            self._current_recording_meta = {
                "name": name,
                "url": url,
                "tags": tags,
                "browser": self.selected_browser
            }

            def on_action(step_data):
                desc = step_data.get("human_description", "")
                self.bridge.log_signal.emit("INFO", f"Recorded step: {desc}")

            self.recorder = BrowserRecorder(on_action_recorded=on_action)
            self.recorder.start_recording(initial_url=url, browser_channel=self.selected_browser)
            self.append_log("INFO", "Recording active in browser. Alt+Click to inject assertions. Close browser when finished.")
