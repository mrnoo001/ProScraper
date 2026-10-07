"""Selector-backed extraction helpers with explicit result validation."""

from __future__ import annotations

from typing import Any

from scraper_app.domain.models import FieldDefinition


def extract_records(
    page: Any, item_selector: str, fields: list[FieldDefinition]
) -> list[dict[str, Any]]:
    if not item_selector:
        raise ValueError("Pilih kontainer item terlebih dahulu.")
    if not fields:
        raise ValueError("Tambahkan setidaknya satu field sebelum menjalankan scraper.")
    return page.evaluate(
        """({itemSelector, fields}) => {
          const items = [...document.querySelectorAll(itemSelector)];
          return items.map(item => {
            const row = {};
            for (const field of fields) {
              const node = field.selector === ":scope" || item.matches(field.selector)
                ? item : item.querySelector(field.selector);
              if (!node) { row[field.name] = ""; continue; }
              const raw = field.attribute
                ? (["href", "src"].includes(field.attribute) && node.hasAttribute(field.attribute)
                    ? node[field.attribute]
                    : node.getAttribute(field.attribute))
                : node.innerText || node.textContent || "";
              const clean = String(raw || "").replace(/\\s+/g, " ").trim();
              if (field.mode === "number") {
                let normalized = clean.replace(/[^0-9,.-]/g, "");
                const comma = normalized.lastIndexOf(",");
                const dot = normalized.lastIndexOf(".");
                if (comma >= 0 && dot >= 0) {
                  normalized = comma > dot
                    ? normalized.replace(/\\./g, "").replace(",", ".")
                    : normalized.replace(/,/g, "");
                } else if (comma >= 0) {
                  normalized = normalized.length - comma - 1 <= 2
                    ? normalized.replace(",", ".")
                    : normalized.replace(/,/g, "");
                } else if (dot >= 0 && normalized.length - dot - 1 > 2) {
                  normalized = normalized.replace(/\\./g, "");
                }
                const parsed = Number(normalized);
                row[field.name] = Number.isFinite(parsed) ? parsed : clean;
              } else {
                row[field.name] = clean;
              }
            }
            return row;
          });
        }""",
        {
            "itemSelector": item_selector,
            "fields": [
                {"name": f.name, "selector": f.selector, "attribute": f.attribute, "mode": f.mode}
                for f in fields
            ],
        },
    )
