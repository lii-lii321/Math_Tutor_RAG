"""Render the v2 direction mockups (warm education + restrained visual) to PNG."""
import pathlib
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "ui-v2-dashboard-2026-10-02.html"
OUT = ROOT / "v2"
OUT.mkdir(parents=True, exist_ok=True)

VIEWPORT = {"width": 1600, "height": 1150}
SCALE = 2


def main() -> int:
    if not SRC.exists():
        print(f"source missing: {SRC}")
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=SCALE)
        page.goto(SRC.as_uri())
        page.wait_for_timeout(900)

        stage = page.query_selector(".app")
        if stage is None:
            print("FAIL: no .app")
            return 1

        target = OUT / "dashboard-v2.png"
        stage.screenshot(path=str(target))
        print("OK", target.name, round(target.stat().st_size / 1024, 1), "KB")

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
