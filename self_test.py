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


def test_import_recent_downloads_copies_to_queue_and_records_manifest(tmp_root=None):
    import tempfile
    from pathlib import Path

    import postpilot_local as pp

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        downloads = root / "Downloads"
        inbox = root / "app" / "data" / "inbox"
        imported = root / "app" / "data" / "imported_posts.json"
        downloads.mkdir()
        newest = downloads / "meta_ai_new.mp4"
        older = downloads / "meta_ai_old.mp4"
        newest.write_bytes(b"new video")
        older.write_bytes(b"old video")
        import os
        os.utime(older, (100, 100))
        os.utime(newest, (200, 200))

        candidates = pp.scan_recent_downloads(downloads)
        assert [candidate.path.name for candidate in candidates] == ["meta_ai_new.mp4", "meta_ai_old.mp4"]

        manifest = pp.import_video_to_queue(newest, pp.BRANDS["1"], inbox, imported)

        copied = inbox / "hairhub_external_001.mp4"
        sidecar = inbox / "hairhub_external_001.json"
        assert copied.exists()
        assert copied.read_bytes() == b"new video"
        assert sidecar.exists()
        assert manifest["caption"] == pp.BRANDS["1"].caption
        assert manifest["website"] == pp.BRANDS["1"].website
        assert pp.read_json_list(imported)[0]["filename"] == "hairhub_external_001.mp4"


def test_import_recent_downloads_prompt_flow_and_queue_upload():
    import tempfile
    from pathlib import Path

    import postpilot_local as pp

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        downloads = root / "Downloads"
        downloads.mkdir()
        first = downloads / "clip_a.mp4"
        second = downloads / "clip_b.mp4"
        first.write_bytes(b"a")
        second.write_bytes(b"b")

        old_inbox = pp.INBOX_DIR
        old_imported = pp.IMPORTED_POSTS_PATH
        pp.INBOX_DIR = root / "app" / "data" / "inbox"
        pp.IMPORTED_POSTS_PATH = root / "app" / "data" / "imported_posts.json"
        outputs = []
        answers = iter(["all", "1", "2"])
        try:
            imported_count = pp.import_recent_downloads(
                downloads,
                input_fn=lambda _prompt: next(answers),
                print_fn=outputs.append,
            )
            queue = pp.load_queue(pp.INBOX_DIR)
            uploaded = pp.upload_next_post(print_fn=outputs.append)
        finally:
            pp.INBOX_DIR = old_inbox
            pp.IMPORTED_POSTS_PATH = old_imported

        assert imported_count == 2
        assert "Imported 2 videos into queue." in outputs
        assert {item["brand"] for item in queue} == {"HairHub", "Beans Perfeto"}
        assert uploaded is not None
        assert uploaded["caption"] in {pp.BRANDS["1"].caption, pp.BRANDS["2"].caption}
        assert uploaded["website"] in {pp.BRANDS["1"].website, pp.BRANDS["2"].website}


if __name__ == "__main__":
    tests = [
        test_navigates_first_page_to_tiktok_upload,
        test_creates_page_when_context_has_no_pages,
        test_forces_tiktok_when_startup_page_stays_blank_once,
        test_source_uses_required_persistent_context_settings,
        test_status_messages_are_exact,
        test_import_recent_downloads_copies_to_queue_and_records_manifest,
        test_import_recent_downloads_prompt_flow_and_queue_upload,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} self tests passed")
