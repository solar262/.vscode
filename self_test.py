"""Self tests for TikTok browser launch/navigation behavior."""

from __future__ import annotations

import inspect

import tiktok_login_check as app


class FakePage:
    def __init__(self, initial_url="about:blank", stay_blank_once=False):
        self.url = initial_url
        self.stay_blank_once = stay_blank_once
        self.goto_calls = []

    def goto(self, url, *, wait_until="load", timeout=0):
        self.goto_calls.append((url, wait_until, timeout))
        if self.stay_blank_once and len(self.goto_calls) == 1:
            self.url = "about:blank"
        else:
            self.url = url


class FakeContext:
    def __init__(self, pages=None):
        self.pages = pages or []
        self.created = False

    def new_page(self):
        self.created = True
        page = FakePage()
        self.pages.append(page)
        return page


def test_navigates_first_page_to_tiktok_upload():
    page = FakePage()
    context = FakeContext([page])

    result = app.navigate_tiktok_upload(context)

    assert result is page
    assert page.goto_calls == [(app.TIKTOK_UPLOAD_URL, "domcontentloaded", 30000)]
    assert page.url == app.TIKTOK_UPLOAD_URL


def test_creates_page_when_context_has_no_pages():
    context = FakeContext()

    page = app.navigate_tiktok_upload(context)

    assert context.created
    assert context.pages[0] is page
    assert page.goto_calls == [(app.TIKTOK_UPLOAD_URL, "domcontentloaded", 30000)]


def test_forces_tiktok_when_startup_page_stays_blank_once():
    page = FakePage(stay_blank_once=True)
    context = FakeContext([page])

    app.navigate_tiktok_upload(context)

    assert page.goto_calls == [
        (app.TIKTOK_UPLOAD_URL, "domcontentloaded", 30000),
        (app.TIKTOK_UPLOAD_URL, "domcontentloaded", 30000),
    ]
    assert page.url == app.TIKTOK_UPLOAD_URL


def test_source_uses_required_persistent_context_settings():
    source = inspect.getsource(app.launch_tiktok_browser)

    assert "launch_persistent_context" in source
    assert "user_data_dir=BROWSER_PROFILE_DIR" in source
    assert "headless=False" in source
    assert "remote-debugging" not in source
    assert "page.pause" not in inspect.getsource(app)


def test_status_messages_are_exact():
    assert app.OPENING_STATUS == "Opening TikTok login/upload page..."
    assert app.OPENED_STATUS == "TikTok opened. Log in manually if needed."
    assert app.LOAD_FAILED_STATUS == "TikTok did not load. Close the browser and try again."


if __name__ == "__main__":
    tests = [
        test_navigates_first_page_to_tiktok_upload,
        test_creates_page_when_context_has_no_pages,
        test_forces_tiktok_when_startup_page_stays_blank_once,
        test_source_uses_required_persistent_context_settings,
        test_status_messages_are_exact,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} self tests passed")
