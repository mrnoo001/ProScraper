"""Responsive Qt worker that owns the persistent Playwright session."""

from __future__ import annotations

import logging
import queue
import random
import threading
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from PySide6.QtCore import QThread, Signal

from scraper_app.domain.models import ProjectConfig
from scraper_app.extraction.extractor import extract_records
from scraper_app.storage.database import Database

PICKER_PATH = Path(__file__).parents[1] / "extraction" / "picker.js"
LOGGER = logging.getLogger(__name__)


class BrowserWorker(QThread):
    status = Signal(str, str)
    selected = Signal(dict)
    preview = Signal(list)
    progress = Signal(int, int, int)
    job_finished = Signal(bool, str)

    def __init__(self, database: Database, profile_path: Path) -> None:
        super().__init__()
        self.database = database
        self.profile_path = profile_path
        self._commands: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        self._pause = threading.Event()
        self._pause.set()
        self._stop = threading.Event()
        self._page: Page | None = None
        self._context: BrowserContext | None = None

    def open_page(self, url: str) -> None:
        self._commands.put(("open", {"url": url}))

    def pick_element(self) -> None:
        self._commands.put(("pick", {}))

    def start_job(self, project_id: int, config: ProjectConfig, resume: bool = False) -> None:
        self._pause.set()
        self._stop.clear()
        self._commands.put(
            ("scrape", {"project_id": project_id, "config": config, "resume": resume})
        )

    def pause_job(self) -> None:
        self._pause.clear()
        self.status.emit("paused", "Job dijeda setelah halaman saat ini selesai.")

    def resume_job(self) -> None:
        self._pause.set()
        self.status.emit("running", "Job dilanjutkan.")

    def stop_job(self) -> None:
        self._stop.set()
        self._pause.set()

    def close_browser(self) -> None:
        self._commands.put(("close", {}))

    def _bind_page(self, context: BrowserContext) -> Page:
        context.add_init_script(path=str(PICKER_PATH))

        def on_selected(_: dict[str, Any], payload: dict[str, Any]) -> None:
            self.selected.emit(payload)

        context.expose_binding("proscraperSelected", on_selected)
        page = context.pages[0] if context.pages else context.new_page()
        return page

    def run(self) -> None:
        try:
            with sync_playwright() as playwright:
                while not self.isInterruptionRequested():
                    try:
                        command, payload = self._commands.get(timeout=0.1)
                    except queue.Empty:
                        if self._page is not None and not self._page.is_closed():
                            self._page.wait_for_timeout(60)
                        continue
                    try:
                        if command == "open":
                            self._open(playwright, str(payload["url"]))
                        elif command == "pick":
                            self._activate_picker()
                        elif command == "scrape":
                            self._scrape(payload)
                        elif command == "close":
                            self._close_context()
                            self.status.emit("browser", "Browser ditutup.")
                    except Exception as exc:
                        self.status.emit("error", str(exc))
        except Exception as exc:
            self.status.emit("error", f"Browser worker berhenti: {exc}")
        finally:
            self._close_context()

    def _open(self, playwright: Any, url: str) -> None:
        self._close_context()
        self.profile_path.mkdir(parents=True, exist_ok=True)
        self._context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_path),
            headless=False,
            viewport={"width": 1440, "height": 960},
            accept_downloads=True,
        )
        self._page = self._bind_page(self._context)
        self._page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        self.status.emit(
            "browser",
            "Browser siap. Login atau selesaikan verifikasi secara manual bila diperlukan.",
        )

    def _activate_picker(self) -> None:
        if self._page is None or self._page.is_closed():
            self.status.emit("error", "Buka halaman browser terlebih dahulu.")
            return
        self._page.evaluate("window.__proscraperPicker?.enable()")
        self.status.emit(
            "picker", "Mode pilih elemen aktif. Klik satu elemen di browser; Esc untuk membatalkan."
        )

    def _scrape(self, payload: dict[str, Any]) -> None:
        project_id = int(payload["project_id"])
        config: ProjectConfig = payload["config"]
        if self._page is None or self._page.is_closed():
            self.job_finished.emit(
                False, "Browser belum dibuka. Buka browser dan muat situs terlebih dahulu."
            )
            return
        if not config.item_selector or not config.fields:
            self.job_finished.emit(False, "Tentukan kontainer berulang dan setidaknya satu field.")
            return
        page = self._page
        try:
            if payload.get("resume"):
                resumable = self.database.resumable_job(project_id)
                if resumable is None:
                    raise ValueError("Tidak ada job yang dapat dilanjutkan.")
                job_id, checkpoint = resumable
                if self.database.job_config(job_id).to_dict() != config.to_dict():
                    raise ValueError(
                        "Konfigurasi proyek berubah sejak job dijeda. "
                        "Jalankan job baru atau pulihkan konfigurasi sebelumnya."
                    )
                self.database.resume_job(job_id)
            else:
                job_id = self.database.create_job(project_id, config)
                checkpoint = 0
            self._stop.clear()
            max_pages = max(config.pagination.max_pages, 1)

            if page.url.rstrip("/") != config.start_url.rstrip("/"):
                page.goto(config.start_url, wait_until="domcontentloaded", timeout=60_000)
            if checkpoint and config.pagination.mode == "click":
                for _ in range(checkpoint):
                    page.locator(config.pagination.selector).first.click(timeout=10_000)
                    page.wait_for_load_state("domcontentloaded", timeout=15_000)
            elif checkpoint and config.pagination.mode == "url":
                page.goto(
                    config.pagination.url_template.format(page=checkpoint + 1),
                    wait_until="domcontentloaded",
                )

            total_records = 0
            for page_number in range(checkpoint + 1, max_pages + 1):
                if not self._wait_if_paused():
                    self.database.finish_job(job_id, "paused")
                    self.job_finished.emit(True, f"Job dijeda pada halaman {page_number - 1}.")
                    return
                if not self._wait_for_manual_challenge(page, self._stop):
                    self.database.finish_job(job_id, "paused")
                    self.job_finished.emit(True, f"Job dijeda setelah {total_records} record.")
                    return
                rows = extract_records(page, config.item_selector, config.fields)
                if not rows:
                    self.status.emit(
                        "warning", "Tidak ada item cocok. Periksa selector atau login situs."
                    )
                self.preview.emit(rows[:100])
                total_records += self.database.save_records(
                    job_id, project_id, rows, config.unique_field
                )
                self.database.update_checkpoint(job_id, page_number)
                self.progress.emit(page_number, max_pages, total_records)
                if self._stop.is_set():
                    self.database.finish_job(job_id, "paused")
                    self.job_finished.emit(True, f"Job dijeda setelah {total_records} record.")
                    return
                if page_number >= max_pages or config.pagination.mode == "none":
                    break
                if not self._wait_if_paused():
                    self.database.finish_job(job_id, "paused")
                    self.job_finished.emit(True, f"Job dijeda setelah {total_records} record.")
                    return
                time.sleep(max(config.request_delay_ms, 0) / 1000 * random.uniform(0.85, 1.15))
                if not self._advance(page, config, page_number + 1):
                    break
            self.database.finish_job(job_id, "done")
            LOGGER.info(
                "Scrape job %s completed for project %s: %s new records",
                job_id,
                project_id,
                total_records,
            )
            self.job_finished.emit(True, f"Selesai. {total_records} record baru disimpan.")
        except Exception as exc:
            if "job_id" in locals():
                self.database.finish_job(job_id, "failed", str(exc))
            LOGGER.exception("Scrape job failed for project %s", project_id)
            self.job_finished.emit(False, str(exc))

    @staticmethod
    def _wait_for_manual_challenge(page: Page, stop: threading.Event) -> bool:
        deadline = time.monotonic() + 600
        markers = (
            "verify you are human",
            "checking your browser",
            "complete the security check",
            "attention required",
            "just a moment",
        )
        while time.monotonic() < deadline:
            if stop.is_set():
                return False
            title = page.title().lower()
            body = page.locator("body").inner_text(timeout=3000).lower()[:5000]
            if not any(marker in title or marker in body for marker in markers):
                return True
            page.wait_for_timeout(1000)
        raise PlaywrightTimeout("Verifikasi manual belum selesai setelah 10 menit.")

    @staticmethod
    def _advance(page: Page, config: ProjectConfig, next_page: int) -> bool:
        pagination = config.pagination
        if pagination.mode == "click":
            page.locator(pagination.selector).first.click(timeout=10_000)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15_000)
            except PlaywrightTimeout:
                page.wait_for_timeout(1200)
        elif pagination.mode == "url":
            page.goto(pagination.url_template.format(page=next_page), wait_until="domcontentloaded")
        elif pagination.mode == "infinite":
            previous_height = page.evaluate("document.body.scrollHeight")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1600)
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height <= previous_height:
                return False
        return True

    def _wait_if_paused(self) -> bool:
        while not self._pause.wait(0.1):
            if self._stop.is_set():
                return False
        return not self._stop.is_set()

    def _close_context(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
            self._page = None
