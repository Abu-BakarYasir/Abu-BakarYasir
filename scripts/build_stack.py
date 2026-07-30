"""Render the stack row as one SVG: vendored brand marks plus labels.

    py scripts/build_stack.py

Run when STACK below changes; the output is committed.

The icons are vendored into assets/icons/ and their path data is inlined here
at build time. Linking them from a CDN -- shields.io, the Simple Icons CDN,
any badge service -- would work, and would also undo the one property this
page is built around: it makes zero third-party requests, so there is nothing
in it that can rate-limit, change under you, or go dark.

Marks are drawn in the page's own ink rather than brand colours, and inherit
the same light/dark palette as everything else. Nine brand hues in a single
row would be the same mistake the language chart already avoids: colour
competing with the rest of the page while carrying no information the label
does not already give.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand import (  # noqa: E402
    ROOT, esc, fmt, font_face, svg_open, theme_css, write,
)

W = 860
PAD = 26
SIZE = 12          # label size
ICON = 15          # rendered icon box
ICON_GAP = 7       # icon to label
GAP = 28           # between items
BASELINE = 26
ICON_Y = 14
ADVANCE = 0.600

# (label, icon slug or None). None draws the label alone -- RAG is a technique,
# not a product, so no brand mark exists for it.
STACK = [
    ("python", "python"),
    ("typescript", "typescript"),
    ("javascript", "javascript"),
    ("c++", "cplusplus"),
    ("rag", None),
    ("mcp", "modelcontextprotocol"),
    ("jupyter", "jupyter"),
    ("vite", "vite"),
    ("git", "git"),
]

PATH_RE = re.compile(r'<path[^>]*\sd="([^"]+)"')


def icon_path(slug):
    """The single path from a vendored 24x24 Simple Icons file."""
    f = ROOT / "assets" / "icons" / f"{slug}.svg"
    if not f.exists():
        sys.exit(f"error: missing icon {f}")
    svg = f.read_text(encoding="utf-8")
    m = PATH_RE.search(svg)
    if not m:
        sys.exit(f"error: no path found in {f}")
    if 'viewBox="0 0 24 24"' not in svg:
        sys.exit(f"error: {slug} is not a 24x24 icon; the scale would be wrong")
    return m.group(1)


def main():
    scale = ICON / 24.0
    items = []
    x = PAD
    for label, slug in STACK:
        text_w = len(label) * SIZE * ADVANCE
        width = text_w + (ICON + ICON_GAP if slug else 0)
        items.append((x, label, slug, width))
        x += width + GAP

    total = x - GAP + PAD
    if total > W:
        print(f"  WARNING: row is {total:.0f}px, wider than the {W}px card")

    out = [svg_open(W, 40, "Stack: " + ", ".join(l for l, _ in STACK))]
    out.append("<defs><style>")
    out.append(font_face("JBM", "mono400.woff2", 400))
    out.append(f"text{{font-family:'JBM',ui-monospace,monospace;"
               f"font-size:{fmt(SIZE)}px}}")
    out.append(theme_css())
    out.append("</style></defs>")

    for x, label, slug, _ in items:
        tx = x
        if slug:
            d = icon_path(slug)
            out.append(
                f'<g class="b" transform="translate({fmt(x)},{ICON_Y}) '
                f'scale({fmt(scale)})"><path d="{d}"/></g>'
            )
            tx = x + ICON + ICON_GAP
        out.append(f'<text class="b" x="{fmt(tx)}" y="{BASELINE}">'
                   f"{esc(label)}</text>")

    out.append("</svg>")

    print()
    write("stack.svg", "".join(out))
    print(f"  {len(STACK)} items, row is {total:.0f}px of {W}px")
    missing = [l for l, s in STACK if not s]
    if missing:
        print(f"  label only (no brand mark exists): {', '.join(missing)}")


if __name__ == "__main__":
    main()
