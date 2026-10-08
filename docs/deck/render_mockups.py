"""Render the four high-fidelity mockups from the design HTML into PNGs for the PPT."""
import pathlib
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "ui-design-2026-10-01.html"
OUT = ROOT / "deck" / "assets"
OUT.mkdir(parents=True, exist_ok=True)

PANES = [
    ("p-dash", "mock-dashboard.png"),
    ("p-notebook", "mock-notebook.png"),
    ("p-review", "mock-review.png"),
    ("p-tutor", "mock-tutor.png"),
]

# .app has min-height 860px; the browser window is this wide so layout does not reflow.
VIEWPORT = {"width": 1520, "height": 1100}
SCALE = 2  # deviceScaleFactor for crisp PPT rendering


def main() -> int:
    if not SRC.exists():
        print(f"source missing: {SRC}")
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=SCALE)
        page.goto(SRC.as_uri())
        page.wait_for_timeout(700)  # let fonts settle

        for pane_id, filename in PANES:
            # activate the tab so the pane is visible
            page.click(f'#tabs .tab[data-t="{pane_id}"]')
            page.wait_for_timeout(350)

            stage = page.query_selector(f"#{pane_id} .stage")
            if stage is None:
                print(f"FAIL: no .stage in #{pane_id}")
                continue

            target = OUT / filename
            stage.screenshot(path=str(target))
            size_kb = round(target.stat().st_size / 1024, 1)
            print(f"OK  {filename}  {size_kb} KB")

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
