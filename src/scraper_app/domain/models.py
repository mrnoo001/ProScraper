"""Typed project and extraction configuration models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

PaginationMode = Literal["none", "click", "url", "infinite"]
ExtractionMode = Literal["text", "number"]


@dataclass(slots=True)
class FieldDefinition:
    name: str
    selector: str
    attribute: str = ""
    mode: ExtractionMode = "text"


@dataclass(slots=True)
class PaginationConfig:
    mode: PaginationMode = "none"
    selector: str = ""
    url_template: str = ""
    max_pages: int = 1


@dataclass(slots=True)
class ProjectConfig:
    name: str
    start_url: str
    item_selector: str = ""
    fields: list[FieldDefinition] = field(default_factory=list)
    pagination: PaginationConfig = field(default_factory=PaginationConfig)
    unique_field: str = ""
    request_delay_ms: int = 1200

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ProjectConfig:
        fields_data = data.get("fields", [])
        pagination_data = data.get("pagination", {})
        return cls(
            name=str(data.get("name", "Untitled project")),
            start_url=str(data.get("start_url", "")),
            item_selector=str(data.get("item_selector", "")),
            fields=[
                FieldDefinition(
                    name=str(item.get("name", "")),
                    selector=str(item.get("selector", "")),
                    attribute=str(item.get("attribute", "")),
                    mode=str(item.get("mode", "text")),  # type: ignore[arg-type]
                )
                for item in fields_data
                if isinstance(item, dict)
            ],
            pagination=PaginationConfig(
                mode=str(pagination_data.get("mode", "none")),  # type: ignore[union-attr,arg-type]
                selector=str(pagination_data.get("selector", "")),  # type: ignore[union-attr]
                url_template=str(pagination_data.get("url_template", "")),  # type: ignore[union-attr]
                max_pages=int(pagination_data.get("max_pages", 1)),  # type: ignore[union-attr]
            ),
            unique_field=str(data.get("unique_field", "")),
            request_delay_ms=int(data.get("request_delay_ms", 1200)),
        )
