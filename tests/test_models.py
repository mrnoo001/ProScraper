from scraper_app.domain.models import FieldDefinition, PaginationConfig, ProjectConfig


def test_project_config_round_trip() -> None:
    config = ProjectConfig(
        name="Katalog",
        start_url="https://example.test/catalog",
        item_selector=".product",
        fields=[FieldDefinition("title", "h2"), FieldDefinition("price", ".price", mode="number")],
        pagination=PaginationConfig(
            mode="url", url_template="https://example.test/page/{page}", max_pages=8
        ),
        unique_field="title",
        request_delay_ms=750,
    )

    assert ProjectConfig.from_dict(config.to_dict()) == config


def test_project_config_reads_missing_optional_fields() -> None:
    config = ProjectConfig.from_dict({"name": "Draft", "start_url": "https://example.test"})

    assert config.item_selector == ""
    assert config.fields == []
    assert config.pagination.max_pages == 1
