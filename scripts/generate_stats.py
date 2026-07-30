"""Draw stats.svg, streak.svg, langs.svg and year.svg from the GraphQL API.

    GITHUB_TOKEN=... GH_LOGIN=... python3 scripts/generate_stats.py

Standard library only -- urllib for the API, no dependencies to break in CI.
The built-in GITHUB_TOKEN is enough; no personal access token is needed.

Two determinism traps are handled here, and both matter because getting them
wrong produces a commit every single night with no real change in it:

1.  The contribution window is pinned to whole UTC days. Left to its default,
    contributionsCollection measures "the past year" from the instant of the
    request, so two runs minutes apart bucket days into different weeks and
    shift the sparkline by a fraction of a pixel -- forever "changed".

2.  Repositories are filtered to privacy: PUBLIC. A personal token sees
    private repositories and the workflow's token does not, so without the
    filter the language percentages depend on who ran the script.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand import (  # noqa: E402
    YEAR_CELL, YEAR_FONT, YEAR_RAMP, YEAR_ROW, esc, fmt, font_face, svg_open,
    theme_css, write,
)

API = "https://api.github.com/graphql"
W = 860                      # intrinsic width shared by the three cards
PAD = 26
WINDOW_DAYS = 365            # inclusive, so the query spans today-364..today

QUERY = """
query($login:String!, $from:DateTime!, $to:DateTime!, $cursor:String) {
  user(login:$login) {
    login
    name
    followers { totalCount }
    contributionsCollection(from:$from, to:$to) {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date weekday contributionCount } }
      }
    }
    repositories(
      first:100
      after:$cursor
      privacy:PUBLIC
      ownerAffiliations:OWNER
      isFork:false
      orderBy:{field:PUSHED_AT, direction:DESC}
    ) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        stargazerCount
        primaryLanguage { name }
        languages(first:16, orderBy:{field:SIZE, direction:DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------

def gql(token, variables):
    payload = json.dumps({"query": QUERY, "variables": variables}).encode()
    req = urllib.request.Request(
        API,
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-selfgen",
        },
    )
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.loads(r.read().decode())
            if "errors" in body:
                sys.exit("GraphQL error: " + json.dumps(body["errors"], indent=2))
            return body["data"]["user"]
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (403, 429, 502, 503):     # transient; back off
                wait = 2 ** attempt
                print(f"  HTTP {e.code}, retrying in {wait}s")
                time.sleep(wait)
                continue
            sys.exit(f"HTTP {e.code}: {e.read().decode()[:400]}")
        except urllib.error.URLError as e:
            last = e
            time.sleep(2 ** attempt)
    sys.exit(f"giving up after retries: {last}")


def utc_window():
    """Whole UTC days, so the buckets are identical for every run today."""
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=WINDOW_DAYS - 1)
    return (
        f"{start.isoformat()}T00:00:00Z",
        f"{today.isoformat()}T23:59:59Z",
        start,
        today,
    )


def fetch(token, login):
    frm, to, start, end = utc_window()
    print(f"  window       {start} .. {end}  (UTC-pinned, {WINDOW_DAYS} days)")

    user = gql(token, {"login": login, "from": frm, "to": to, "cursor": None})
    repos = list(user["repositories"]["nodes"])
    page = user["repositories"]["pageInfo"]
    while page["hasNextPage"]:
        nxt = gql(token, {"login": login, "from": frm, "to": to,
                          "cursor": page["endCursor"]})
        repos.extend(nxt["repositories"]["nodes"])
        page = nxt["repositories"]["pageInfo"]

    print(f"  repos        {len(repos)} public, non-fork, owned")
    return user, repos


# --------------------------------------------------------------------------
# derived numbers
# --------------------------------------------------------------------------

def flatten_days(cal):
    days = []
    for week in cal["weeks"]:
        for d in week["contributionDays"]:
            days.append((date.fromisoformat(d["date"]), d["contributionCount"]))
    days.sort()
    return days


def streaks(days):
    """Current and longest run of consecutive non-zero days.

    Only the queried window is visible, so a streak that began before it is
    reported as starting on the window's first day. Stated, not hidden.

    Today counts as neutral rather than breaking: a run through yesterday is
    still 'current' until the day is over, which is the convention every
    streak card uses and the only one that isn't demoralising at 09:00.
    """
    best = cur = 0
    best_span = cur_span = (None, None)
    for d, n in days:
        if n > 0:
            cur = cur + 1 if cur else 1
            cur_span = (cur_span[0] if cur > 1 else d, d)
            if cur > best:
                best, best_span = cur, cur_span
        else:
            cur, cur_span = 0, (None, None)

    if days and days[-1][1] == 0:
        # Re-run ignoring today so an empty morning does not zero the streak.
        tail = days[:-1]
        run = 0
        span = (None, None)
        for d, n in reversed(tail):
            if n == 0:
                break
            run += 1
            span = (d, span[1] or d)
        cur, cur_span = run, span

    return cur, cur_span, best, best_span


