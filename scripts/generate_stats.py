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
    ACCENT, INK, OP_BODY, OP_FAINT, OP_GRID, OP_MUTED, OP_STRONG, RAMP,
    esc, fmt, font_face, svg_open, write,
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
    by_bytes, by_repo, colours = {}, {}, {}
    for r in repos:
        for e in r["languages"]["edges"]:
            name = e["node"]["name"]
            by_bytes[name] = by_bytes.get(name, 0) + e["size"]
            colours.setdefault(name, e["node"]["color"] or INK)
        p = r["primaryLanguage"]
        if p:
            by_repo[p["name"]] = by_repo.get(p["name"], 0) + 1
    # Sort by value then name so ties never reorder between runs.
    rank = lambda d: sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))
    return rank(by_bytes), rank(by_repo), colours


# --------------------------------------------------------------------------
# SVG helpers
# --------------------------------------------------------------------------

def head(title, w, h, weights=(400, 700)):
    out = [svg_open(w, h, title), "<defs><style>"]
    if 400 in weights:
        out.append(font_face("JBM", "mono400.woff2", 400))
    if 700 in weights:
        out.append(font_face("JBM", "mono700.woff2", 700))
    out.append(
        "text{font-family:'JBM',ui-monospace,monospace;"
        f"fill:{INK};white-space:pre}}"
    )
    out.append("</style></defs>")
    return out


def tx(x, y, s, size=12, weight=400, op=OP_BODY, fill=None, anchor="start",
       spacing=None):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    f = f' fill="{fill}"' if fill else ""
    ls = f' letter-spacing="{fmt(spacing)}"' if spacing else ""
    wt = f' font-weight="{weight}"' if weight != 400 else ""
    return (
        f'<text x="{fmt(x)}" y="{fmt(y)}" font-size="{fmt(size)}"{wt}'
        f' opacity="{op}"{f}{a}{ls}>{esc(s)}</text>'
    )


def rule(x1, y, x2, op=OP_GRID):
    return (f'<line x1="{fmt(x1)}" y1="{fmt(y)}" x2="{fmt(x2)}" y2="{fmt(y)}"'
            f' stroke="{INK}" stroke-width="1" opacity="{op}"/>')


def group(n):
    return f"{n:,}"


def short_date(d):
    return d.strftime("%-d %b") if os.name != "nt" else d.strftime("%d %b").lstrip("0")


# --------------------------------------------------------------------------
# stats.svg -- hero total + weekly sparkline
# --------------------------------------------------------------------------

def render_stats(user, cc, repos):
    cal = cc["contributionCalendar"]
    total = cal["totalContributions"]
    wk = weekly(cal)
    h = 208

    out = head("Contribution totals and a weekly sparkline", W, h)

    out.append(tx(PAD, 76, group(total), 56, 700, OP_STRONG, ACCENT))
    out.append(tx(PAD, 102, "contributions  ·  last 365 days", 12, 400, OP_MUTED))

    # Weekly aggregates, so a line is defensible: consecutive weeks really are
    # continuous quantities. Daily counts are sparse and discrete -- a line
    # through 0,0,11,0,0,10 asserts values that never existed, which is why
    # the day-level graphic (year.svg) uses one discrete mark per day instead.
    gx, gy, gw, gh = 404, 26, W - 404 - PAD, 76
    lo, hi = min(wk), max(wk) or 1
    n = len(wk)
    step = gw / max(1, n - 1)
    pts = [(gx + i * step, gy + gh - (v - lo) / max(1, hi - lo) * gh)
           for i, v in enumerate(wk)]

    area = (f'M{fmt(pts[0][0])},{fmt(gy + gh)}'
            + "".join(f"L{fmt(x)},{fmt(y)}" for x, y in pts)
            + f'L{fmt(pts[-1][0])},{fmt(gy + gh)}Z')
    line = "M" + "L".join(f"{fmt(x)},{fmt(y)}" for x, y in pts)

    out.append(f'<path d="{area}" fill="{ACCENT}" opacity="0.12"/>')
    out.append(f'<path d="{line}" fill="none" stroke="{ACCENT}" '
               f'stroke-width="1.75" stroke-linejoin="round" opacity="0.95"/>')

    peak = max(range(n), key=lambda i: wk[i])
    out.append(f'<circle cx="{fmt(pts[peak][0])}" cy="{fmt(pts[peak][1])}" '
               f'r="2.75" fill="{ACCENT}"/>')
    out.append(tx(W - PAD, gy - 6, f"peak {hi}/wk", 10, 400, OP_MUTED,
                  anchor="end"))
    out.append(tx(gx, gy + gh + 14, "52 weeks", 10, 400, OP_FAINT))

    out.append(rule(PAD, 134, W - PAD))

    # Chosen to carry information rather than to fill a row: reviews, issues
    # and followers were all zero here, and three zeros side by side say less
    # than nothing. Swap any of these back in once they are non-zero.
    cells = [
        (group(cc["totalCommitContributions"]), "commits"),
        (group(cc["totalPullRequestContributions"]), "pull requests"),
        (group(len(repos)), "public repos"),
        (group(sum(r["stargazerCount"] for r in repos)), "stars earned"),
        (group(len({n for r in repos for n in
                    (e["node"]["name"] for e in r["languages"]["edges"])})),
         "languages"),
    ]
    span = (W - PAD * 2) / len(cells)
    for i, (v, label) in enumerate(cells):
        x = PAD + i * span
        out.append(tx(x, 172, v, 21, 700, OP_STRONG))
        out.append(tx(x, 190, label, 10, 400, OP_MUTED))

    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# streak.svg
