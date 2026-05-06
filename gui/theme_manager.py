from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import Qt

class ThemeManager:
    DARK_STYLESHEET = """
        QWidget {
            background-color: #1e1e1e;
            color: #d4d4d4;
            font-family: 'Segoe UI', sans-serif;
            font-size: 10pt;
        }
        QMainWindow, QDialog {
            background-color: #1e1e1e;
        }
        QMenuBar {
            background-color: #2d2d2d;
            color: #d4d4d4;
            border-bottom: 1px solid #333;
        }
        QMenuBar::item:selected {
            background-color: #3e3e42;
        }
        QMenu {
            background-color: #2d2d2d;
            color: #d4d4d4;
            border: 1px solid #454545;
        }
        QMenu::item:selected {
            background-color: #007acc;
            color: white;
        }
        QTabWidget::pane {
            border: 1px solid #333;
            background: #252526;
            top: -1px;
        }
        QTabBar::tab {
            background: #2d2d2d;
            color: #969696;
            padding: 8px 15px;
            border: 1px solid #333;
            border-bottom: none;
            min-width: 80px;
        }
        QTabBar::tab:selected {
            background: #252526;
            color: white;
            border-bottom: 2px solid #007acc;
        }
        QPushButton {
            background-color: #333337;
            color: #f1f1f1;
            border: 1px solid #454545;
            padding: 6px 12px;
            border-radius: 3px;
            min-height: 20px;
        }
        QPushButton:hover {
            background-color: #3e3e42;
            border: 1px solid #007acc;
        }
        QPushButton:pressed {
            background-color: #007acc;
        }
        QPushButton:disabled {
            background-color: #2d2d2d;
            color: #666;
        }
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
            background-color: #3c3c3c;
            color: #f1f1f1;
            border: 1px solid #454545;
            padding: 4px;
            border-radius: 2px;
        }
        QComboBox QAbstractItemView {
            background-color: #2d2d2d;
            color: #d4d4d4;
            selection-background-color: #007acc;
            outline: 0;
        }
        QLabel {
            color: #d4d4d4;
            background: transparent;
        }
        QGroupBox {
            border: 1px solid #444;
            margin-top: 15px;
            font-weight: bold;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
            color: #007acc;
        }
        QStatusBar {
            background: #007acc;
            color: white;
        }
        QSplitter::handle {
            background: #333;
        }
        QScrollBar:vertical {
            border: none;
            background: #2d2d2d;
            width: 12px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: #4f4f4f;
            min-height: 20px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
    """

    LIGHT_STYLESHEET = """
        QWidget {
            background-color: #f3f3f3;
            color: #1a1a1a;
            font-family: 'Segoe UI', sans-serif;
            font-size: 10pt;
        }
        QMainWindow, QDialog {
            background-color: #f3f3f3;
        }
        QMenuBar {
            background-color: #ffffff;
            color: #1a1a1a;
            border-bottom: 1px solid #ccc;
        }
        QMenuBar::item:selected {
            background-color: #e1e1e1;
        }
        QMenu {
            background-color: #ffffff;
            color: #1a1a1a;
            border: 1px solid #ccc;
        }
        QMenu::item:selected {
            background-color: #007acc;
            color: white;
        }
        QTabWidget::pane {
            border: 1px solid #ccc;
            background: white;
            top: -1px;
        }
        QTabBar::tab {
            background: #e1e1e1;
            color: #666;
            padding: 8px 15px;
            border: 1px solid #ccc;
            border-bottom: none;
            min-width: 80px;
        }
        QTabBar::tab:selected {
            background: white;
            color: black;
            border-bottom: 2px solid #007acc;
        }
        QPushButton {
            background-color: #ffffff;
            color: #1a1a1a;
            border: 1px solid #ccc;
            padding: 6px 12px;
            border-radius: 3px;
            min-height: 20px;
        }
        QPushButton:hover {
            background-color: #f0f0f0;
            border: 1px solid #007acc;
        }
        QPushButton:pressed {
            background-color: #e5e5e5;
        }
        QPushButton:disabled {
            background-color: #f9f9f9;
            color: #aaa;
        }
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
            background-color: white;
            color: #1a1a1a;
            border: 1px solid #ccc;
            padding: 4px;
            border-radius: 2px;
        }
        QComboBox QAbstractItemView {
            background-color: white;
            color: #1a1a1a;
            selection-background-color: #007acc;
            outline: 0;
            border: 1px solid #ccc;
        }
        QLabel {
            color: #1a1a1a;
            background: transparent;
        }
        QGroupBox {
            border: 1px solid #ccc;
            margin-top: 15px;
            font-weight: bold;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
            color: #007acc;
        }
        QStatusBar {
            background: #007acc;
            color: white;
        }
        QSplitter::handle {
            background: #ccc;
        }
        QScrollBar:vertical {
            border: none;
            background: #f0f0f0;
            width: 12px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: #cdcdcd;
            min-height: 20px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
    """

    @classmethod
    def apply_theme(cls, theme_name: str):
        app = QApplication.instance()
        if not app:
            return

        if theme_name == "dark":
            app.setStyleSheet(cls.DARK_STYLESHEET)
        else:
            app.setStyleSheet(cls.LIGHT_STYLESHEET)