def weekly(cal):
    return [sum(d["contributionCount"] for d in w["contributionDays"])
            for w in cal["weeks"]]


def languages(repos):
    by_bytes, by_repo = {}, {}
    for r in repos:
        for e in r["languages"]["edges"]:
            name = e["node"]["name"]
            by_bytes[name] = by_bytes.get(name, 0) + e["size"]
        p = r["primaryLanguage"]
        if p:
            by_repo[p["name"]] = by_repo.get(p["name"], 0) + 1
    # Sort by value then name so ties never reorder between runs.
    rank = lambda d: sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))
    return rank(by_bytes), rank(by_repo)


# --------------------------------------------------------------------------
# SVG helpers
# --------------------------------------------------------------------------

def head(title, w, h, weights=(400, 700)):
    out = [svg_open(w, h, title), "<defs><style>"]
    if 400 in weights:
        out.append(font_face("JBM", "mono400.woff2", 400))
    if 700 in weights:
        out.append(font_face("JBM", "mono700.woff2", 700))
    out.append("text{font-family:'JBM',ui-monospace,monospace;white-space:pre}")
    out.append(theme_css())
    out.append("</style></defs>")
    return out


def tx(x, y, s, size=12, weight=400, cls="b", anchor="start", spacing=None):
    """A text node. cls selects the themed fill: v/b/m/f, strongest first."""
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    ls = f' letter-spacing="{fmt(spacing)}"' if spacing else ""
    wt = f' font-weight="{weight}"' if weight != 400 else ""
    return (
        f'<text class="{cls}" x="{fmt(x)}" y="{fmt(y)}" '
        f'font-size="{fmt(size)}"{wt}{a}{ls}>{esc(s)}</text>'
    )


def rule(x1, y, x2):
    return (f'<line class="gl" x1="{fmt(x1)}" y1="{fmt(y)}" x2="{fmt(x2)}" '
            f'y2="{fmt(y)}" stroke-width="1"/>')


def group(n):
    return f"{n:,}"


def short_date(d):
    """'jul 25'. Lowercase, and %-d/%#d are avoided because the two platforms
    spell that flag differently and this runs on both."""
    return f"{d.strftime('%b').lower()} {d.day}"


# --------------------------------------------------------------------------
# stats.svg -- hero total + weekly sparkline
# --------------------------------------------------------------------------

def render_stats(user, cc, repos, days):
    """Hero total, two figures on the right, wide sparkline underneath."""
    cal = cc["contributionCalendar"]
    total = cal["totalContributions"]
    wk = weekly(cal)
    active = sum(1 for _, n in days if n > 0)
    h = 214

    out = head("Contribution totals and a weekly sparkline", W, h)

    out.append(tx(PAD, 78, group(total), 58, 700, "v"))
    out.append(tx(PAD, 102, "contributions in the last year", 12, 400, "m"))

    for i, (v, label) in enumerate(((group(active), "active days"),
                                    (group(max(wk)), "best week"))):
        y = 50 + i * 44
        out.append(tx(W - PAD, y, v, 22, 700, "v", anchor="end"))
        out.append(tx(W - PAD, y + 16, label, 10, 400, "m", anchor="end"))

    # Weekly aggregates, so a line is defensible: consecutive weeks really are
    # continuous quantities. Daily counts are sparse and discrete -- a line
    # through 0,0,11,0,0,10 asserts values that never existed, which is why
    # the day-level graphic (year.svg) uses one discrete mark per day instead.
    gx, gy, gw, gh = PAD, 130, W - PAD * 2, 64
    lo, hi = min(wk), max(wk) or 1
    n = len(wk)
    step = gw / max(1, n - 1)
    pts = [(gx + i * step, gy + gh - (v - lo) / max(1, hi - lo) * gh)
           for i, v in enumerate(wk)]

    area = (f'M{fmt(pts[0][0])},{fmt(gy + gh)}'
            + "".join(f"L{fmt(x)},{fmt(y)}" for x, y in pts)
            + f'L{fmt(pts[-1][0])},{fmt(gy + gh)}Z')
    line = "M" + "L".join(f"{fmt(x)},{fmt(y)}" for x, y in pts)

    # Opacity, not a lighter colour, for the area: opacity degrades the same on
    # both backgrounds, a fixed light grey only works on one.
    out.append(f'<path class="ar" d="{area}" opacity="0.14"/>')
    out.append(f'<path class="ln" d="{line}" fill="none" stroke-width="1.4" '
               f'stroke-linejoin="round"/>')
    # A dot on the final week, so "now" is locatable on a 53-point line.
    out.append(f'<circle class="v" cx="{fmt(pts[-1][0])}" '
               f'cy="{fmt(pts[-1][1])}" r="2.5"/>')
    out.append(rule(gx, gy + gh, gx + gw))

    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# streak.svg
