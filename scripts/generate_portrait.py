"""Turn a photograph into a self-typing ASCII portrait as an animated SVG.

    py scripts/generate_portrait.py path/to/photo.jpg

Run locally and commit the result. This is NOT in the nightly workflow -- it
needs Pillow, OpenCV, rembg and a ~176 MB ONNX model, none of which belong in
a job that only has to refresh four numbers.

The input matters far more than any flag below. ASCII draws with shadow, not
detail: there are 13 brightness levels total. A flatly-lit face collapses into
one tone and renders as a hole no matter how the curve is tuned. Want side
light at roughly 45 degrees, a tight crop (chin to just above the hair), and
1200 px or more -- thin features like glasses frames average away on downscale
from anything smaller.
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand import (  # noqa: E402
    CHAR_H, CHAR_W, COLS, FONT_SIZE, INK, RAMP, ROW_ASPECT, ROW_DUR,
    ROW_STAGGER, fmt, font_face, svg_open, write,
)

WORK_W = 1400        # cap for the expensive filters; downscale to grid follows
ASCENT = FONT_SIZE * 0.80
ALPHA_CUTOFF = 128   # rembg alpha above this counts as subject


def cutout(path):
    """Isolate the subject and return (grayscale, subject mask).

    Without this stage the background keeps whatever tone it had, gets pushed
    around by CLAHE, and fills with '@' -- which drowns the portrait. The mask
    is returned rather than applied so the tone pipeline can run on the real
    pixels first; forcing white before CLAHE would let the equaliser treat the
    flat white as a tile to stretch.
    """
    from rembg import new_session, remove

    src = Image.open(path).convert("RGB")
    print(f"  input        {src.width}x{src.height}")
    if min(src.size) < 600:
        print("  WARNING: small input. Thin features will not survive.")

    print("  rembg        removing background (first run downloads ~176 MB)")
    rgba = remove(src, session=new_session("u2net"))

    alpha = np.array(rgba.getchannel("A"))
    mask = alpha > ALPHA_CUTOFF
    if not mask.any():
        sys.exit("error: background removal found no subject at all")

    frac = mask.mean()
    print(f"  subject      {frac * 100:.1f}% of frame")
    if frac < 0.18:
        print("  WARNING: subject is small in frame. Crop tighter -- at 90")
        print("           columns a face this size will not resolve eyes.")

    rgb = np.array(rgba.convert("RGB"))
    return rgb, mask


def crop_to_subject(rgb, mask, pad=0.03):
    """Trim to the subject's bounding box so the grid is not spent on margin."""
    ys, xs = np.where(mask)
    y0, y1 = ys.min(), ys.max()
    x0, x1 = xs.min(), xs.max()
    py = int((y1 - y0) * pad)
    px = int((x1 - x0) * pad)
    y0 = max(0, y0 - py)
    y1 = min(mask.shape[0] - 1, y1 + py)
    x0 = max(0, x0 - px)
    x1 = min(mask.shape[1] - 1, x1 + px)
    print(f"  crop         {x1 - x0 + 1}x{y1 - y0 + 1}")
    return rgb[y0:y1 + 1, x0:x1 + 1], mask[y0:y1 + 1, x0:x1 + 1]


def tone(rgb, gamma, clip):
    """Grayscale, smooth, equalise locally, then darken.

    bilateral   smooths skin texture while keeping edges intact, so the ramp
                does not spend levels on noise.
    CLAHE       local contrast per tile. Global autocontrast leaves a flatly
                lit face as a single tone, because the frame's true black and
                white are elsewhere in the image.
    curve       (v/255) ** gamma with gamma > 1 darkens the midtones. This is
                the stage that decides whether the portrait has features:
                without it the face comes out washed out and flat. It leaves
                255 at 255, so the background stays clean.
    """
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    gray = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8)).apply(gray)
    curve = (((np.arange(256) / 255.0) ** gamma) * 255.0).astype(np.uint8)
    return cv2.LUT(gray, curve)


def to_rows(gray, mask, cols):
    """Force the background white, downscale to the grid, map to the ramp."""
    gray = np.where(mask, gray, 255).astype(np.uint8)

    h, w = gray.shape
    rows = max(1, int(round(cols * (h / w) * ROW_ASPECT)))
    small = cv2.resize(gray, (cols, rows), interpolation=cv2.INTER_AREA)

    # 255 -> index 0 (a space, i.e. nothing drawn); 0 -> the darkest glyph.
    idx = np.rint((1.0 - small / 255.0) * (len(RAMP) - 1)).astype(int)
    return ["".join(RAMP[i] for i in row) for row in idx]


