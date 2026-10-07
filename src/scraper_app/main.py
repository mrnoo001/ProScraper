"""Desktop application entry point."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication

if getattr(sys, "frozen", False):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(Path(sys._MEIPASS) / "ms-playwright")

from scraper_app.ui.mainwindow import STYLESHEET, MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ProScraper")
    app.setOrganizationName("ProScraper")
    app.setStyle("Fusion")
    data_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    log_dir = Path(data_path)
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "proscraper.log", maxBytes=2_000_000, backupCount=4, encoding="utf-8"
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[handler],
    )
    app.setStyleSheet(STYLESHEET)
    window = MainWindow(log_dir)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
