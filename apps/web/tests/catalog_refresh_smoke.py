"""Real-library browser smoke for non-blocking persistent catalog refresh."""

from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright


WEB_URL = os.environ.get("LBC_WEB_URL", "http://localhost:3000")
API_URL = os.environ.get("LBC_API_URL", "http://localhost:8000")
OUTPUT_DIR = Path(
    os.environ.get("LBC_CATALOG_OUTPUT_DIR", r"L:\caches\temp\lbc-catalog-smoke")
)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    page_errors: list[str] = []
    console_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        page.set_default_timeout(120_000)
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )

        # Seed both SQL snapshots before the browser starts parallel shelf requests.
        books = page.request.get(f"{API_URL}/v1/library/local?limit=1")
        audio = page.request.get(f"{API_URL}/v1/audiobooks?limit=1")
        assert books.ok and books.json()["catalog_total"] > 30_000
        assert audio.ok and audio.json()["total_tracks"] > 15_000

        response = page.goto(WEB_URL, wait_until="domcontentloaded")
        assert response is not None and response.ok
        page.get_by_text("Your library", exact=True).wait_for()
        refresh = page.get_by_role("button", name="Refresh shelf")
        refresh.wait_for()
        before = page.request.get(f"{API_URL}/v1/library/catalog/status").json()
        before_generation = {
            catalog["kind"]: catalog["generation"]
            for catalog in before["catalogs"]
        }

        refresh.click()
        page.get_by_role("button", name="Refreshing in background…").wait_for()
        page.get_by_text("Shelf refreshed", exact=False).wait_for(timeout=180_000)
        page.get_by_role("button", name="Refresh shelf").wait_for()

        after = page.request.get(f"{API_URL}/v1/library/catalog/status").json()
        assert all(catalog["status"] == "idle" for catalog in after["catalogs"])
        assert all(
            catalog["generation"] > before_generation[catalog["kind"]]
            for catalog in after["catalogs"]
        )
        page.screenshot(path=str(OUTPUT_DIR / "persistent-catalog-refresh.png"), full_page=True)

        ignored = [
            message
            for message in console_errors
            if "favicon" not in message.casefold()
        ]
        assert not page_errors, page_errors
        assert not ignored, ignored
        browser.close()

    print(f"catalog refresh smoke passed; screenshot: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
