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
# 90 columns displayed at 460px. Shrinking the portrait by lowering the <img>
# width alone does not work: at 460px a 110-column grid puts each character at
# 4.2px and the face turns to texture. Fewer, larger characters resolve better
# than more, smaller ones, so the column count comes down with the display
# width. Below about 76 the face goes blocky.
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
HEADINGS = ["about", "stack", "projects", "stats"]

# --- palette -------------------------------------------------------------
# These SVGs are served through <img>, so they cannot inherit the page colour
# and cannot read prefers-color-scheme from the host document. Every value
# below is therefore chosen to stay legible on BOTH the light (#ffffff) and
# dark (#0d1117) GitHub backgrounds, and all hierarchy is expressed with
# opacity rather than lightness -- opacity degrades symmetrically on both,
# a lighter grey only works on one.
# Monochrome, but theme-aware rather than a compromise mid-grey.
#
# The obvious approach -- one ink that is legible on both #ffffff and #0d1117 --
# forces every value to a mid-grey, and the result is uniformly dull: the hero
# number carries no more weight than its own caption.
#
# Instead each file ships both palettes and picks at render time with
# @media (prefers-color-scheme: dark) inside its own <style>. That works even
# though these load through an <img>: the SVG is an independent document and
# the preference is a user-level signal available to it. Verified by rendering
# the same file under a forced dark preference and watching the rule win.
#
# One caveat, the same one GitHub's own recommended <picture> approach has:
# this follows the OS/browser preference, not GitHub's in-page theme setting.
# GitHub defaults to "sync with system", so the two agree for most people.
LIGHT = {"v": "#1f2328",   # values, the strongest thing on the card
         "b": "#424a53",   # body text
         "m": "#59636e",   # labels
         "f": "#818b98",   # axis and legend furniture
         "g": "#d0d7de"}   # rules, bar troughs
DARK = {"v": "#f0f6fc",
        "b": "#c9d1d9",
        "m": "#8b949e",
        "f": "#6e7681",
        "g": "#30363d"}


def theme_css():
    """Both palettes as classes, dark applied via a preference query.

    Classes rather than fill="var(--x)": var() in a presentation attribute is
    not reliably supported, whereas a class selector always is.
    """
    def block(p):
        return (f".v{{fill:{p['v']}}}"
                f".b{{fill:{p['b']}}}"
                f".m{{fill:{p['m']}}}"
                f".f{{fill:{p['f']}}}"
                f".gf{{fill:{p['g']}}}"
                f".gl{{stroke:{p['g']}}}"
                f".ln{{stroke:{p['v']}}}"
                f".ar{{fill:{p['v']}}}")
    return block(LIGHT) + "@media(prefers-color-scheme:dark){" + block(DARK) + "}"

# --- the year calendar ---------------------------------------------------
# Four levels, not the portrait's thirteen. A day is one bucket of activity,
# not a brightness; thirteen shades of "some commits" is false precision, and
# at calendar size the middle ten are indistinguishable anyway.
YEAR_RAMP = " :+#@"

# Each day is drawn as the glyph TWICE. One character per day makes a 53-week
# year only ~400px wide, which looks cramped beside a full-width card; doubling
# the glyph fills the measure without inflating the font size.
YEAR_FONT = 12.5
YEAR_CELL = YEAR_FONT * ADVANCE_EM * 2      # 15.0
YEAR_ROW = 15.0                             # near-square cells


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