def render(rows, cols):
    """One clipPath per row, each wiping open, with a block riding the edge.

    Animation is SMIL because scripts are stripped from anything GitHub
    serves. Every animate/set carries fill="freeze" so the portrait types
    itself once and stays put -- a loop on a profile page is a distraction.
    """
    w = cols * CHAR_W
    h = len(rows) * CHAR_H

    out = [svg_open(w, h, "ASCII self-portrait, drawn one line at a time")]
    out.append("<defs>")
    out.append("<style>")
    out.append(font_face("JBM Ramp", "ramp.woff2"))
    out.append(
        f".r{{font-family:'JBM Ramp',monospace;font-size:{fmt(FONT_SIZE)}px;"
        f"fill:{INK};white-space:pre}}"
        f".c{{fill:{INK}}}"
    )
    out.append("</style>")

    live = []
    for i, row in enumerate(rows):
        stripped = row.rstrip()
        if not stripped:
            continue                     # blank row: no clip, no text, no bytes
        lead = len(row) - len(row.lstrip())
        text = row[lead:len(stripped)]
        x = lead * CHAR_W
        run = len(text) * CHAR_W
        begin = i * ROW_STAGGER
        live.append((i, text, x, run, begin))

        out.append(f'<clipPath id="c{i}">')
        out.append(
            f'<rect x="{fmt(x)}" y="{fmt(i * CHAR_H)}" width="0" '
            f'height="{fmt(CHAR_H)}">'
            f'<animate attributeName="width" from="0" to="{fmt(run)}" '
            f'begin="{fmt(begin)}s" dur="{fmt(ROW_DUR)}s" fill="freeze"/>'
            f"</rect>"
        )
        out.append("</clipPath>")
    out.append("</defs>")

    for i, text, x, run, begin in live:
        y = i * CHAR_H + ASCENT
        # xml:space is required: SVG collapses runs of whitespace by default,
        # which would slide every glyph after an interior gap out of column.
        out.append(
            f'<text class="r" x="{fmt(x)}" y="{fmt(y)}" '
            f'clip-path="url(#c{i})" xml:space="preserve">'
            f"{_esc(text)}</text>"
        )
        out.append(
            f'<rect class="c" x="{fmt(x)}" y="{fmt(i * CHAR_H + 2)}" '
            f'width="{fmt(CHAR_W)}" height="{fmt(CHAR_H - 4)}" opacity="0">'
            f'<animate attributeName="x" from="{fmt(x)}" to="{fmt(x + run)}" '
            f'begin="{fmt(begin)}s" dur="{fmt(ROW_DUR)}s" fill="freeze"/>'
            f'<set attributeName="opacity" to="0.55" begin="{fmt(begin)}s"/>'
            f'<set attributeName="opacity" to="0" '
            f'begin="{fmt(begin + ROW_DUR)}s"/>'
            f"</rect>"
        )

    out.append("</svg>")
    return "".join(out), len(live)


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("photo")
    ap.add_argument("--cols", type=int, default=COLS,
                    help=f"grid width (default {COLS}; below ~88 the face muddies)")
    ap.add_argument("--gamma", type=float, default=1.7,
                    help="darkening exponent (default 1.7; raise to deepen shadow)")
    ap.add_argument("--clip", type=float, default=3.0,
                    help="CLAHE clip limit (default 3.0)")
    ap.add_argument("--no-crop", action="store_true",
                    help="skip auto-crop to the subject bounding box")
    ap.add_argument("--txt", action="store_true",
                    help="also dump portrait.txt to eyeball the grid")
    args = ap.parse_args()

    if not Path(args.photo).exists():
        sys.exit(f"error: no such file: {args.photo}")

    print()
    rgb, mask = cutout(args.photo)
    if not args.no_crop:
        rgb, mask = crop_to_subject(rgb, mask)

    if rgb.shape[1] > WORK_W:
        scale = WORK_W / rgb.shape[1]
        size = (WORK_W, int(round(rgb.shape[0] * scale)))
        rgb = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
        mask = cv2.resize(mask.astype(np.uint8), size,
                          interpolation=cv2.INTER_NEAREST).astype(bool)

    gray = tone(rgb, args.gamma, args.clip)
    rows = to_rows(gray, mask, args.cols)

    ink = sum(c != " " for r in rows for c in r)
    cells = sum(len(r) for r in rows)
    print(f"  grid         {args.cols}x{len(rows)}, {ink / cells * 100:.0f}% inked")

    body, drawn = render(rows, args.cols)
    print()
    write("portrait.svg", body)
    total = (len(rows) - 1) * ROW_STAGGER + ROW_DUR
    print(f"  {len(rows)} rows, {drawn} drawn, types in {total:.1f}s")
    print(f"  intrinsic {fmt(args.cols * CHAR_W)}px wide")

    if args.txt:
        dump = Path(__file__).resolve().parent.parent / "portrait.txt"
        with open(dump, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(rows) + "\n")
        print("  wrote portrait.txt")


if __name__ == "__main__":
    main()
