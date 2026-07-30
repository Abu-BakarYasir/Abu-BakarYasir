"""Render each README section heading as an SVG.

    py scripts/build_headings.py

Run when HEADINGS in brand.py changes; outputs are committed. Rebuild the font
subsets afterwards too -- head.woff2 only carries the letters these words use.

This exists because an SVG is the only way to put a chosen typeface on a
heading. GitHub strips <style> blocks, style attributes, class attributes and
inline <svg> from README markdown, so there is no CSS route and no way to reach
for a font in the document itself.

The cost is worth stating plainly rather than burying: an <img> heading has no
anchor link, so the repository's README outline is empty and nobody can deep
link to a section. The alt text carries the word for screen readers, and the
<title> inside each file backs it up.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand import (  # noqa: E402
    HEADINGS, esc, fmt, font_face, svg_open, theme_css, write,
)

W = 860
H = 30
SIZE = 13
ADVANCE = 0.600
TRACKING = 0.9          # a little air; lowercase mono at 13px sets tight
BASELINE = 20
GAP = 14                # between the last letter and the rule


def slug(text):
    return text.replace(" ", "-")


def render(word):
    # Advance is exact for this font, so the rule can start immediately after
    # the word without measuring anything at runtime.
    text_w = len(word) * SIZE * ADVANCE + (len(word) - 1) * TRACKING
    rule_x = text_w + GAP

    out = [svg_open(W, H, word)]
    out.append("<defs><style>")
    out.append(font_face("JBM Head", "head.woff2"))
    out.append(
        f"text{{font-family:'JBM Head',ui-monospace,monospace;"
        f"font-size:{fmt(SIZE)}px;"
        f"letter-spacing:{fmt(TRACKING)}px}}"
    )
    out.append(theme_css())
    out.append("</style></defs>")
    out.append(f'<text class="b" x="0" y="{fmt(BASELINE)}">{esc(word)}</text>')
    # Hairline to the right edge. Half-pixel y so it renders as one crisp line
    # rather than a two-pixel smear.
    out.append(
        f'<line class="gl" x1="{fmt(rule_x)}" y1="{fmt(BASELINE - 4.5)}" '
        f'x2="{W}" y2="{fmt(BASELINE - 4.5)}" stroke-width="1"/>'
    )
    out.append("</svg>")
    return "".join(out)


def main():
    print()
    for word in HEADINGS:
        write(f"heading-{slug(word)}.svg", render(word))
    print(f"\n  {len(HEADINGS)} headings")
    print("  note: <img> headings have no anchor links; the README outline")
    print("        will be empty. alt text carries each word.")


if __name__ == "__main__":
    main()
