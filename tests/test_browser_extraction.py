from urllib.parse import quote

from playwright.sync_api import sync_playwright

from scraper_app.domain.models import FieldDefinition
from scraper_app.engine.worker import PICKER_PATH
from scraper_app.extraction.extractor import extract_records


def test_visual_picker_infers_repeated_items_and_extracts_values() -> None:
    html = """
      <head><base href="https://example.test/catalog/"></head>
      <main>
        <article data-testid="product">
          <a class="item-link" href="/item/alpha">
            <h2 class="title">Alpha</h2>
          </a>
          <span class="price">€1.299,99</span>
        </article>
        <article data-testid="product">
          <a class="item-link" href="/item/beta"><h2 class="title">Beta</h2></a>
          <span class="price">€29,50</span>
        </article>
        <article data-testid="product">
          <a class="item-link" href="/item/gamma"><h2 class="title">Gamma</h2></a>
          <span class="price">€8</span>
        </article>
      </main>
    """
    selected: list[dict] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        context.expose_binding("proscraperSelected", lambda _, data: selected.append(data))
        context.add_init_script(path=str(PICKER_PATH))
        page = context.new_page()
        page.goto(f"data:text/html,{quote(html)}")
        page.evaluate("window.__proscraperPicker.enable()")
        page.locator(".title").first.click()

        assert selected[0]["count"] == 3
        rows = extract_records(
            page,
            selected[0]["item_selector"],
            [
                FieldDefinition("title", selected[0]["field_selector"]),
                FieldDefinition("price", ".price", mode="number"),
                FieldDefinition("url", ".item-link", attribute="href"),
            ],
        )
        assert rows == [
            {"title": "Alpha", "price": 1299.99, "url": "https://example.test/item/alpha"},
            {"title": "Beta", "price": 29.5, "url": "https://example.test/item/beta"},
            {"title": "Gamma", "price": 8, "url": "https://example.test/item/gamma"},
        ]
        context.close()
        browser.close()
