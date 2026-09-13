"""E2E 夹具：Playwright page。"""
from __future__ import annotations

import pytest


@pytest.fixture
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        yield page
        context.close()
        browser.close()
