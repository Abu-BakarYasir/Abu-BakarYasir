"""Shared constants and SVG helpers.

Standard library only, deliberately: generate_stats.py runs in CI and must not
grow a dependency that can break the nightly refresh.
"""

import base64
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets" / "fonts"

# --- the ramp -------------------------------------------------------------
# Brightest to darkest. Index 0 is a space so the white background that rembg
# leaves behind maps to nothing at all, rather than filling with '@'.
RAMP = " .`:-=+*cs#%@"
assert len(RAMP) == 13

# --- the character grid --------------------------------------------------
# JetBrains Mono is 600/1000 units, i.e. an advance of exactly 0.600 em, which
# is what these numbers assume. Verified with fontTools; see build_fonts.py.
# Substituting a font with a different advance (Consolas is ~0.55) shrinks the
# portrait horizontally, which is why the font is embedded rather than named.
COLS = 90
FONT_SIZE = 12.9
ADVANCE_EM = 0.600
CHAR_W = FONT_SIZE * ADVANCE_EM          # 7.74
ROW_ASPECT = 0.48                        # mono cells are ~2x taller than wide
CHAR_H = CHAR_W / ROW_ASPECT             # 16.125, i.e. line-height 1.25

# Typing animation. Rows stagger top to bottom; each row wipes open quickly.
# Total run time = (rows - 1) * ROW_STAGGER + ROW_DUR.
ROW_STAGGER = 0.09
ROW_DUR = 0.15

PORTRAIT_DISPLAY_W = 460                 # the <img width> the README uses

# --- README section headings ---------------------------------------------
# Rendered as SVG because that is the only way to put a chosen typeface on a
# heading; GitHub strips <style>, class and inline <svg>. The trade is real and
# worth stating: an <img> heading has no anchor link, so the repository's
# README outline is empty. The alt text carries the word.
HEADINGS = ["about", "stack", "selected work", "activity", "elsewhere"]

# --- palette -------------------------------------------------------------
# These SVGs are served through <img>, so they cannot inherit the page colour
# and cannot read prefers-color-scheme from the host document. Every value
# below is therefore chosen to stay legible on BOTH the light (#ffffff) and
# dark (#0d1117) GitHub backgrounds, and all hierarchy is expressed with
# opacity rather than lightness -- opacity degrades symmetrically on both,
# a lighter grey only works on one.
INK = "#768390"      # ~4.0:1 on white, ~4.4:1 on dark
ACCENT = "#2f81f7"   # ~3.7:1 on white, ~4.3:1 on dark

OP_STRONG = "1"
OP_BODY = "0.78"
OP_MUTED = "0.55"
OP_FAINT = "0.30"
OP_GRID = "0.18"


def esc(text):
    """XML-escape text destined for an SVG text node."""
    return escape(str(text), {'"': "&quot;"})


def font_face(family, filename, weight=400):
    """An @font-face rule carrying the font inline as a base64 data URI.

    An external font URL cannot work here. These files load through an <img>
    tag, and browsers refuse subresource requests for image documents, so a
    src:url(https://...) silently falls back to a system font. A data URI is
    part of the document itself and does load.
    """
    raw = (FONTS / filename).read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return (
        "@font-face{"
        f"font-family:'{family}';"
        f"font-weight:{weight};"
        "font-style:normal;"
        "font-display:block;"
        f"src:url(data:font/woff2;base64,{b64}) format('woff2')"
        "}"
    )


def svg_open(width, height, title):
    """Root element plus an accessible title.

    role/aria-label are what a screen reader reaches when the SVG is embedded
    via <img>; the alt attribute in the README carries the same words.
    """
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {fmt(width)} {fmt(height)}" '
        f'width="{fmt(width)}" height="{fmt(height)}" '
        f'role="img" aria-label="{esc(title)}">'
        f"<title>{esc(title)}</title>"
    )


def fmt(n):
    """Trim float noise so regenerated files are byte-stable."""
    if isinstance(n, int):
        return str(n)
    r = round(float(n), 3)
    if r == int(r):
        return str(int(r))
    return f"{r:g}"


def write(path, body):
    """Write an SVG, reporting its size. Newline-terminated for clean diffs.

    newline="\\n" is load-bearing. In text mode Python translates \\n to the
    platform separator, so the same script emits CRLF on a Windows workstation
    and LF on the Linux runner -- and the nightly job then sees every file as
    modified and commits, forever. .gitattributes pins the checkout; this pins
    what gets written in the first place.
    """
    p = ROOT / path
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(body + "\n")
    print(f"  {path:<16} {len(body) / 1024:6.1f} KB")
