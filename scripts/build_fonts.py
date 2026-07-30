"""Subset JetBrains Mono into the smallest woff2 files each graphic needs.

Run once; the outputs are committed. Not part of the nightly workflow.

    py scripts/build_fonts.py --src <dir containing JetBrainsMono-*.ttf>

Every SVG has to carry its own copy of the font, because an <img>-embedded
document cannot fetch a subresource. So the cost is per file, and subsetting
per role is what keeps the page from becoming megabytes: inlining the full
267 KB TTF into each of six files would be ~4.5 MB even before base64's 33%
overhead.

Uses the fontTools API rather than the pyftsubset CLI on purpose -- the ramp
contains a backtick, which PowerShell treats as its escape character, so the
documented --text=... invocation silently drops characters on Windows.
"""

import argparse
import shutil
import sys
from pathlib import Path

from fontTools.subset import Options, Subsetter, load_font, save_font
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand import ADVANCE_EM, FONTS, HEADINGS, RAMP  # noqa: E402

BASIC_LATIN = "".join(chr(c) for c in range(0x20, 0x7F))

# Characters the SVG headings actually draw, and nothing else.
HEADING_CHARS = "".join(sorted(set("".join(HEADINGS))))

JOBS = [
    # (output name, source weight, characters, what uses it)
    ("ramp.woff2", "Regular", RAMP, "portrait.svg"),
    ("head.woff2", "Regular", HEADING_CHARS, "heading-*.svg"),
    ("mono400.woff2", "Regular", BASIC_LATIN, "stats/streak/langs/year"),
    ("mono700.woff2", "Bold", BASIC_LATIN, "stats/streak/langs/year"),
]


def verify_metrics(path):
    """Fail loudly if the source font is not the 0.600 em the grid assumes."""
    font = TTFont(path)
    upm = font["head"].unitsPerEm
    widths = {font["hmtx"][g][0] for g in ("A", "space", "at", "percent")}
    if len(widths) != 1:
        sys.exit(f"error: {path.name} is not monospaced (advances {sorted(widths)})")
    ratio = widths.pop() / upm
    if abs(ratio - ADVANCE_EM) > 1e-6:
        sys.exit(
            f"error: {path.name} advance is {ratio:.4f} em, grid assumes "
            f"{ADVANCE_EM}. Portrait geometry would be wrong."
        )
    print(f"  metrics ok: {path.name} = {ratio:.3f} em ({upm} upm)")


def subset(src, out, text):
    opts = Options()
    opts.flavor = "woff2"
    opts.with_zopfli = False
    opts.layout_features = []       # no kerning/ligatures needed in a mono grid
    opts.hinting = False            # hints are dead weight at these sizes
    opts.desubroutinize = True
    opts.name_IDs = ["*"]           # keep the name table so the licence travels
    opts.name_legacy = True
    opts.notdef_outline = False
    opts.recalc_bounds = True
    opts.drop_tables = ["FFTM"]

    font = load_font(str(src), opts)
    s = Subsetter(options=opts)
    s.populate(text=text)
    s.subset(font)
    save_font(font, str(out), opts)
    font.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--src",
        required=True,
        help="directory holding JetBrainsMono-Regular.ttf and -Bold.ttf",
    )
    args = ap.parse_args()
    src_dir = Path(args.src).expanduser()

    FONTS.mkdir(parents=True, exist_ok=True)

    sources = {}
    for weight in ("Regular", "Bold"):
        p = src_dir / f"JetBrainsMono-{weight}.ttf"
        if not p.exists():
            sys.exit(f"error: missing {p}")
        sources[weight] = p
        verify_metrics(p)

    # The font ships inside a public repository, so its licence has to travel
    # with it. JetBrains Mono is SIL OFL 1.1, which permits exactly this.
    ofl = src_dir.parent.parent / "OFL.txt"
    if not ofl.exists():
        ofl = next(src_dir.parent.parent.rglob("OFL.txt"), None)
    if ofl and ofl.exists():
        shutil.copyfile(ofl, FONTS / "OFL.txt")
        print(f"  licence: assets/fonts/OFL.txt ({ofl.stat().st_size} bytes)")
    else:
        print("  WARNING: OFL.txt not found -- add the licence before pushing")

    total = 0
    print()
    for name, weight, text, used_by in JOBS:
        out = FONTS / name
        subset(sources[weight], out, text)
        size = out.stat().st_size
        total += size
        print(f"  {name:<14} {len(set(text)):>3} glyphs  {size / 1024:5.1f} KB  -> {used_by}")

    print(f"\n  {'total':<14}     {'':>3}         {total / 1024:5.1f} KB")
    print(f"  ramp subset covers: {RAMP!r}")
    print(f"  heading subset covers: {HEADING_CHARS!r}")


if __name__ == "__main__":
    main()
