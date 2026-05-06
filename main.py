import sys
import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

import config
from core.logger_setup import configure_logging
from gui.main_window import MainWindow


def main():
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    config.CASES_DIR.mkdir(parents=True, exist_ok=True)
    config.STUDIES_DIR.mkdir(parents=True, exist_ok=True)

    configure_logging()
    log = logging.getLogger(__name__)
    log.info("=== Rekon labs CFD starting ===")

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Rekon labs CFD")
    app.setOrganizationName("Rekon labs")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
