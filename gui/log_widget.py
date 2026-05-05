import logging

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
)

LEVEL_COLORS = {
    logging.DEBUG:    "#888888",
    logging.INFO:     "#e0e0e0",
    logging.WARNING:  "#ffcc00",
    logging.ERROR:    "#ff5555",
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
        self._setup_ui()

        from core.logger_setup import attach_qt_handler
        attach_qt_handler(self._handler)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._edit = QTextEdit()
        self._edit.setReadOnly(True)
        self._edit.setFont(QFont("Consolas", 9))
        self._edit.setStyleSheet("background:#1e1e1e; color:#e0e0e0; border:none;")
        layout.addWidget(self._edit)

        btn_row = QHBoxLayout()
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(60)
        clear_btn.clicked.connect(self._edit.clear)
        btn_row.addStretch()
        btn_row.addWidget(clear_btn)
        layout.addLayout(btn_row)

    def _on_record(self, record: logging.LogRecord):
        color = LEVEL_COLORS.get(record.levelno, "#e0e0e0")
        self._edit.setTextColor(QColor(color))
        self._edit.append(self._handler.format(record))
        sb = self._edit.verticalScrollBar()
        sb.setValue(sb.maximum())
