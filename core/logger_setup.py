import logging
import logging.handlers
import config

_qt_handler: logging.Handler | None = None


def configure_logging():
    """Call once at startup before QApplication exists."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, config.LOG_LEVEL, logging.DEBUG))

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    log_file = config.LOGS_DIR / "rekon_labs_cfd.log"
    fh = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=config.LOG_FILE_MAX_BYTES,
        backupCount=config.LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    root.addHandler(ch)


def attach_qt_handler(handler: logging.Handler):
    """Call after QApplication is created to wire the GUI log widget."""
    global _qt_handler
    _qt_handler = handler
    logging.getLogger().addHandler(handler)