# --------------------------------------------------------------------------

def render_streak(days):
    cur, cur_span, best, best_span = streaks(days)
    active = sum(1 for _, n in days if n > 0)
    h = 152
    out = head("Current streak, longest streak and active days", W, h)

    def span_text(a, b):
        if not a or not b:
            return "--"
        if a == b:
            return short_date(a)
        return f"{short_date(a)} – {short_date(b)}"

    cells = [
        (group(cur), "current streak", span_text(*cur_span)),
        (group(best), "longest streak", span_text(*best_span)),
        (group(active), "active days", f"of {len(days)} in window"),
    ]
    span = (W - PAD * 2) / len(cells)
    for i, (v, label, sub) in enumerate(cells):
        x = PAD + i * span
        if i:
            out.append(f'<line x1="{fmt(x - 22)}" y1="34" x2="{fmt(x - 22)}" '
                       f'y2="{h - 34}" stroke="{INK}" stroke-width="1" '
                       f'opacity="{OP_GRID}"/>')
        out.append(tx(x, 84, v, 46, 700, OP_STRONG, ACCENT if i == 0 else None))
        out.append(tx(x, 108, label, 12, 400, OP_BODY))
        out.append(tx(x, 126, sub, 10, 400, OP_MUTED))

    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# langs.svg
# --------------------------------------------------------------------------

def render_langs(by_bytes, by_repo, colours, top=6):
    rows = max(len(by_bytes[:top]), len(by_repo[:top]))
    h = 78 + rows * 30
    out = head("Most used languages, by bytes and by repository", W, h)

    col_w = (W - PAD * 2 - 40) / 2
    for ci, (title, data, unit) in enumerate((
        ("by bytes", by_bytes[:top], "pct"),
        ("by repository", by_repo[:top], "count"),
    )):
        x = PAD + ci * (col_w + 40)
        out.append(tx(x, 30, title, 11, 700, OP_MUTED))
        out.append(rule(x, 40, x + col_w))

        peak = max((v for _, v in data), default=1) or 1
        grand = sum(v for _, v in data) or 1
        for ri, (name, value) in enumerate(data):
            y = 68 + ri * 30
            # The language's own colour identifies it, in a 7px dot. The bar
            # itself stays in the page's single ink so six rows do not become
            # six competing hues.
            out.append(f'<circle cx="{fmt(x + 3.5)}" cy="{fmt(y - 4)}" r="3.5" '
                       f'fill="{colours.get(name, INK)}"/>')
            out.append(tx(x + 14, y, name, 12, 400, OP_BODY))
            shown = (f"{value / grand * 100:.1f}%" if unit == "pct"
                     else f"{value} repo" + ("s" if value != 1 else ""))
            out.append(tx(x + col_w, y, shown, 11, 700, OP_MUTED, anchor="end"))

            bw = col_w * (value / peak)
            out.append(f'<rect x="{fmt(x)}" y="{fmt(y + 6)}" '
                       f'width="{fmt(col_w)}" height="3" rx="1.5" '
                       f'fill="{INK}" opacity="{OP_GRID}"/>')
            out.append(f'<rect x="{fmt(x)}" y="{fmt(y + 6)}" '
                       f'width="{fmt(bw)}" height="3" rx="1.5" '
                       f'fill="{ACCENT}" opacity="0.85"/>')

    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# year.svg -- one character per day, using the portrait's own ramp
