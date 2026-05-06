import logging

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
)

LEVEL_COLORS_DARK = {
    logging.DEBUG:    "#888888",
    logging.INFO:     "#e0e0e0",
    logging.WARNING:  "#ffcc00",
    logging.ERROR:    "#ff5555",
    logging.CRITICAL: "#ff0000",
}

LEVEL_COLORS_LIGHT = {
    logging.DEBUG:    "#555555",
    logging.INFO:     "#000000",
    logging.WARNING:  "#b26b00",
    logging.ERROR:    "#aa0000",
    logging.CRITICAL: "#ff0000",
}





class _Signaller(QObject):
    record = pyqtSignal(logging.LogRecord)


class QtLogHandler(logging.Handler):
    """Thread-safe handler: emits a Qt signal so any thread can log safely."""

    def __init__(self):
        super().__init__()
        self.signaller = _Signaller()

    def emit(self, record: logging.LogRecord):
        self.signaller.record.emit(record)


class LogWidget(QWidget):
    """
    Dark-themed QTextEdit that displays log records colour-coded by level.
    Registers itself with the root logger via attach_qt_handler().
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._handler = QtLogHandler()
        self._handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
        self._handler.signaller.record.connect(self._on_record)
        self._records = []  # Store last 1000 records for re-rendering on theme switch
        self._setup_ui()


        from core.logger_setup import attach_qt_handler
        attach_qt_handler(self._handler)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._edit = QTextEdit()
        self._edit.setReadOnly(True)
        self._edit.setFont(QFont("Consolas", 9))
        layout.addWidget(self._edit)
        self.refresh_theme()

        btn_row = QHBoxLayout()
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(60)
        clear_btn.clicked.connect(self._edit.clear)
        btn_row.addStretch()
        btn_row.addWidget(clear_btn)
        layout.addLayout(btn_row)

    def _on_record(self, record: logging.LogRecord):
        self._records.append(record)
        if len(self._records) > 1000:
            self._records.pop(0)
            
        self._render_record(record)

    def _render_record(self, record: logging.LogRecord):
        from core.settings_manager import SettingsManager
        theme = SettingsManager.get("theme")
        colors = LEVEL_COLORS_DARK if theme == "dark" else LEVEL_COLORS_LIGHT
        
        color = colors.get(record.levelno, "#000000" if theme == "light" else "#e0e0e0")
        self._edit.setTextColor(QColor(color))
        self._edit.append(self._handler.format(record))

        sb = self._edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def refresh_theme(self):
        from core.settings_manager import SettingsManager
        theme = SettingsManager.get("theme")
        if theme == "dark":
            self._edit.setStyleSheet("background:#1e1e1e; color:#e0e0e0; border:none;")
        else:
            self._edit.setStyleSheet("background:#ffffff; color:#000000; border:none;")
        
        # Re-render existing logs
        self._edit.clear()
        for record in self._records:
            self._render_record(record)



