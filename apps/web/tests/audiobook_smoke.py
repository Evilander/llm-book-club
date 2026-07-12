"""Real-browser audiobook library, playback, and cross-profile resume smoke test."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import Page, sync_playwright


WEB_URL = os.environ.get("LBC_WEB_URL", "http://localhost:3000")
API_URL = os.environ.get("LBC_API_URL", "http://localhost:8000")
OUTPUT_DIR = Path(
    os.environ.get("LBC_AUDIOBOOK_OUTPUT_DIR", r"L:\caches\temp\lbc-audiobook-smoke")
)
BOOK_PATH = os.environ.get(
    "LBC_AUDIOBOOK_EBOOK",
    r"D:\Books\Nixaly Leonardo - Active Listening Techniques.epub",
)


def wait_for_audio_metadata(page: Page) -> None:
    page.wait_for_function(
        """() => {
            const audio = document.querySelector('[data-testid="audiobook-audio"]');
            return audio && audio.readyState >= 1 && Number.isFinite(audio.duration) && audio.duration > 0;
        }""",
        timeout=30_000,
    )


def set_audio_position(page: Page, seconds: float) -> None:
    page.locator('[data-testid="audiobook-audio"]').evaluate(
        """(audio, position) => {
            audio.currentTime = Math.min(position, Math.max(0, audio.duration - 0.5));
            audio.dispatchEvent(new Event('timeupdate'));
            audio.dispatchEvent(new Event('pause'));
        }""",
        seconds,
    )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    page_errors: list[str] = []
    audio_api_events: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        first_context = browser.new_context(viewport={"width": 1440, "height": 960})
        page = first_context.new_page()
        page.set_default_timeout(60_000)
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on(
            "response",
            lambda response: audio_api_events.append(
                f"response {response.status} {response.url}"
            )
            if "/v1/audiobooks" in response.url
            else None,
        )
        page.on(
            "requestfailed",
            lambda request: audio_api_events.append(
                f"failed {request.url} {request.failure}"
            )
            if "/v1/audiobooks" in request.url
            else None,
        )

        catalog_probe = page.request.get(
            f"{API_URL}/v1/audiobooks?search=Active%20Listening%20Techniques&limit=1"
        )
        assert catalog_probe.ok
        assert catalog_probe.json()["audiobooks"][0]["track_count"] == 42

        response = page.goto(f"{WEB_URL}/listen", wait_until="domcontentloaded")
        assert response is not None and response.ok
        page.get_by_role("heading", name="Let the shelf read to you.").wait_for()
        search = page.get_by_placeholder("Search titles, authors, or folders…")
        search.fill("Active Listening Techniques")
        card = page.get_by_test_id("audiobook-card").first
        try:
            card.wait_for(state="visible")
        except Exception:
            print("AUDIO_API_EVENTS", audio_api_events)
            print("PAGE_ERRORS", page_errors)
            print("CONSOLE_ERRORS", console_errors)
            print("BODY", page.locator("body").inner_text())
            raise
        card.get_by_text("Active Listening Techniques", exact=False).wait_for()
        card.get_by_text("42 tracks", exact=False).wait_for()
        page.screenshot(path=str(OUTPUT_DIR / "audio-library.png"), full_page=True)

        card.click()
        page.wait_for_url("**/listen?audioId=**")
        page.get_by_text("Active Listening Techniques", exact=True).first.wait_for()
        page.get_by_text("Nixaly Leonardo", exact=False).first.wait_for()
        assert page.get_by_test_id("audiobook-track").count() == 42
        wait_for_audio_metadata(page)

        audio_url = page.get_by_test_id("audiobook-audio").get_attribute("src")
        assert audio_url and "/v1/audiobooks/" in audio_url
        ranged = page.request.get(audio_url, headers={"Range": "bytes=0-31"})
        assert ranged.status == 206
        assert ranged.headers["accept-ranges"] == "bytes"
        assert len(ranged.body()) == 32

        page.get_by_role("button", name="Play").click()
        page.get_by_role("button", name="Pause").wait_for()
        page.get_by_role("button", name="Pause").click()
        page.get_by_role("button", name="1.25×").click()
        page.get_by_test_id("audiobook-track").nth(1).click()
        wait_for_audio_metadata(page)
        set_audio_position(page, 5.5)
        page.locator('[data-testid="audiobook-sync-status"][data-status="synced"]').wait_for()
        page.screenshot(path=str(OUTPUT_DIR / "audio-player.png"), full_page=True)

        player_url = page.url
        assert "audioId=" in player_url
        first_context.close()

        second_context = browser.new_context(viewport={"width": 1440, "height": 960})
        second_page = second_context.new_page()
        second_page.set_default_timeout(60_000)
        second_page.on(
            "console",
            lambda message: console_errors.append(f"second profile: {message.text}")
            if message.type == "error"
            else None,
        )
        second_page.on(
            "pageerror", lambda error: page_errors.append(f"second profile: {error}")
        )
        response = second_page.goto(player_url, wait_until="domcontentloaded")
        assert response is not None and response.ok
        wait_for_audio_metadata(second_page)
        restored = second_page.get_by_test_id("audiobook-audio").evaluate(
            "audio => ({ time: audio.currentTime, rate: audio.playbackRate })"
        )
        assert restored["time"] >= 4.5, restored
        assert abs(restored["rate"] - 1.25) < 0.01, restored
        second_page.get_by_text("Publisher's Note", exact=True).first.wait_for()
        second_page.get_by_role(
            "heading", name="Active Listening Techniques", exact=True
        ).wait_for()
        second_page.locator(
            '[data-testid="audiobook-sync-status"][data-status="synced"]'
        ).wait_for()
        second_page.wait_for_timeout(700)
        second_page.screenshot(
            path=str(OUTPUT_DIR / "cross-browser-audio-resume.png"), full_page=True
        )
        second_page.get_by_role("button", name="Audio library").click()
        second_page.wait_for_url(f"{WEB_URL}/listen")
        second_page.get_by_test_id("continue-listening-card").first.wait_for()

        reader_query = urlencode(
            {
                "path": BOOK_PATH,
                "title": "Active Listening Techniques",
                "author": "Nixaly Leonardo",
                "format": "epub",
                "renderer": "foliate",
                "canDiscuss": "true",
            }
        )
        response = second_page.goto(
            f"{WEB_URL}/read?{reader_query}", wait_until="domcontentloaded"
        )
        assert response is not None and response.ok
        match = second_page.get_by_test_id("reader-audiobook-match")
        match.wait_for(state="visible")
        match.get_by_text("42 tracks", exact=False).wait_for()
        match.get_by_role("button", name="Continue in the listening room").click()
        second_page.wait_for_url("**/listen?audioId=**")
        second_page.get_by_role("button", name="Return to the book").wait_for()

        assert not page_errors, page_errors
        ignored_console_errors = [
            message
            for message in console_errors
            if "favicon" not in message.lower()
        ]
        assert not ignored_console_errors, ignored_console_errors
        second_context.close()
        browser.close()

    print(f"audiobook smoke passed; screenshots: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
