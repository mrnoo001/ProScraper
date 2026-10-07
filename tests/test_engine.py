from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

from scraper_app.domain.models import FieldDefinition, ProjectConfig
from scraper_app.engine.worker import BrowserWorker
from scraper_app.storage.database import Database


def test_scrape_job_persists_rows_and_finishes(tmp_path: Path) -> None:
    html = """
      <head><base href="https://example.test/catalog/"></head>
      <article class="product"><h2>Alpha</h2><a href="/alpha">Open</a></article>
      <article class="product"><h2>Beta</h2><a href="/beta">Open</a></article>
    """
    database = Database(tmp_path / "engine.db")
    config = ProjectConfig(
        name="Fixture",
        start_url=f"data:text/html,{quote(html)}",
        item_selector=".product",
        fields=[
            FieldDefinition("title", "h2"),
            FieldDefinition("url", "a", attribute="href"),
        ],
        unique_field="url",
    )
    project_id = database.save_project(None, config)
    worker = BrowserWorker(database, tmp_path / "browser-profile")
    finished: list[tuple[bool, str]] = []
    worker.job_finished.connect(lambda success, message: finished.append((success, message)))

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(config.start_url)
            worker._page = page
            worker._scrape({"project_id": project_id, "config": config, "resume": False})

            assert finished and finished[0][0] is True
            assert database.project_records(project_id) == [
                {"title": "Alpha", "url": "https://example.test/alpha"},
                {"title": "Beta", "url": "https://example.test/beta"},
            ]
            browser.close()
    finally:
        database.close()