# --------------------------------------------------------------------------

def render_year(cal):
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
    levels = len(RAMP) - 1
    cuts = [nz[min(len(nz) - 1, int(len(nz) * (i + 1) / levels))]
            for i in range(levels)] if nz else []

    def glyph(count):
        if count <= 0:
            return RAMP[0]
        for i, c in enumerate(cuts):
            if count <= c:
                return RAMP[i + 1]
        return RAMP[-1]

    # Cell size is fixed rather than stretched to the card width. Scaling the
    # grid to fill 860px puts the glyphs at 25px, and a year that is mostly
    # empty then reads as scattered debris instead of a calendar. Cells are
    # also kept near-square (1.28, not the portrait's 2.08) because a
    # contribution calendar is a familiar shape and stretching it vertically
    # makes it unrecognisable.
    left, topm = 46, 44
    adv = 11.32
    size = adv / 0.600                      # the grid's advance-width identity
    rowh = adv * 1.28
    grid_w = len(weeks) * adv
    facts_x = left + grid_w + 46
    h = topm + 7 * rowh + 44

    out = head("The year at one character per day", W, h)

    # Label a month at the week it first appears, but only if there is room
    # since the last label -- at 11px per week, consecutive labels collide and
    # render as "ju*ug".
    seen, last_x = None, -999
    for wi, wk in enumerate(weeks):
        d = date.fromisoformat(wk["contributionDays"][0]["date"])
        x = left + wi * adv
        if d.month != seen and wi < len(weeks) - 1 and x - last_x >= 26:
            seen, last_x = d.month, x
            out.append(tx(x, topm - 13, d.strftime("%b").lower(),
                          10, 400, OP_MUTED))
        elif d.month != seen:
            seen = d.month

    for wd, label in ((1, "mon"), (3, "wed"), (5, "fri")):
        out.append(tx(left - 9, topm + wd * rowh + size * 0.72, label,
                      9, 400, OP_FAINT, anchor="end"))

    for (wi, wd), (count, _) in sorted(days.items()):
        ch = glyph(count)
        if ch == " ":
            continue                        # a zero day draws nothing at all
        out.append(
            f'<text x="{fmt(left + wi * adv)}" '
            f'y="{fmt(topm + wd * rowh + size * 0.72)}" '
            f'font-size="{fmt(size)}" opacity="{OP_BODY}" '
            f'xml:space="preserve">{esc(ch)}</text>'
        )

    # The width left over beside the grid carries the numbers the grid cannot
    # state precisely.
    best_c, best_d = max(days.values(), key=lambda v: (v[0], v[1]))
    active = sum(1 for c, _ in days.values() if c > 0)
    facts = [
        (f"{cal['totalContributions']:,}", "contributions"),
        (str(active), f"active days of {len(days)}"),
        (str(best_c), f"best day  ·  {short_date(best_d)}"),
    ]
    for i, (v, label) in enumerate(facts):
        y = topm + 4 + i * 32
        out.append(tx(facts_x, y, v, 17, 700, OP_STRONG))
        out.append(tx(facts_x + 52, y, label, 10, 400, OP_MUTED))

    ly = topm + 7 * rowh + 26
    out.append(tx(left, ly, "less", 9, 400, OP_FAINT))
    for i, ch in enumerate(RAMP[1:]):
        out.append(f'<text x="{fmt(left + 30 + i * 12)}" y="{fmt(ly)}" '
                   f'font-size="12" opacity="{OP_MUTED}" '
                   f'xml:space="preserve">{esc(ch)}</text>')
    out.append(tx(left + 30 + len(RAMP[1:]) * 12 + 6, ly, "more", 9, 400,
                  OP_FAINT))

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
    by_bytes, by_repo, colours = languages(repos)

    print(f"  total        {cal['totalContributions']:,} contributions")
    print(f"  languages    {len(by_bytes)} distinct")
    print()

    write("stats.svg", render_stats(user, cc, repos))
    write("streak.svg", render_streak(days))
    write("langs.svg", render_langs(by_bytes, by_repo, colours))
    write("year.svg", render_year(cal))
    print()


if __name__ == "__main__":
    main()