# --------------------------------------------------------------------------

def render_streak(days):
    """Two columns: current and longest, each with its date range."""
    cur, cur_span, best, best_span = streaks(days)
    h = 132
    out = head("Current streak and longest streak", W, h)

    def span_text(a, b):
        if not a or not b:
            return "none yet"
        if a == b:
            return short_date(a)
        return f"{short_date(a)} – {short_date(b)}"

    cells = [
        (group(cur), "current streak", span_text(*cur_span)),
        (group(best), "longest streak", span_text(*best_span)),
    ]
    span = (W - PAD * 2) / len(cells)
    for i, (v, label, sub) in enumerate(cells):
        x = PAD + i * span
        if i:
            out.append(f'<line class="gl" x1="{fmt(x - 30)}" y1="22" '
                       f'x2="{fmt(x - 30)}" y2="{h - 22}" stroke-width="1"/>')
        out.append(tx(x, 62, v, 42, 700, "v"))
        out.append(tx(x, 86, label, 12, 400, "b"))
        out.append(tx(x, 106, sub, 11, 400, "m"))

    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# langs.svg
# --------------------------------------------------------------------------

def render_langs(by_bytes, by_repo, top=5):
    """Two columns of name / bar / value. One ink, lowercase names.

    Language names are lowercased and the per-language brand colours are
    dropped. GitHub's palette puts an orange, a yellow and two blues next to
    each other; five of those in a row is five competing hues fighting the rest
    of the page, and the colour carries no information the label does not.
    """
    rows = max(len(by_bytes[:top]), len(by_repo[:top]))
    h = 54 + rows * 30
    out = head("Most used languages, by bytes and by repository", W, h)

    gap = 56
    col_w = (W - PAD * 2 - gap) / 2
    # Wide enough for the longest label GitHub actually returns here --
    # "jupyter notebook" is 16 characters, which at 12px mono is ~115px and
    # overflowed into the bar at 96.
    name_w, val_w = 124, 40
    bar_w = col_w - name_w - val_w - 12
    max_chars = int(name_w / (12 * 0.6)) - 1

    for ci, (title, data, unit) in enumerate((
        ("BY BYTES", by_bytes[:top], "pct"),
        ("BY REPOS", by_repo[:top], "count"),
    )):
        x = PAD + ci * (col_w + gap)
        out.append(tx(x, 26, title, 10, 400, "m", spacing=1.1))

        peak = max((v for _, v in data), default=1) or 1
        grand = sum(v for _, v in data) or 1
        for ri, (name, value) in enumerate(data):
            y = 56 + ri * 30
            label = name.lower()
            if len(label) > max_chars:
                # ASCII full stop, not U+2026: the font subset is basic latin
                # only, so an ellipsis would render as a missing-glyph box.
                label = label[:max_chars - 1] + "."
            out.append(tx(x, y, label, 12, 400, "b"))

            bx = x + name_w
            out.append(f'<rect class="gf" x="{fmt(bx)}" y="{fmt(y - 9)}" '
                       f'width="{fmt(bar_w)}" height="9" rx="2"/>')
            out.append(f'<rect class="ar" x="{fmt(bx)}" y="{fmt(y - 9)}" '
                       f'width="{fmt(bar_w * (value / peak))}" height="9" '
                       f'rx="2" opacity="0.72"/>')

            shown = (f"{value / grand * 100:.0f}%" if unit == "pct"
                     else str(value))
            out.append(tx(x + col_w, y, shown, 11, 400, "m", anchor="end"))

    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# year.svg -- one character per day, using the portrait's own ramp
# --------------------------------------------------------------------------

