"""Formatted, streaming Excel, CSV, and JSON exports."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import xlsxwriter

EXCEL_DATA_ROWS = 1_048_575


def _prepare_rows(
    records: Iterable[dict[str, Any]], columns: Sequence[str] | None
) -> tuple[list[str], Iterator[dict[str, Any]]]:
    iterator = iter(records)
    first = next(iterator, None)
    names = list(columns) if columns is not None else list(first) if first is not None else []

    def rows() -> Iterator[dict[str, Any]]:
        if first is not None:
            yield first
        yield from iterator

    return names, rows()


def export_excel(
    records: Iterable[dict[str, Any]],
    destination: Path,
    source_url: str,
    project_name: str,
    errors: int = 0,
    columns: Sequence[str] | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    names, rows = _prepare_rows(records, columns)
    workbook = xlsxwriter.Workbook(str(destination), {"constant_memory": True})
    header_format = workbook.add_format(
        {
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": "#5142C5",
            "bottom": 1,
            "bottom_color": "#392D9A",
        }
    )
    date_format = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm"})

    def new_data_sheet(sheet_number: int) -> tuple[Any, list[int]]:
        sheet = workbook.add_worksheet(f"Data {sheet_number}")
        sheet.freeze_panes(1, 0)
        for column_index, name in enumerate(names):
            sheet.write_string(0, column_index, name, header_format)
        return sheet, [min(max(len(name), 12), 48) for name in names]

    sheet_number = 1
    sheet, widths = new_data_sheet(sheet_number)
    row_in_sheet = 0
    total_records = 0
    for record in rows:
        if row_in_sheet == EXCEL_DATA_ROWS:
            sheet.autofilter(0, 0, row_in_sheet, max(len(names) - 1, 0))
            for column_index, width in enumerate(widths):
                sheet.set_column(column_index, column_index, width)
            sheet_number += 1
            sheet, widths = new_data_sheet(sheet_number)
            row_in_sheet = 0
        for column_index, name in enumerate(names):
            value = record.get(name, "")
            cell_row = row_in_sheet + 1
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                sheet.write_number(cell_row, column_index, value)
            elif isinstance(value, datetime):
                sheet.write_datetime(cell_row, column_index, value, date_format)
            else:
                text = str(value) if value is not None else ""
                parsed_url = urlsplit(text)
                is_url = parsed_url.scheme in ("http", "https") and parsed_url.netloc
                if is_url and len(text) <= 2079:
                    sheet.write_url(cell_row, column_index, text, string=text)
                else:
                    sheet.write_string(cell_row, column_index, text)
                widths[column_index] = min(max(widths[column_index], len(text) + 2), 48)
        row_in_sheet += 1
        total_records += 1

    sheet.autofilter(0, 0, row_in_sheet, max(len(names) - 1, 0))
    for column_index, width in enumerate(widths):
        sheet.set_column(column_index, column_index, width)

    summary = workbook.add_worksheet("Ringkasan")
    summary.set_column("A:A", 24)
    summary.set_column("B:B", 72)
    summary.write_row(0, 0, ["Informasi", "Nilai"], header_format)
    summary.write_row(1, 0, ["Proyek", project_name])
    summary.write_row(2, 0, ["Sumber URL", source_url])
    summary.write_row(3, 0, ["Waktu ekspor (UTC)", datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")])
    summary.write_row(4, 0, ["Jumlah record", total_records])
    summary.write_row(5, 0, ["Jumlah error", errors])
    workbook.close()
    return destination


def export_csv(
    records: Iterable[dict[str, Any]], destination: Path, columns: Sequence[str] | None = None
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    names, rows = _prepare_rows(records, columns)
    with destination.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=names, extrasaction="ignore")
        if names:
            writer.writeheader()
            writer.writerows(_safe_csv_row(row) for row in rows)
    return destination


def _safe_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
            safe[key] = f"'{value}"
        else:
            safe[key] = value
    return safe


def export_json(records: Iterable[dict[str, Any]], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as stream:
        stream.write("[")
        first = True
        for row in records:
            if not first:
                stream.write(",")
            stream.write("\n")
            json.dump(row, stream, ensure_ascii=False, indent=2)
            first = False
        if not first:
            stream.write("\n")
        stream.write("]\n")
    return destination
