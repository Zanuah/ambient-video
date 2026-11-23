"""Set the YouTube Studio fields the Data API cannot write.

Opens a visible browser, reuses a saved login, and clicks Save.
Automatic chapters, places, and concepts are left alone, so they stay checked.
"""

from __future__ import annotations

import re
import threading

from app.config import data_dir

_studio_lock = threading.Lock()
FIELD_WAIT_MS = 30_000
LOGIN_WAIT_MS = 300_000
SAVE_WAIT_MS = 60_000
NEVER_AIRED = re.compile(r"never aired on television", re.I)
LOCATION_QUERY = "San Antonio, Texas"


class StudioSettingsError(RuntimeError):
    """Studio did not save the location or the caption certification."""


def apply_studio_settings(video_id: str) -> None:
    from playwright.sync_api import sync_playwright

    profile = data_dir() / "studio-profile"
    profile.mkdir(parents=True, exist_ok=True)
    url = f"https://studio.youtube.com/video/{video_id}/edit"
    with _studio_lock:
        with sync_playwright() as playwright:
            context = _launch(playwright, profile)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(FIELD_WAIT_MS)
                _open_editor(page, url)
                _show_more(page)
                _set_english(page)
                _set_never_aired(page)
                _set_location(page)
                _save(page)
            finally:
                context.close()


def _launch(playwright, profile):
    options = {
        "headless": False,
        "viewport": {"width": 1400, "height": 1000},
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    try:
        return playwright.chromium.launch_persistent_context(str(profile), channel="chrome", **options)
    except Exception:
        return playwright.chromium.launch_persistent_context(str(profile), **options)


def _open_editor(page, url: str) -> None:
    page.goto(url, wait_until="domcontentloaded")
    if "accounts.google.com" in page.url or "signin" in page.url:
        page.wait_for_url(re.compile(r"studio\.youtube\.com/.*/edit"), timeout=LOGIN_WAIT_MS)
    try:
        page.wait_for_selector("#toggle-button, ytcp-video-title", timeout=FIELD_WAIT_MS)
    except Exception as exc:
        raise StudioSettingsError("YouTube Studio did not open the video. Sign in in the browser window and retry the upload.") from exc


def _show_more(page) -> None:
    advanced = page.locator("ytcp-video-metadata-editor-advanced")
    button = page.locator("#toggle-button")
    for _ in range(4):
        if advanced.count() and advanced.first.is_visible():
            advanced.first.scroll_into_view_if_needed()
            return
        if button.count() == 0:
            break
        button.first.click()
        page.wait_for_timeout(800)
    raise StudioSettingsError("Show more did not open the advanced settings.")


def _already_english(text: str) -> bool:
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    return any(line in {"English", "English (United States)"} for line in lines)


def _set_english(page) -> None:
    language = page.locator("ytcp-form-language-input, #language-input").first
    language.wait_for()
    if _already_english(language.inner_text()):
        return
    trigger = language.locator("ytcp-dropdown-trigger").first
    if trigger.count():
        trigger.click()
    else:
        page.get_by_text("Video language", exact=True).first.click()
    search = page.locator("ytcp-text-menu input, tp-yt-paper-dialog input").last
    if search.count() and search.is_visible():
        search.fill("English")
    items = page.locator("tp-yt-paper-item, [role='option']")
    items.first.wait_for()
    for index in range(items.count()):
        name = " ".join(items.nth(index).inner_text().split())
        if name == "English":
            items.nth(index).click()
            return
    raise StudioSettingsError("Could not choose English as the video language.")


def _set_never_aired(page) -> None:
    label = page.get_by_text(re.compile(r"Caption certification", re.I)).last
    label.wait_for()
    label.scroll_into_view_if_needed()
    block = label.locator(
        "xpath=ancestor::*[self::ytcp-form-select or self::ytcp-form-input-container or self::ytcp-dropdown-trigger][1]"
    )
    if block.count() == 0:
        block = label
    if NEVER_AIRED.search(block.inner_text() or ""):
        return
    opener = block.locator("ytcp-dropdown-trigger").first
    if opener.count():
        opener.click()
    else:
        block.click()
    choice = page.locator("tp-yt-paper-item, [role='option']").filter(has_text=NEVER_AIRED).first
    choice.wait_for()
    choice.click()


def _set_location(page) -> None:
    field = page.locator(
        "ytcp-video-metadata-editor-advanced #location input, "
        "ytcp-video-metadata-editor-advanced input[aria-label*='ocation' i], "
        "input[aria-label='Video location'], "
        "input[placeholder*='ocation' i]"
    ).first
    field.wait_for()
    field.scroll_into_view_if_needed()
    if "San Antonio" in (field.input_value() or ""):
        return
    field.click()
    field.fill(LOCATION_QUERY)
    suggestion = page.locator("tp-yt-paper-item, [role='option']").filter(
        has_text=re.compile(r"San Antonio", re.I)
    ).first
    suggestion.wait_for()
    suggestion.click()


def _save_disabled(save) -> bool:
    return bool(
        save.evaluate(
            """(node) => node.hasAttribute('disabled') || node.getAttribute('aria-disabled') === 'true'"""
        )
    )


def _save(page) -> None:
    save = page.locator("#save-button, ytcp-button#save").first
    save.wait_for()
    if _save_disabled(save):
        return
    save.click()
    try:
        page.wait_for_function(
            """() => {
              const button = document.querySelector('#save-button, ytcp-button#save');
              if (!button) return false;
              return button.hasAttribute('disabled') || button.getAttribute('aria-disabled') === 'true';
            }""",
            timeout=SAVE_WAIT_MS,
        )
    except Exception as exc:
        raise StudioSettingsError("YouTube Studio did not confirm the save.") from exc