def render_year(cal):
    """One day per cell, each drawn as its glyph twice, month labels beneath."""
    weeks = cal["weeks"]
    days = {}
    for wi, wk in enumerate(weeks):
        for d in wk["contributionDays"]:
            days[(wi, d["weekday"])] = (d["contributionCount"],
                                        date.fromisoformat(d["date"]))
    nz = sorted(c for c, _ in days.values() if c > 0)

    # Quantile buckets over non-zero days, so one 40-commit afternoon does not
    # flatten every ordinary day to the lightest mark. Zero stays a space --
    # a day with no contributions draws nothing at all rather than a floor.
    levels = len(YEAR_RAMP) - 1
    cuts = [nz[min(len(nz) - 1, int(len(nz) * (i + 1) / levels))]
            for i in range(levels)] if nz else []

    def glyph(count):
        if count <= 0:
            return YEAR_RAMP[0]
        for i, c in enumerate(cuts):
            if count <= c:
                return YEAR_RAMP[i + 1]
        return YEAR_RAMP[-1]

    left, top = 46, 66
    grid_w = len(weeks) * YEAR_CELL
    active = sum(1 for c, _ in days.values() if c > 0)
    h = top + 7 * YEAR_ROW + 34

    out = head("The year, one character per day", W, h)

    out.append(tx(left, 26, "THE YEAR", 10, 400, "m", spacing=1.1))
    out.append(tx(left, 46, f"{active} of {len(days)} days had a contribution",
                  11, 400, "b"))

    # Legend, right-aligned as a block: "less : + # @ more".
    lx = W - PAD - 116
    out.append(tx(lx, 26, "less", 9, 400, "f"))
    for i, ch in enumerate(YEAR_RAMP[1:]):
        out.append(f'<text class="m" x="{fmt(lx + 30 + i * 14)}" y="26" '
                   f'font-size="{fmt(YEAR_FONT)}" '
                   f'xml:space="preserve">{esc(ch)}</text>')
    out.append(tx(lx + 30 + len(YEAR_RAMP[1:]) * 14 + 4, 26, "more",
                  9, 400, "f"))

    for wd, label in ((1, "mon"), (3, "wed"), (5, "fri")):
        out.append(tx(left - 10, top + wd * YEAR_ROW + YEAR_FONT * 0.72, label,
                      9, 400, "f", anchor="end"))

    for (wi, wd), (count, _) in sorted(days.items()):
        ch = glyph(count)
        if ch == " ":
            continue                        # a zero day draws nothing at all
        out.append(
            f'<text class="b" x="{fmt(left + wi * YEAR_CELL)}" '
            f'y="{fmt(top + wd * YEAR_ROW + YEAR_FONT * 0.72)}" '
            f'font-size="{fmt(YEAR_FONT)}" '
            f'xml:space="preserve">{esc(ch * 2)}</text>'
        )

    # Month labels below the grid, at the week each month first appears, but
    # only where there is room since the last one -- otherwise consecutive
    # labels collide and render as "ju*ug".
    my = top + 7 * YEAR_ROW + 20
    seen, last_x = None, -999
    for wi, wk in enumerate(weeks):
        d = date.fromisoformat(wk["contributionDays"][0]["date"])
        x = left + wi * YEAR_CELL
        if d.month != seen and wi < len(weeks) - 1 and x - last_x >= 34:
            seen, last_x = d.month, x
            out.append(tx(x, my, d.strftime("%b").lower(), 10, 400, "m"))
        elif d.month != seen:
            seen = d.month

    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------

def main():
    token = os.environ.get("GITHUB_TOKEN")
    login = os.environ.get("GH_LOGIN")
    if not token:
        sys.exit("error: GITHUB_TOKEN is not set")
    if not login:
        sys.exit("error: GH_LOGIN is not set")

    # The contribution calendar is viewer-dependent, and not only for the
    # repository list that privacy:PUBLIC already handles. Measured on this
    # repository, same pinned window, same code, minutes apart:
    #
    #     workflow GITHUB_TOKEN : 41 active days, longest streak 5 (17-21 Jul)
    #     personal OAuth token  : 39 active days, longest streak 4 (19-22 Jun)
    #
    # Reproducible across runs, so it is visibility, not eventual consistency.
    # Whichever token wrote the files last, the other one reverts them, and the
    # nightly job then commits a churn diff every single night.
    #
    # So the action owns these four files. Running locally is for debugging the
    # drawing code, not for producing what gets committed.
    if os.environ.get("GITHUB_ACTIONS") != "true" and "--local" not in sys.argv:
        sys.exit(
            "refusing to run outside CI.\n\n"
            "  These four SVGs are owned by .github/workflows/refresh-stats.yml.\n"
            "  A personal token sees a different contribution calendar than the\n"
            "  workflow's token, so regenerating locally and committing the\n"
            "  result makes the nightly job fight your working copy forever.\n\n"
            "  To iterate on the drawing code:  python scripts/generate_stats.py --local\n"
            "  then discard the output:         git checkout -- '*.svg'\n"
        )

    print()
    user, repos = fetch(token, login)
    cc = user["contributionsCollection"]
    cal = cc["contributionCalendar"]
    days = flatten_days(cal)
    by_bytes, by_repo = languages(repos)

    print(f"  total        {cal['totalContributions']:,} contributions")
    print(f"  languages    {len(by_bytes)} distinct")
    print()

    write("stats.svg", render_stats(user, cc, repos, days))
    write("streak.svg", render_streak(days))
    write("langs.svg", render_langs(by_bytes, by_repo))
    write("year.svg", render_year(cal))
    print()


if __name__ == "__main__":
    main()
