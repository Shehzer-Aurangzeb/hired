"""
Diff our CV's vertical spacing against the Google Docs original.

The layout is copied from a document nobody can diff by eye, so this measures
both PDFs instead: every baseline on page one, and the distance to the line
above it. A spacing change that drifts shows up as a number, not a feeling.

    .venv/bin/python tools/spacing.py                     # ours vs the reference
    .venv/bin/python tools/spacing.py some.pdf            # just dump one file

Needs pypdf, which is not a runtime dependency:  pip install pypdf
"""

import sys
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "docs/cv/ShehzarAurangzeb.pdf"

# What the source document does, measured off it. Baseline to baseline, in
# points, at the 10pt body size whose own line-to-line is 12.1pt.
EXPECTED = {
    "line to line inside a paragraph": 12.1,
    "body into a section heading": 19.2,
    "section heading into the line under it": 20.7,
    "WORK EXPERIENCE into the first employer": 21.1,
    "employer into its role and dates": 12.3,
    "role into the first project": 17.1,
    "project into the next project": 17.1,
    "last line into the next employer": 20.5,
    "role into a bullet with no project heading": 12.1,
    "bullet into bullet": 12.1,
}


def lines(pdf: Path) -> list[tuple[float, float, str]]:
    """(baseline y, font size, text) for page one, top of the page first."""
    rows: dict[float, list] = defaultdict(list)

    def visit(text, cm, tm, font, size):
        if text.strip():
            x = tm[0] * cm[0] + tm[1] * cm[2] + cm[4] + tm[4] * cm[0]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            rows[round(y, 1)].append((round(x, 1), text, abs(size * cm[3])))

    PdfReader(pdf).pages[0].extract_text(visitor_text=visit)
    return [
        (y, max(p[2] for p in rows[y]), "".join(p[1] for p in sorted(rows[y])).strip())
        for y in sorted(rows, reverse=True)
    ]


def dump(pdf: Path) -> None:
    print(f"\n=== {pdf.name}")
    previous = None
    for y, size, text in lines(pdf):
        gap = f"{previous - y:5.1f}" if previous is not None else "    -"
        print(f"  y={y:6.1f} gap={gap} {size:4.1f}pt | {text[:70]}")
        previous = y


if __name__ == "__main__":
    if len(sys.argv) > 1:
        dump(Path(sys.argv[1]))
    else:
        print(__doc__.strip().splitlines()[0])
        print("\nWhat the source document does:")
        for what, points in EXPECTED.items():
            print(f"  {points:5.1f}pt  {what}")
        if REFERENCE.exists():
            dump(REFERENCE)
        else:
            print(f"\nNo reference at {REFERENCE} — export the Doc as PDF to compare.")
