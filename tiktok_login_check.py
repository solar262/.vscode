"""Tkinter utility for opening TikTok's upload/login page with Playwright."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

TIKTOK_UPLOAD_URL = "https://www.tiktok.com/upload"
BROWSER_PROFILE_DIR = "app/data/browser_profile"
OPENING_STATUS = "Opening TikTok login/upload page..."
OPENED_STATUS = "TikTok opened. Log in manually if needed."
LOAD_FAILED_STATUS = "TikTok did not load. Close the browser and try again."


class PageLike(Protocol):
    """Small subset of Playwright's Page API used by this module."""

    url: str

    def goto(self, url: str, *, wait_until: str = "load", timeout: float = 30000) -> object:
        ...


class BrowserContextLike(Protocol):
    """Small subset of Playwright's BrowserContext API used by this module."""

    pages: list[PageLike]

    def new_page(self) -> PageLike:
        ...

    def close(self) -> None:
        ...


class BrowserLaunchError(RuntimeError):
    """Raised when TikTok's upload/login page cannot be loaded."""


StatusCallback = Callable[[str], None]


@dataclass
class BrowserSession:
    """Objects that must stay alive while the Playwright browser is open."""

    playwright: object
    context: BrowserContextLike
    page: PageLike


def navigate_tiktok_upload(context: BrowserContextLike) -> PageLike:
    """Get the first page in a persistent context and navigate it to TikTok upload.

    The first navigation is forced with DOMContentLoaded and a 30 second timeout so
    an about:blank startup tab cannot remain as the final page.
    """

    page = context.pages[0] if context.pages else context.new_page()

    try:
        page.goto("https://www.tiktok.com/upload", wait_until="domcontentloaded", timeout=30000)
        if getattr(page, "url", "about:blank") == "about:blank":
            page.goto("https://www.tiktok.com/upload", wait_until="domcontentloaded", timeout=30000)
    except Exception as exc:  # Playwright raises several navigation-specific errors.
        raise BrowserLaunchError(LOAD_FAILED_STATUS) from exc

    if getattr(page, "url", "about:blank") == "about:blank":
        raise BrowserLaunchError(LOAD_FAILED_STATUS)

    return page


def launch_tiktok_browser(status_callback: StatusCallback) -> BrowserSession:
    """Launch Chromium persistently and open TikTok's upload/login page."""

    status_callback(OPENING_STATUS)
    os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=BROWSER_PROFILE_DIR,
            headless=False,
        )
        page = navigate_tiktok_upload(context)
    except BrowserLaunchError:
        raise
    except Exception as exc:
        raise BrowserLaunchError(LOAD_FAILED_STATUS) from exc

    status_callback(OPENED_STATUS)
    return BrowserSession(playwright=playwright, context=context, page=page)


class TikTokLoginCheckApp:
    """Simple GUI with an "Open TikTok Login Check" browser-launch button."""

    def __init__(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.root = tk.Tk()
        self.root.title("TikTok Login Check")
        self.status = tk.StringVar(value="Ready.")
        self.session: Optional[BrowserSession] = None

        frame = ttk.Frame(self.root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.open_button = ttk.Button(
            frame,
            text="Open TikTok Login Check",
            command=self.open_tiktok_login_check,
        )
        self.open_button.grid(row=0, column=0, sticky="ew")

        status_label = ttk.Label(frame, textvariable=self.status, wraplength=360)
        status_label.grid(row=1, column=0, pady=(12, 0), sticky="ew")
        frame.columnconfigure(0, weight=1)

        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def set_status(self, message: str) -> None:
        self.root.after(0, self.status.set, message)

    def open_tiktok_login_check(self) -> None:
        thread = threading.Thread(target=self._open_browser_worker, daemon=True)
        thread.start()

    def _open_browser_worker(self) -> None:
        try:
            self.session = launch_tiktok_browser(self.set_status)
        except BrowserLaunchError:
            self.set_status(LOAD_FAILED_STATUS)

    def close(self) -> None:
        if self.session:
            try:
                self.session.context.close()
            finally:
                stop = getattr(self.session.playwright, "stop", None)
                if stop:
                    stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    TikTokLoginCheckApp().run()
