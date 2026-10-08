"""Render the UI upgrade spec HTML to an A4 PDF via headless Chromium."""
import pathlib
import sys

from playwright.sync_api import sync_playwright

DOCS = pathlib.Path(__file__).resolve().parent
SRC = DOCS / "ui-upgrade-spec-2026-10-02.html"
OUT = DOCS / "ui-upgrade-spec-2026-10-02.pdf"


def main() -> int:
    if not SRC.exists():
        print(f"missing: {SRC}")
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1240, "height": 1754})
        page.goto(SRC.as_uri())
        page.wait_for_timeout(900)  # fonts + images

        # Report any image that failed to load, so a blank box never ships silently.
        broken = page.evaluate(
            """() => Array.from(document.images)
                   .filter(i => !i.complete || i.naturalWidth === 0)
                   .map(i => i.getAttribute('src'))"""
        )
        if broken:
            print("WARNING broken images: " + ", ".join(broken))

        page.pdf(
            path=str(OUT),
            format="A4",
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        browser.close()

    print(f"WROTE {OUT}  size={round(OUT.stat().st_size / 1024, 1)} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
