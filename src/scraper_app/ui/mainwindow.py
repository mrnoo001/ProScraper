"""Modern desktop workspace for configuring and running scraping projects."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from scraper_app.domain.models import FieldDefinition, PaginationConfig, ProjectConfig
from scraper_app.engine.worker import BrowserWorker
from scraper_app.exporting.excel import export_csv, export_excel, export_json
from scraper_app.storage.database import Database

LOGGER = logging.getLogger(__name__)

STYLESHEET = """
* { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
QMainWindow, QWidget#root { background: #0d0f17; color: #e9eaf2; }
QWidget#sidebar { background: #11131d; border-right: 1px solid #242735; }
QLabel#brand { font-size: 19px; font-weight: 750; color: #f7f6ff; }
QLabel#brandMark { color: #a998ff; font-size: 22px; font-weight: 900; }
QLabel#eyebrow { color: #8c91a6; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#title { font-size: 26px; font-weight: 750; color: #f7f7fc; }
QLabel#subtitle { color: #959aaf; font-size: 13px; }
QLabel#sectionTitle { font-size: 15px; font-weight: 700; color: #f1f1f8; }
QLabel#muted { color: #9297aa; }
QFrame#card { background: #151824; border: 1px solid #272b3a; border-radius: 14px; }
QFrame#sidebarCard { background: #181a27; border: 1px solid #282b3b; border-radius: 11px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
 background: #10121b; border: 1px solid #303447; border-radius: 8px; padding: 9px 10px;
 color: #eff0f6; selection-background-color: #6655dc; min-height: 18px;
}
QComboBox::drop-down { border: 0; width: 24px; }
QComboBox QAbstractItemView {
 background: #171a25; color: #eee; selection-background-color: #5142c5;
}
QPushButton {
 background: #212434; border: 1px solid #33374b; border-radius: 8px;
 padding: 9px 13px; color: #e7e8f0; font-weight: 650;
}
QPushButton:hover { background: #2a2d40; border-color: #6f60d9; }
QPushButton:disabled { color: #696d7e; background: #171923; border-color: #252837; }
QPushButton#primary { background: #6655dc; border-color: #7668e7; color: white; }
QPushButton#primary:hover { background: #7666ec; }
QPushButton#danger { color: #ff989f; }
QTableWidget {
 background: #10121b; alternate-background-color: #141722; border: 1px solid #2a2e3e;
 border-radius: 9px; gridline-color: #262a39;
}
QHeaderView::section {
 background: #191c29; color: #aeb2c2; border: 0; border-bottom: 1px solid #303447;
 padding: 8px; font-weight: 650;
}
QTableWidget::item { padding: 4px; }
QStatusBar { background: #11131d; color: #9a9eae; border-top: 1px solid #262a38; }
"""


def _label(text: str, object_name: str = "") -> QLabel:
    label = QLabel(text)
    if object_name:
        label.setObjectName(object_name)
    return label


def _card(layout: QVBoxLayout, title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    inner = QVBoxLayout(frame)
    inner.setContentsMargins(18, 16, 18, 16)
    inner.setSpacing(11)
    inner.addWidget(_label(title, "sectionTitle"))
    if subtitle:
        inner.addWidget(_label(subtitle, "muted"))
    layout.addWidget(frame)
    return frame, inner


class MainWindow(QMainWindow):
    def __init__(self, app_data: Path) -> None:
        super().__init__()
        self.app_data = app_data
        self.app_data.mkdir(parents=True, exist_ok=True)
        self.database = Database(self.app_data / "proscraper.db")
        self.project_id: int | None = None
        self._job_active = False
        self._job_paused = False
        self.worker = BrowserWorker(self.database, self.app_data / "browser-profile")
        self.worker.status.connect(self._on_status)
        self.worker.selected.connect(self._on_selected)
        self.worker.preview.connect(self._show_preview)
        self.worker.progress.connect(self._show_progress)
        self.worker.job_finished.connect(self._job_finished)
        self.worker.start()
        self.setWindowTitle("ProScraper")
        self.resize(1440, 940)
        self.setMinimumSize(1120, 740)
        self._build_ui()
        self._load_projects()
        self.statusBar().showMessage("Siap · sesi browser disimpan secara lokal")

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        page = QHBoxLayout(root)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(244)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 24, 18, 20)
        side.setSpacing(15)
        brand = QHBoxLayout()
        brand.addWidget(_label("◈", "brandMark"))
        brand.addWidget(_label("ProScraper", "brand"))
        brand.addStretch()
        side.addLayout(brand)
        side.addSpacing(12)
        side.addWidget(_label("WORKSPACE", "eyebrow"))

        project_panel = QFrame()
        project_panel.setObjectName("sidebarCard")
        panel_layout = QVBoxLayout(project_panel)
        panel_layout.setContentsMargins(11, 11, 11, 11)
        panel_layout.setSpacing(9)
        self.project_combo = QComboBox()
        self.project_combo.currentIndexChanged.connect(self._select_project)
        panel_layout.addWidget(self.project_combo)
        project_buttons = QHBoxLayout()
        new_button = QPushButton("+ Proyek baru")
        new_button.clicked.connect(self._new_project)
        save_button = QPushButton("Simpan")
        save_button.clicked.connect(self._save_project)
        project_buttons.addWidget(new_button)
        project_buttons.addWidget(save_button)
        panel_layout.addLayout(project_buttons)
        side.addWidget(project_panel)
        side.addStretch()
        side.addWidget(_label("AUTOMATION", "eyebrow"))
        side.addWidget(_label("Playwright · Persistent profile", "muted"))
        side.addWidget(_label("SQLite · Local-first storage", "muted"))
        side.addSpacing(8)
        side.addWidget(_label("ProScraper  0.1.0", "muted"))
        page.addWidget(sidebar)

        main = QWidget()
        content = QVBoxLayout(main)
        content.setContentsMargins(30, 26, 30, 22)
        content.setSpacing(17)
        page.addWidget(main, 1)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(5)
        heading.addWidget(_label("Scraping workspace", "title"))
        heading.addWidget(
            _label("Rancang field, jalankan pengambilan data, dan ekspor hasil.", "subtitle")
        )
        header.addLayout(heading)
        header.addStretch()
        self.status_pill = _label("●  Siap")
        self.status_pill.setStyleSheet(
            "color:#9be3c3;background:#172a26;border:1px solid #25483d;"
            "border-radius:14px;padding:7px 11px;"
        )
        header.addWidget(self.status_pill, 0, Qt.AlignmentFlag.AlignTop)
        content.addLayout(header)

        _, url_layout = _card(
            content,
            "Sumber halaman",
            "Gunakan browser headed untuk login atau menyelesaikan verifikasi secara manual.",
        )
        url_row = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Nama proyek")
        self.name_input.setMaximumWidth(210)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com/products")
        self.open_button = QPushButton("Buka browser ↗")
        self.open_button.setObjectName("primary")
        self.open_button.clicked.connect(self._open_browser)
        url_row.addWidget(self.name_input)
        url_row.addWidget(self.url_input, 1)
        url_row.addWidget(self.open_button)
        url_layout.addLayout(url_row)

        work_area = QHBoxLayout()
        work_area.setSpacing(16)
        left_column = QVBoxLayout()
        left_column.setSpacing(16)
        right_column = QVBoxLayout()
        right_column.setSpacing(16)
        work_area.addLayout(left_column, 6)
        work_area.addLayout(right_column, 5)
        content.addLayout(work_area, 1)

        _, extraction_layout = _card(
            left_column,
            "1. Tentukan data",
            "Klik contoh nilai di browser. Selector relatif dan kontainer berulang "
            "akan disarankan otomatis.",
        )
        selector_row = QHBoxLayout()
        self.item_selector = QLineEdit()
        self.item_selector.setPlaceholderText(
            "CSS selector kontainer item — terisi otomatis atau edit manual"
        )
        selector_row.addWidget(self.item_selector, 1)
        self.pick_button = QPushButton("＋ Pilih elemen")
        self.pick_button.setObjectName("primary")
        self.pick_button.clicked.connect(self._pick_element)
        selector_row.addWidget(self.pick_button)
        extraction_layout.addLayout(selector_row)
        self.fields_table = QTableWidget(0, 4)
        self.fields_table.setHorizontalHeaderLabels(
            ["Kolom", "Selector relatif", "Atribut", "Tipe"]
        )
        self.fields_table.horizontalHeader().setStretchLastSection(True)
        self.fields_table.horizontalHeader().setSectionResizeMode(
            0, self.fields_table.horizontalHeader().ResizeMode.ResizeToContents
        )
        self.fields_table.setAlternatingRowColors(True)
        self.fields_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.fields_table.setMinimumHeight(250)
        extraction_layout.addWidget(self.fields_table)
        field_buttons = QHBoxLayout()
        remove_field = QPushButton("Hapus field")
        remove_field.clicked.connect(self._remove_field)
        self.unique_combo = QComboBox()
        self.unique_combo.setMinimumWidth(150)
        field_buttons.addWidget(remove_field)
        field_buttons.addStretch()
        field_buttons.addWidget(_label("Kunci deduplikasi:", "muted"))
        field_buttons.addWidget(self.unique_combo)
        extraction_layout.addLayout(field_buttons)

        _, pagination_layout = _card(
            right_column,
            "2. Pagination & kontrol",
            "Batasi laju permintaan dan lanjutkan job yang terjeda.",
        )
        pagination_grid = QGridLayout()
        pagination_grid.addWidget(_label("Strategi", "muted"), 0, 0)
        self.pagination_combo = QComboBox()
        self.pagination_combo.addItem("Satu halaman", "none")
        self.pagination_combo.addItem("Klik tombol Next", "click")
        self.pagination_combo.addItem("Pola URL", "url")
        self.pagination_combo.addItem("Infinite scroll", "infinite")
        self.pagination_combo.currentIndexChanged.connect(self._pagination_changed)
        pagination_grid.addWidget(self.pagination_combo, 0, 1)
        pagination_grid.addWidget(_label("Selector / URL template", "muted"), 1, 0)
        self.pagination_input = QLineEdit()
        self.pagination_input.setPlaceholderText(
            "CSS tombol Next atau https://site.test/page/{page}"
        )
        pagination_grid.addWidget(self.pagination_input, 1, 1)
        pagination_grid.addWidget(_label("Maks. halaman", "muted"), 2, 0)
        self.max_pages = QSpinBox()
        self.max_pages.setRange(1, 100_000)
        self.max_pages.setValue(1)
        pagination_grid.addWidget(self.max_pages, 2, 1)
        pagination_grid.addWidget(_label("Jeda (detik)", "muted"), 3, 0)
        self.delay = QDoubleSpinBox()
        self.delay.setRange(0.0, 300.0)
        self.delay.setSingleStep(0.5)
        self.delay.setValue(1.2)
        self.delay.setSuffix(" s")
        pagination_grid.addWidget(self.delay, 3, 1)
        pagination_layout.addLayout(pagination_grid)
        self.progress_label = _label("Belum ada job berjalan", "muted")
        pagination_layout.addWidget(self.progress_label)
        controls = QGridLayout()
        self.run_button = QPushButton("Jalankan scraper")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self._run_job)
        self.pause_button = QPushButton("Jeda")
        self.pause_button.clicked.connect(self._pause_job)
        self.resume_button = QPushButton("Lanjutkan job")
        self.resume_button.clicked.connect(self._resume_job)
        self.stop_button = QPushButton("Hentikan")
        self.stop_button.setObjectName("danger")
        self.stop_button.clicked.connect(self.worker.stop_job)
        controls.addWidget(self.run_button, 0, 0, 1, 2)
        controls.addWidget(self.pause_button, 1, 0)
        controls.addWidget(self.resume_button, 1, 1)
        controls.addWidget(self.stop_button, 2, 0, 1, 2)
        pagination_layout.addLayout(controls)
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.stop_button.setEnabled(False)

        _, preview_layout = _card(
            right_column,
            "3. Pratinjau hasil",
            "Maksimal 100 baris ditampilkan; semua hasil tersimpan di SQLite lokal.",
        )
        self.preview_table = QTableWidget(0, 0)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview_table.setMinimumHeight(230)
        preview_layout.addWidget(self.preview_table)
        export_row = QHBoxLayout()
        self.record_count = _label("0 record", "muted")
        export_row.addWidget(self.record_count)
        export_row.addStretch()
        for label, callback in (
            ("Ekspor Excel", self._export_excel),
            ("CSV", self._export_csv),
            ("JSON", self._export_json),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            export_row.addWidget(button)
        preview_layout.addLayout(export_row)

    def _load_projects(self) -> None:
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        self.project_combo.addItem("Pilih proyek…", None)
        for project_id, config in self.database.list_projects():
            self.project_combo.addItem(config.name, project_id)
        self.project_combo.blockSignals(False)

    def _select_project(self, index: int) -> None:
        project_id = self.project_combo.itemData(index)
        if project_id is None:
            return
        entries = dict(self.database.list_projects())
        config = entries.get(project_id)
        if config is None:
            return
        self.project_id = project_id
        self._set_config(config)
        self._refresh_project_records()
        self._update_resume_button()

    def _new_project(self) -> None:
        self.project_id = None
        self.project_combo.blockSignals(True)
        self.project_combo.setCurrentIndex(0)
        self.project_combo.blockSignals(False)
        self._set_config(ProjectConfig(name="", start_url=""))
        self._show_preview([])
        self.record_count.setText("0 record")

    def _set_config(self, config: ProjectConfig) -> None:
        self.name_input.setText(config.name)
        self.url_input.setText(config.start_url)
        self.item_selector.setText(config.item_selector)
        self.fields_table.setRowCount(0)
        for item in config.fields:
            self._add_field(item.name, item.selector, item.attribute, item.mode)
        mode_index = self.pagination_combo.findData(config.pagination.mode)
        self.pagination_combo.setCurrentIndex(max(mode_index, 0))
        self.pagination_input.setText(config.pagination.selector or config.pagination.url_template)
        self.max_pages.setValue(max(config.pagination.max_pages, 1))
        self.delay.setValue(config.request_delay_ms / 1000)
        self._update_unique_fields(config.unique_field)
        self._pagination_changed()

    def _get_config(self) -> ProjectConfig:
        fields: list[FieldDefinition] = []
        for row in range(self.fields_table.rowCount()):
            fields.append(
                FieldDefinition(
                    name=self._cell_text(row, 0),
                    selector=self._cell_text(row, 1),
                    attribute=self._cell_text(row, 2),
                    mode=self._cell_text(row, 3) or "text",  # type: ignore[arg-type]
                )
            )
        mode = self.pagination_combo.currentData()
        pagination = PaginationConfig(
            mode=mode,
            selector=self.pagination_input.text().strip() if mode == "click" else "",
            url_template=self.pagination_input.text().strip() if mode == "url" else "",
            max_pages=self.max_pages.value(),
        )
        return ProjectConfig(
            name=self.name_input.text().strip() or "Proyek tanpa nama",
            start_url=self.url_input.text().strip(),
            item_selector=self.item_selector.text().strip(),
            fields=fields,
            pagination=pagination,
            unique_field=self.unique_combo.currentData() or "",
            request_delay_ms=int(self.delay.value() * 1000),
        )

    def _cell_text(self, row: int, column: int) -> str:
        item = self.fields_table.item(row, column)
        if item is not None:
            return item.text().strip()
        widget = self.fields_table.cellWidget(row, column)
        if isinstance(widget, QComboBox):
            return str(widget.currentData() or widget.currentText())
        return ""

    def _add_field(self, name: str, selector: str, attribute: str = "", mode: str = "text") -> None:
        row = self.fields_table.rowCount()
        self.fields_table.insertRow(row)
        for column, text in enumerate((name, selector, attribute)):
            self.fields_table.setItem(row, column, QTableWidgetItem(text))
        choice = QComboBox()
        choice.addItem("Tekst", "text")
        choice.addItem("Angka", "number")
        choice.setCurrentIndex(max(choice.findData(mode), 0))
        self.fields_table.setCellWidget(row, 3, choice)
        self._update_unique_fields(self.unique_combo.currentData() or "")

    def _update_unique_fields(self, selected: str = "") -> None:
        current_fields = [self._cell_text(row, 0) for row in range(self.fields_table.rowCount())]
        self.unique_combo.blockSignals(True)
        self.unique_combo.clear()
        self.unique_combo.addItem("Hash seluruh field", "")
        for name in current_fields:
            self.unique_combo.addItem(name, name)
        index = self.unique_combo.findData(selected)
        self.unique_combo.setCurrentIndex(max(index, 0))
        self.unique_combo.blockSignals(False)

    def _remove_field(self) -> None:
        row = self.fields_table.currentRow()
        if row >= 0:
            self.fields_table.removeRow(row)
            self._update_unique_fields()

    def _pagination_changed(self) -> None:
        mode = self.pagination_combo.currentData()
        self.pagination_input.setEnabled(mode in ("click", "url"))
        self.pagination_input.setPlaceholderText(
            "CSS tombol Next"
            if mode == "click"
            else "Contoh: https://site.test/page/{page}"
            if mode == "url"
            else "Tidak diperlukan untuk strategi ini"
        )

    def _valid_url(self) -> bool:
        url = self.url_input.text().strip()
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            QMessageBox.warning(
                self,
                "URL tidak valid",
                "Masukkan URL lengkap yang dimulai dengan http:// atau https://.",
            )
            return False
        return True

    def _save_project(self) -> bool:
        config = self._get_config()
        if not config.start_url:
            QMessageBox.warning(self, "URL diperlukan", "Isi URL sumber sebelum menyimpan proyek.")
            return False
        self.project_id = self.database.save_project(self.project_id, config)
        self._load_projects()
        index = self.project_combo.findData(self.project_id)
        if index >= 0:
            self.project_combo.setCurrentIndex(index)
        self.statusBar().showMessage("Proyek tersimpan di database lokal.", 3500)
        return True

    def _open_browser(self) -> None:
        if self._valid_url() and self._save_project():
            self.worker.open_page(self.url_input.text().strip())
            self._set_status("browser", "Membuka browser…")

    def _pick_element(self) -> None:
        if self.project_id is None:
            QMessageBox.information(
                self, "Simpan proyek", "Simpan proyek dan buka browser sebelum memilih elemen."
            )
            return
        self.worker.pick_element()

    def _on_selected(self, data: dict) -> None:
        self.item_selector.setText(str(data.get("item_selector", "")))
        suggested = str(data.get("suggested_name", "field")).strip().replace(" ", "_").lower()
        existing = {self._cell_text(row, 0) for row in range(self.fields_table.rowCount())}
        name = suggested
        suffix = 2
        while name in existing:
            name = f"{suggested}_{suffix}"
            suffix += 1
        self._add_field(name, str(data.get("field_selector", "")))
        self.statusBar().showMessage(
            f"Field '{name}' dipilih · {data.get('count', 0)} kontainer · "
            f"contoh: {data.get('sample', '')}",
            9000,
        )

    def _run_job(self) -> None:
        if not self._valid_url() or not self._save_project():
            return
        config = self._get_config()
        if config.pagination.mode == "click" and not config.pagination.selector:
            QMessageBox.warning(
                self, "Selector Next diperlukan", "Isi selector CSS tombol pagination."
            )
            return
        if config.pagination.mode == "url" and "{page}" not in config.pagination.url_template:
            QMessageBox.warning(
                self, "Template URL tidak valid", "Template URL harus memuat {page}."
            )
            return
        self._set_controls_running(True)
        self._job_active = True
        self._job_paused = False
        self.worker.start_job(self.project_id or 0, config)

    def _pause_job(self) -> None:
        self.worker.pause_job()
        self._job_paused = True
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(True)

    def _resume_job(self) -> None:
        if self.project_id is None:
            return
        if self._job_active and self._job_paused:
            self.worker.resume_job()
        else:
            if not self._valid_url() or not self._save_project():
                return
            self.worker.start_job(self.project_id, self._get_config(), resume=True)
            self._job_active = True
        self._job_paused = False
        self._set_controls_running(True)

    def _update_resume_button(self) -> None:
        available = (
            self.project_id is not None and self.database.resumable_job(self.project_id) is not None
        )
        self.resume_button.setEnabled(bool(available))

    def _set_controls_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.pause_button.setEnabled(running)
        self.stop_button.setEnabled(running)
        self.resume_button.setEnabled(
            not running
            and self.project_id is not None
            and self.database.resumable_job(self.project_id) is not None
        )

    def _on_status(self, kind: str, message: str) -> None:
        self._set_status(kind, message)
        if kind == "error":
            LOGGER.error(message)

    def _set_status(self, kind: str, message: str) -> None:
        colors = {
            "error": ("#ffafb3", "#321b22", "#62313b"),
            "warning": ("#ffd58b", "#302718", "#594321"),
            "running": ("#a9b5ff", "#1d2036", "#343c6e"),
            "paused": ("#ffd58b", "#302718", "#594321"),
            "picker": ("#d3c9ff", "#241f39", "#443776"),
        }
        text, background, border = colors.get(kind, ("#9be3c3", "#172a26", "#25483d"))
        self.status_pill.setText(f"●  {message[:54]}")
        self.status_pill.setStyleSheet(
            f"color:{text};background:{background};border:1px solid {border};"
            "border-radius:14px;padding:7px 11px;"
        )
        self.statusBar().showMessage(message, 8000)

    def _show_progress(self, page: int, total: int, records: int) -> None:
        self.progress_label.setText(f"Halaman {page} / {total}    ·    {records:,} record baru")
        self.record_count.setText(f"{records:,} record pada job ini")

    def _job_finished(self, success: bool, message: str) -> None:
        self._job_active = False
        self._job_paused = False
        self._set_controls_running(False)
        self._set_status("done" if success else "error", message)
        self._update_resume_button()
        if not success:
            QMessageBox.warning(self, "Job tidak selesai", message)
        else:
            self._refresh_project_records()

    def _show_preview(self, rows: list) -> None:
        columns = list(rows[0]) if rows else []
        self.preview_table.clear()
        self.preview_table.setColumnCount(len(columns))
        self.preview_table.setHorizontalHeaderLabels(columns)
        self.preview_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, name in enumerate(columns):
                self.preview_table.setItem(
                    row_index, column_index, QTableWidgetItem(str(row.get(name, "")))
                )
        self.preview_table.resizeColumnsToContents()
        self.preview_table.setAlternatingRowColors(True)
        if rows:
            self.record_count.setText(f"{len(rows)} record pratinjau")

    def _refresh_project_records(self) -> None:
        if self.project_id is None:
            return
        total = self.database.project_record_count(self.project_id)
        records = self.database.project_records(self.project_id, limit=100, newest=True)
        self.record_count.setText(f"{total:,} record tersimpan")
        self._show_preview(records)

    def _export_path(self, extension: str) -> Path | None:
        if self.project_id is None:
            QMessageBox.information(
                self, "Tidak ada proyek", "Simpan atau pilih proyek sebelum mengekspor."
            )
            return None
        path, _ = QFileDialog.getSaveFileName(
            self, "Ekspor data", str(self.app_data / f"scrape{extension}"), f"*{extension}"
        )
        return Path(path) if path else None

    def _export_source(self) -> tuple[Iterator[dict[str, Any]], list[str]]:
        if self.project_id is None:
            return iter(()), []
        columns = [field.name for field in self._get_config().fields]
        return self.database.iter_project_records(self.project_id), columns

    def _export_excel(self) -> None:
        path = self._export_path(".xlsx")
        if path:
            config = self._get_config()
            records, columns = self._export_source()
            export_excel(records, path, config.start_url, config.name, columns=columns)
            self.statusBar().showMessage(f"Excel diekspor: {path}", 5000)

    def _export_csv(self) -> None:
        path = self._export_path(".csv")
        if path:
            records, columns = self._export_source()
            export_csv(records, path, columns=columns)
            self.statusBar().showMessage(f"CSV diekspor: {path}", 5000)

    def _export_json(self) -> None:
        path = self._export_path(".json")
        if path:
            records, _ = self._export_source()
            export_json(records, path)
            self.statusBar().showMessage(f"JSON diekspor: {path}", 5000)

    def closeEvent(self, event: object) -> None:
        self.worker.stop_job()
        self.worker.requestInterruption()
        if self.worker.isRunning():
            self.worker.wait(15_000)
        if self.worker.isRunning():
            QMessageBox.information(
                self,
                "Menunggu browser",
                "Operasi browser sedang diselesaikan. "
                "Tutup aplikasi kembali setelah proses berhenti.",
            )
            event.ignore()  # type: ignore[attr-defined]
            return
        self.database.close()
        super().closeEvent(event)  # type: ignore[arg-type]
