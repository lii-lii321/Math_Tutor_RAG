"""QA helper: render the compiled deck to a PDF and export per-slide PNGs."""
import pathlib
import subprocess
import sys

DECK = pathlib.Path(r"D:\Math_Tutor_RAG\docs\deck")
PPTX = DECK / "slides" / "output" / "mathmaster-ui-redesign-v1.pptx"
QA = DECK / "qa"
SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"

QA.mkdir(parents=True, exist_ok=True)
for old in QA.glob("*.pdf"):
    old.unlink()


def to_pdf() -> pathlib.Path:
    subprocess.run(
        [
            SOFFICE,
            f"-env:UserInstallation=file:///{(QA / 'loprofile').as_posix()}",
            "--headless", "--norestore", "--convert-to", "pdf",
            "--outdir", str(QA), str(PPTX),
        ],
        check=True, capture_output=True, timeout=600,
    )
    pdf = QA / (PPTX.stem + ".pdf")
    if not pdf.exists():
        sys.exit("PDF conversion produced nothing")
    return pdf


def to_pngs(pdf: pathlib.Path, zoom: float = 1.6) -> list[pathlib.Path]:
    import pymupdf

    out = []
    with pymupdf.open(pdf) as doc:
        for i, page in enumerate(doc, 1):
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            target = QA / f"slide-{i:02d}.png"
            pix.save(target)
            out.append(target)
    return out


if __name__ == "__main__":
    pdf = to_pdf()
    pngs = to_pngs(pdf)
    print(f"pdf: {pdf}  pages: {len(pngs)}")
