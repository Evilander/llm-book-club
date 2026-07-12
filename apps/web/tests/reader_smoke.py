"""Browser smoke test for the local-library reader.

Run with the API and web app available on localhost and set LBC_TEST_EPUB.
Optional LBC_TEST_AZW3, LBC_TEST_FB2, LBC_TEST_CBZ, and LBC_TEST_PDF paths
exercise the additional renderers used by a mixed personal library.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import Page, sync_playwright


WEB_URL = os.environ.get("LBC_WEB_URL", "http://localhost:3000")
OUTPUT_DIR = Path(tempfile.gettempdir()) / "lbc-reader-smoke"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def reader_url(path: str, renderer: str, *, can_discuss: bool) -> str:
    extension = Path(path).suffix.lstrip(".").lower()
    query = urlencode(
        {
            "path": path,
            "title": Path(path).stem,
            "format": extension,
            "renderer": renderer,
            "canDiscuss": str(can_discuss).lower(),
        }
    )
    return f"{WEB_URL}/read?{query}"


def wait_for_reader(page: Page, timeout: int = 60_000) -> None:
    try:
        page.locator(".reader-shell").wait_for(state="visible", timeout=timeout)
    except Exception:
        print(f"Reader did not mount at {page.url}")
        page.screenshot(path=str(OUTPUT_DIR / "reader-mount-failure.png"), full_page=True)
        body_text = page.locator("body").inner_text()[:1200]
        print(body_text.encode("ascii", errors="backslashreplace").decode())
        raise
    page.locator(".reader-loading-state").wait_for(state="hidden", timeout=timeout)
    assert page.locator(".reader-error-state").count() == 0


def select_publication_text(page: Page, quote: str) -> str:
    return page.evaluate(
        """quote => {
            const view = document.querySelector('foliate-view');
            const contents = view?.renderer?.getContents?.() || [];
            for (const { doc } of contents) {
                const walker = doc.createTreeWalker(
                    doc.body,
                    doc.defaultView.NodeFilter.SHOW_TEXT,
                );
                for (let node = walker.nextNode(); node; node = walker.nextNode()) {
                    const start = node.nodeValue?.indexOf(quote) ?? -1;
                    if (start < 0) continue;
                    const range = doc.createRange();
                    range.setStart(node, start);
                    range.setEnd(node, start + quote.length);
                    const selection = doc.getSelection();
                    selection.removeAllRanges();
                    selection.addRange(range);
                    doc.dispatchEvent(new doc.defaultView.MouseEvent('mouseup', {
                        bubbles: true,
                    }));
                    return selection.toString();
                }
            }
            return '';
        }""",
        quote,
    )


def open_direct(
    page: Page,
    *,
    path: str,
    renderer: str,
    screenshot_name: str,
    can_discuss: bool = False,
) -> None:
    page.goto(
        reader_url(path, renderer, can_discuss=can_discuss),
        wait_until="domcontentloaded",
    )
    wait_for_reader(page)
    page.screenshot(path=str(OUTPUT_DIR / screenshot_name), full_page=True)


def search_book(
    page: Page,
    query: str,
    screenshot_name: str,
    active_selector: str | None = None,
) -> str:
    page.keyboard.press("Control+f")
    search_input = page.get_by_label("Search text")
    search_input.wait_for(state="visible")
    search_input.fill(query)
    search_input.press("Enter")
    first_result = page.locator(".reader-search-results > button").first
    first_result.wait_for(state="visible")
    result_text = first_result.inner_text()
    assert query.lower() in result_text.lower()
    first_result.click()
    page.wait_for_timeout(600)
    if active_selector:
        page.locator(active_selector).first.wait_for(state="visible")
    page.screenshot(path=str(OUTPUT_DIR / screenshot_name), full_page=True)
    page.get_by_role("button", name="Close search").click()
    return result_text


def main() -> None:
    epub_path = os.environ["LBC_TEST_EPUB"]
    azw3_path = os.environ.get("LBC_TEST_AZW3")
    fb2_path = os.environ.get("LBC_TEST_FB2")
    cbz_path = os.environ.get("LBC_TEST_CBZ")
    pdf_path = os.environ.get("LBC_TEST_PDF")
    epub_search_term = os.environ.get("LBC_TEST_EPUB_SEARCH")
    pdf_search_term = os.environ.get("LBC_TEST_PDF_SEARCH")
    txt_path = os.environ.get("LBC_TEST_TXT")
    txt_search_term = os.environ.get("LBC_TEST_TXT_SEARCH")
    focus_ready = os.environ.get("LBC_TEST_FOCUS_READY") == "true"

    console_errors: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        page.set_default_timeout(60_000)
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.on(
            "pageerror",
            lambda error: page_errors.append(
                f"{error}\n{getattr(error, 'stack', '') or ''}"
            ),
        )

        # Enter through the real shelf so this also covers catalog search and
        # the local-book -> reader handoff.
        response = page.goto(WEB_URL, wait_until="domcontentloaded")
        assert response is not None and response.ok
        page.get_by_text("Your library", exact=True).wait_for(state="visible")
        search = page.locator('input[placeholder^="Search"]')
        search.fill(Path(epub_path).stem[:24])
        local_card = page.get_by_test_id("local-book-card").first
        local_card.wait_for(state="visible")
        local_card.get_by_text("Dan Harris", exact=True).wait_for(state="visible")
        cover = local_card.locator("img")
        cover.wait_for(state="attached")
        page.wait_for_function(
            "image => image.complete && image.naturalWidth > 1",
            arg=cover.element_handle(),
        )
        page.wait_for_timeout(700)
        page.screenshot(path=str(OUTPUT_DIR / "library-search.png"), full_page=True)
        local_card.click()
        page.wait_for_url("**/read?**")

        # Reader routes use explicit UI readiness because publication blob
        # activity can intentionally keep the network busy.
        csp_response = page.request.get(page.url)
        assert csp_response.ok
        assert "script-src" in (csp_response.headers.get("content-security-policy") or "")
        wait_for_reader(page, timeout=30_000)
        page.locator("foliate-view:visible").wait_for(state="visible")
        assert page.locator("foliate-view:visible").count() == 1
        assert page.get_by_text("The margin", exact=True).count() >= 1
        page.screenshot(path=str(OUTPUT_DIR / "epub-paper.png"), full_page=True)

        if epub_search_term:
            search_book(page, epub_search_term, "epub-search.png")

            highlight_quote = "Nielsen ratings data"
            assert select_publication_text(page, highlight_quote) == highlight_quote
            page.wait_for_timeout(500)
            assert page.locator(".reader-selection-card").is_visible(), (
                f"Selection did not reach the margin; page errors: {page_errors}"
            )
            assert (
                page.locator(".reader-selection-card blockquote").inner_text()
                == highlight_quote
            )
            page.get_by_role("button", name="Keep in the margin").click()
            saved_highlight = page.locator(".reader-saved-notes blockquote").filter(
                has_text=highlight_quote
            )
            saved_highlight.wait_for(state="visible")
            page.wait_for_function(
                """() => {
                    const view = document.querySelector('foliate-view');
                    return (view?.renderer?.getContents?.() || []).some(
                        ({ overlayer }) => overlayer?.element?.querySelector('g'),
                    );
                }"""
            )

        page.get_by_role("button", name="Mark", exact=True).click()
        page.get_by_text("Page marked", exact=True).wait_for(state="visible")

        page.get_by_role("button", name="Type").click()
        page.get_by_role("button", name="Night").click()
        page.screenshot(path=str(OUTPUT_DIR / "epub-night.png"), full_page=True)
        page.get_by_role("button", name="Type").click()

        note = "The opening cadence is worth returning to."
        page.get_by_placeholder("Leave yourself a thought…").fill(note)
        page.get_by_role("button", name="Keep in the margin").click()
        assert page.get_by_text(note, exact=True).is_visible()
        page.locator(
            '[data-testid="reader-sync-status"][data-status="synced"]'
        ).wait_for(state="visible")
        # The custom reader keeps blob-backed publication activity alive, so
        # a reload may never reach Playwright's strict network-idle heuristic.
        page.reload(wait_until="domcontentloaded")
        wait_for_reader(page)
        assert page.get_by_text(note, exact=True).is_visible()
        assert page.get_by_text("Page marked", exact=True).is_visible()
        if epub_search_term:
            highlight_rects = page.wait_for_function(
                """() => {
                    const view = document.querySelector('foliate-view');
                    const count = (view?.renderer?.getContents?.() || []).reduce(
                        (total, { overlayer }) => total
                            + (overlayer?.element?.querySelectorAll('g rect').length || 0),
                        0,
                    );
                    return count > 0 ? count : false;
                }"""
            ).json_value()
            saved_targets = page.evaluate(
                """() => Object.keys(localStorage)
                    .filter(key => key.startsWith('lbc-reader-notes-'))
                    .flatMap(key => JSON.parse(localStorage.getItem(key) || '[]'))
                    .map(note => note.target)"""
            )
            assert 1 <= highlight_rects <= 6, (
                "Expected a phrase-sized highlight, found "
                f"{highlight_rects} rectangles for {saved_targets}"
            )
        page.screenshot(path=str(OUTPUT_DIR / "epub-marks.png"), full_page=True)
        with page.expect_download() as download_info:
            page.locator('button[title="Export all marks as Markdown"]').click()
        assert download_info.value.suggested_filename.endswith(" - notes.md")

        if epub_search_term:
            synced_reader_url = page.url
            second_context = browser.new_context(viewport={"width": 1440, "height": 960})
            second_page = second_context.new_page()
            second_page.set_default_timeout(60_000)
            second_page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            second_page.on(
                "pageerror",
                lambda error: page_errors.append(
                    f"second profile: {error}\n{getattr(error, 'stack', '') or ''}"
                ),
            )
            second_page.goto(synced_reader_url, wait_until="domcontentloaded")
            wait_for_reader(second_page)
            second_page.locator(
                '[data-testid="reader-sync-status"][data-status="synced"]'
            ).wait_for(state="visible")
            assert second_page.get_by_text(note, exact=True).is_visible()
            assert second_page.get_by_text("Page marked", exact=True).is_visible()
            assert "reader-theme-night" in (
                second_page.locator(".reader-shell").get_attribute("class") or ""
            )
            assert "opening" not in second_page.locator(".reader-kicker").inner_text().lower()
            second_highlight_rects = second_page.wait_for_function(
                """() => {
                    const view = document.querySelector('foliate-view');
                    const count = (view?.renderer?.getContents?.() || []).reduce(
                        (total, { overlayer }) => total
                            + (overlayer?.element?.querySelectorAll('g rect').length || 0),
                        0,
                    );
                    return count > 0 ? count : false;
                }"""
            ).json_value()
            assert 1 <= second_highlight_rects <= 6
            second_page.goto(WEB_URL, wait_until="domcontentloaded")
            second_page.get_by_text("Your library", exact=True).wait_for(state="visible")
            second_page.get_by_test_id("reading-history-card").first.wait_for(
                state="visible"
            )
            assert second_page.get_by_text("Continue reading", exact=True).is_visible()
            second_page.wait_for_timeout(1200)
            second_page.screenshot(
                path=str(OUTPUT_DIR / "cross-browser-profile.png"),
                full_page=True,
            )
            second_context.close()

        page.locator('button[title="Back to your library"]').click()
        page.wait_for_url(WEB_URL + "/")
        history_card = page.get_by_test_id("reading-history-card").first
        history_card.wait_for(state="visible")
        history_cover = history_card.locator("img")
        history_cover.wait_for(state="attached")
        page.wait_for_function(
            "image => image.complete && image.naturalWidth > 1",
            arg=history_cover.element_handle(),
        )
        assert page.get_by_text("Continue reading", exact=True).is_visible()
        page.wait_for_timeout(900)
        page.screenshot(path=str(OUTPUT_DIR / "continue-reading.png"), full_page=True)
        history_card.click()
        page.wait_for_url("**/read?**")
        wait_for_reader(page)

        if focus_ready:
            focus_quote = (
                "the Nielsen ratings data, 5.019 million people saw me lose my mind."
            )
            selected = select_publication_text(page, focus_quote)
            assert selected == focus_quote
            page.get_by_text(focus_quote, exact=True).wait_for(state="visible")
            question = "Why begin the chapter with public humiliation?"
            page.get_by_placeholder("What did you notice?").fill(question)
            page.get_by_role("button", name="Discuss this passage").click()
            page.wait_for_url("**/books/**?from=reader&focus=1")
            focus_card = page.get_by_test_id("discussion-focus-card")
            focus_card.wait_for(state="visible")
            assert focus_card.get_by_text(focus_quote, exact=False).is_visible()
            assert focus_card.get_by_text(question, exact=True).is_visible()
            page.wait_for_timeout(500)
            page.screenshot(path=str(OUTPUT_DIR / "passage-handoff.png"), full_page=True)
            page.go_back(wait_until="domcontentloaded")
            wait_for_reader(page)

        if azw3_path:
            open_direct(
                page,
                path=azw3_path,
                renderer="foliate",
                screenshot_name="azw3.png",
                can_discuss=True,
            )
            page.locator("foliate-view:visible").wait_for(state="visible")
            assert page.locator("foliate-view:visible").count() == 1
            assert page.get_by_role("button", name="Prepare the AI room").is_visible()

        if fb2_path:
            open_direct(
                page,
                path=fb2_path,
                renderer="foliate",
                screenshot_name="fb2.png",
                can_discuss=True,
            )
            page.locator("foliate-view:visible").wait_for(state="visible")
            assert page.get_by_role("button", name="Prepare the AI room").is_visible()

        if cbz_path:
            open_direct(
                page,
                path=cbz_path,
                renderer="foliate",
                screenshot_name="cbz.png",
            )
            page.locator("foliate-view:visible").wait_for(state="visible")
            assert page.locator("foliate-view:visible").count() == 1

        if pdf_path:
            open_direct(
                page,
                path=pdf_path,
                renderer="pdf",
                screenshot_name="pdf.png",
                can_discuss=True,
            )
            assert page.locator(".pdf-reader-host canvas").count() == 1
            assert page.locator(".pdf-reader-controls").is_visible()
            if pdf_search_term:
                result_text = search_book(
                    page,
                    pdf_search_term,
                    "pdf-search.png",
                    ".pdf-search-hit",
                )
                assert result_text.lower().startswith("page ")

        if txt_path:
            open_direct(
                page,
                path=txt_path,
                renderer="text",
                screenshot_name="txt.png",
                can_discuss=True,
            )
            assert page.locator(".text-reader-page").is_visible()
            if txt_search_term:
                search_book(
                    page,
                    txt_search_term,
                    "txt-search.png",
                    ".text-search-hit",
                )

        browser.close()

    ignored_console_fragments = (
        "Download the React DevTools",
        "favicon.ico",
    )
    actionable_console_errors = [
        message
        for message in console_errors
        if not any(fragment in message for fragment in ignored_console_fragments)
    ]
    assert not page_errors, f"Page errors: {page_errors}"
    assert not actionable_console_errors, f"Console errors: {actionable_console_errors}"
    print(f"reader smoke passed; screenshots: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
