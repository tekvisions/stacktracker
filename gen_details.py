#!/usr/bin/env python3
"""StackTracker static detail-page generator.

Generates one static page per tracked repo at p/<slug>/index.html (served at
/p/<slug>), plus regenerates sitemap.xml (homepage + every detail page) and
llms.txt. Reuses the hub's EXACT header/nav/footer/theme by linking the shared
style.css and the same theme-init + theme-toggle behavior.

Runs two ways:
  • imported: build_data.py calls generate_details(data) at the end of its run
    so the daily cron keeps detail pages fresh.
  • standalone: `python3 gen_details.py` loads the EXISTING data.json (no network
    fetch) and regenerates everything.

slugify() MUST stay byte-for-byte equivalent to app.js's slugify() so the hub
rows' internal hrefs resolve.
"""
from __future__ import annotations
import json, os, re, html, shutil
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://stacktracker.kymatalabs.com"
ORG = "Kymata Labs"


def slugify(owner: str, name: str) -> str:
    """lowercase url-safe slug from 'owner-name'. Mirror of app.js slugify()."""
    s = f"{owner}-{name}".lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _esc(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def rel_date(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        d = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    except Exception:
        return None
    if d < 1:
        return "today"
    if d < 2:
        return "yesterday"
    if d < 30:
        return f"{round(d)}d ago"
    if d < 365:
        return f"{round(d/30)}mo ago"
    return f"{round(d/365)}y ago"


def fmt_int(n) -> str:
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n)


def fmt_stars(n) -> str:
    n = int(n or 0)
    if n >= 1000:
        v = n / 1000.0
        s = f"{v:.0f}" if n >= 10000 else f"{v:.1f}".rstrip("0").rstrip(".")
        return s + "k"
    return str(n)


def momentum_components(recent4: int, prior4: int, days_release):
    """Recompute the three momentum sub-scores EXACTLY as build_data.momentum()
    does, so the detail page can show the weighted breakdown + the math.
    Returns a dict of 0..1 component values, their weights, and weighted points.
    Kept byte-for-byte equivalent to build_data.momentum() — if that changes,
    change this too (there's a CI-style assertion in __main__ self-check)."""
    act = min(recent4 / 400.0, 1.0)
    if days_release is None:
        rel = 0.2
    else:
        rel = max(0.0, 1.0 - max(0.0, days_release - 30) / 240.0)
    if prior4 > 0:
        tr = min(max((recent4 - prior4) / prior4 * 0.5 + 0.5, 0.0), 1.0)
    else:
        tr = 0.7 if recent4 > 0 else 0.5
    weights = {"act": 0.55, "rel": 0.25, "tr": 0.20}
    comps = {"act": act, "rel": rel, "tr": tr}
    points = {k: round(100 * weights[k] * comps[k], 1) for k in comps}
    total = round(100 * sum(weights[k] * comps[k] for k in comps))
    return {"comps": comps, "weights": weights, "points": points, "total": max(0, min(100, total))}


def _days_since(iso):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    except Exception:
        return None


def _component_row(label: str, desc: str, frac: float, weight: float, pts: float, raw: str) -> str:
    pct = max(0.0, min(1.0, frac)) * 100
    return (
        f'<div class="cmp">'
        f'<div class="cmp-head"><span class="cmp-name">{_esc(label)}</span>'
        f'<span class="cmp-w">{int(weight*100)}% weight</span>'
        f'<span class="cmp-pts">+{pts:.1f} pts</span></div>'
        f'<div class="cmp-track"><i style="width:{pct:.1f}%"></i></div>'
        f'<div class="cmp-foot"><span class="cmp-desc">{_esc(desc)}</span>'
        f'<span class="cmp-raw">{_esc(raw)} &middot; {pct:.0f}/100</span></div>'
        f'</div>'
    )


def commit_chart(arr, w=760, h=210) -> str:
    """Detail-page commit-volume chart: phosphor-trace area + value-labelled
    points + a baseline graticule, drawn at the chart's true aspect (no x/y
    distortion — preserveAspectRatio is on so it scales cleanly). Values are
    the 6 monthly (30-day) commit buckets, oldest → newest."""
    if not arr or len(arr) < 2:
        return '<div class="dt-chart-empty"><span class="ph">— commit signal warming up —</span></div>'
    n = len(arr)
    padL, padR, padT, padB = 8, 8, 26, 30
    mx = max(arr)
    top = mx if mx > 0 else 1
    plotw, ploth = w - padL - padR, h - padT - padB
    def X(i): return padL + i * plotw / (n - 1)
    def Y(v): return padT + ploth - (v / top) * ploth
    pts = [(X(i), Y(v)) for i, v in enumerate(arr)]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    base = padT + ploth
    area = f"{X(0):.1f},{base:.1f} " + poly + f" {X(n-1):.1f},{base:.1f}"
    # horizontal graticule lines (0, mid, max)
    grid = ""
    for g in (0.0, 0.5, 1.0):
        gy = padT + ploth - g * ploth
        grid += f'<line x1="{padL}" y1="{gy:.1f}" x2="{w-padR}" y2="{gy:.1f}" class="ch-grid"/>'
    # value labels at each point + month-offset labels along the baseline
    labels = ""
    for i, (x, y) in enumerate(pts):
        v = arr[i]
        labels += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="var(--scope-trace)" opacity=".85"/>'
        labels += f'<text x="{x:.1f}" y="{y-9:.1f}" class="ch-val" text-anchor="middle">{v}</text>'
        mo = n - 1 - i
        ml = "now" if mo == 0 else f"-{mo}mo"
        labels += f'<text x="{x:.1f}" y="{h-9:.1f}" class="ch-x" text-anchor="middle">{ml}</text>'
    lx, ly = pts[-1]
    return (
        f'<svg class="dt-chart" viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="Monthly commit volume over the last 6 months: {", ".join(str(v) for v in arr)} commits per 30-day window, oldest to newest.">'
        f'{grid}'
        f'<polygon points="{area}" fill="var(--phos-trail)" stroke="none"/>'
        f'<polyline points="{poly}" fill="none" stroke="var(--scope-trace)" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>'
        f'{labels}'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4" fill="var(--scope-dot)"/></svg>'
    )


def rank_chart(rhist: list, w=760, h=150) -> str:
    """Race-position chart: an INVERTED rank-over-time trace (rank #1 plotted at the
    top, so a climb reads as an upward line). Self-contained — the baseline is the
    series' OWN worst rank, not an outer `total`: worst→0, best→largest, so the
    polyline rises when the repo climbs. Points are labelled with the actual rank."""
    ranks = [int(p.get("rank")) for p in (rhist or []) if isinstance(p.get("rank"), int)]
    if len(ranks) < 2:
        return '<div class="dt-chart-empty"><span class="ph">— position movement fills in as the board runs daily —</span></div>'
    worst = max(ranks)
    # invert: a smaller (better) rank → larger plotted value → higher on the chart
    series = [max(1, (worst + 1) - rv) for rv in ranks]
    n = len(series)
    padL, padR, padT, padB = 8, 8, 26, 30
    top = max(series) or 1
    plotw, ploth = w - padL - padR, h - padT - padB
    def X(i): return padL + i * plotw / (n - 1)
    def Y(v): return padT + ploth - (v / top) * ploth
    pts = [(X(i), Y(v)) for i, v in enumerate(series)]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    base = padT + ploth
    area = f"{X(0):.1f},{base:.1f} " + poly + f" {X(n-1):.1f},{base:.1f}"
    grid = ""
    for g in (0.0, 0.5, 1.0):
        gy = padT + ploth - g * ploth
        grid += f'<line x1="{padL}" y1="{gy:.1f}" x2="{w-padR}" y2="{gy:.1f}" class="ch-grid"/>'
    labels = ""
    for i, (x, y) in enumerate(pts):
        labels += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="var(--scope-trace)" opacity=".85"/>'
        labels += f'<text x="{x:.1f}" y="{y-9:.1f}" class="ch-val" text-anchor="middle">#{ranks[i]}</text>'
        days_ago = n - 1 - i
        ml = "now" if days_ago == 0 else f"-{days_ago}d"
        labels += f'<text x="{x:.1f}" y="{h-9:.1f}" class="ch-x" text-anchor="middle">{ml}</text>'
    lx, ly = pts[-1]
    return (
        f'<svg class="dt-chart" viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="Board position over the last {n} days tracked, oldest to newest: ranks {", ".join("#"+str(rv) for rv in ranks)}. Higher on the chart means a better rank.">'
        f'{grid}'
        f'<polygon points="{area}" fill="var(--phos-trail)" stroke="none"/>'
        f'<polyline points="{poly}" fill="none" stroke="var(--scope-trace)" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>'
        f'{labels}'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4" fill="var(--scope-dot)"/></svg>'
    )


def _badge_svg(r: dict) -> str:
    """shields.io-style embeddable rank badge. Left label "StackTracker", right
    "#<rank>" in the app's phosphor green; appends "▲N" when the repo climbed
    (rank_delta > 0). Self-contained, theme-neutral, accessible (role/title).
    Character-width estimation keeps the right pill snug without a web font."""
    rank = r.get("rank")
    rank_txt = f"#{rank}" if isinstance(rank, int) else "#—"
    delta = r.get("rank_delta")
    if isinstance(delta, int) and delta > 0:
        rank_txt = f"{rank_txt} ▲{delta}"
    label = "StackTracker"
    name = r.get("name", "") or r.get("repo", "")
    # ~6px per char @ 11px; +pad. Stable, no font metrics needed.
    lw = len(label) * 6 + 18
    rw = len(rank_txt) * 6 + 18
    total = lw + rw
    title = f"StackTracker — {_esc(name)} ranked {rank_txt}"
    # unique gradient id per badge — guards against id collision if multiple badges
    # are ever inlined together on a third-party page (img-embeds are already isolated).
    # falls back to the repo's rank so the id is still unique when owner/name are blank.
    gid = f"st{slugify(r.get('owner', '') or '', name) or ('r' + str(rank if isinstance(rank, int) else 'x'))}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" '
        f'role="img" aria-label="{title}">'
        f'<title>{title}</title>'
        f'<linearGradient id="{gid}" x2="0" y2="100%">'
        f'<stop offset="0" stop-color="#fff" stop-opacity=".12"/>'
        f'<stop offset="1" stop-opacity=".12"/></linearGradient>'
        f'<clipPath id="{gid}r"><rect width="{total}" height="20" rx="3" fill="#fff"/></clipPath>'
        f'<g clip-path="url(#{gid}r)">'
        f'<rect width="{lw}" height="20" fill="#0c1310"/>'
        f'<rect x="{lw}" width="{rw}" height="20" fill="#107a52"/>'
        f'<rect width="{total}" height="20" fill="url(#{gid})"/></g>'
        f'<g fill="#fff" text-anchor="middle" '
        f'font-family="Verdana,DejaVu Sans,Geneva,sans-serif" font-size="11">'
        f'<text x="{lw/2:.0f}" y="14">{label}</text>'
        f'<text x="{lw + rw/2:.0f}" y="14" font-weight="bold">{_esc(rank_txt)}</text>'
        f'</g></svg>'
    )


def generate_badges(data: dict, here: str = HERE) -> int:
    """Write a static /badge/<slug>.svg per repo (mirrors detail-page generation).
    Static-deployable: no serverless needed; the daily build refreshes each badge.
    Stale badges (repos that left the index) are pruned."""
    repos = data.get("repos", [])
    b_dir = os.path.join(here, "badge")
    os.makedirs(b_dir, exist_ok=True)
    # default-guard owner/name so a malformed record can never crash the daily cron
    # (production blast radius); empty slugs are skipped, never written as ".svg".
    fresh = {s for s in (slugify(r.get("owner", ""), r.get("name", "")) for r in repos) if s}
    for fn in os.listdir(b_dir):
        if fn.endswith(".svg") and fn[:-4] not in fresh:
            try:
                os.remove(os.path.join(b_dir, fn))
            except OSError:
                pass
    written = 0
    for r in repos:
        slug = slugify(r.get("owner", ""), r.get("name", ""))
        if not slug:
            continue
        with open(os.path.join(b_dir, f"{slug}.svg"), "w", encoding="utf-8") as f:
            f.write(_badge_svg(r))
        written += 1
    return written


def generate_feed(data: dict, here: str = HERE) -> None:
    """Write feed.json — a small, documented, stable-schema public API subset of
    the board (read-only data already public on the page; no secrets)."""
    # explicit None-check (not `or 999`) so a present-but-None rank can't raise
    # TypeError on the Py3 sort comparison and crash the daily cron build, while a
    # legitimate rank 0 still sorts correctly.
    repos = sorted(data.get("repos", []),
                   key=lambda x: x.get("rank") if isinstance(x.get("rank"), int) else 999)
    # only emit repos with a non-empty slug — mirrors generate_badges() so the
    # feed never advertises a broken /p// or /badge/.svg URL for a malformed record.
    feed_repos = [r for r in repos if slugify(r.get("owner", ""), r.get("name", ""))]
    feed = {
        "$schema_version": "1",
        "generator": "StackTracker (Kymata Labs)",
        "generated_at": data.get("generated_at"),
        "site": BASE,
        "docs": f"{BASE}/#how",
        "license": "Data derived from the public GitHub REST API; attribution to StackTracker (kymatalabs.com) appreciated.",
        "count": len(feed_repos),
        "repos": [
            {
                "rank": r.get("rank"),
                "name": r.get("name"),
                "owner": r.get("owner"),
                "category": r.get("category"),
                "momentum": r.get("momentum"),
                "stars": r.get("stars"),
                "contributors": r.get("contributors"),
                "rank_delta": r.get("rank_delta"),
                "url": f"{BASE}/p/{slugify(r.get('owner', ''), r.get('name', ''))}/",
                "badge": f"{BASE}/badge/{slugify(r.get('owner', ''), r.get('name', ''))}.svg",
            }
            for r in feed_repos
        ],
        "movers": data.get("movers", []),
    }
    with open(os.path.join(here, "feed.json"), "w", encoding="utf-8") as f:
        json.dump(feed, f, indent=2)


def generate_rss(data: dict, here: str = HERE) -> None:
    """Write rss.xml — an RSS 2.0 feed of the current momentum board (top entries by
    rank) so researchers / builders / journalists can subscribe. Per-entry guids are the
    stable detail-page URLs; pubDate is the board's daily refresh. Additive, read-only
    public data (same subset the page already shows)."""
    from email.utils import format_datetime
    repos = sorted(data.get("repos", []),
                   key=lambda x: x.get("rank") if isinstance(x.get("rank"), int) else 999)
    feed_repos = [r for r in repos if slugify(r.get("owner", ""), r.get("name", ""))][:30]
    gen_iso = data.get("generated_at")
    try:
        dt = datetime.fromisoformat(gen_iso) if gen_iso else datetime.now(timezone.utc)
    except (TypeError, ValueError):
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    rfc = format_datetime(dt)
    title = "StackTracker — live AI-infra momentum"
    desc = ("The live momentum index for open-source AI infrastructure — ranked by real "
            "GitHub velocity, recomputed daily by autonomous agents.")
    items = []
    for r in feed_repos:
        slug = slugify(r.get("owner", ""), r.get("name", ""))
        url = f"{BASE}/p/{slug}/"
        rank, mom, cat = r.get("rank"), r.get("momentum"), r.get("category")
        rd = r.get("rank_delta")
        move = f" ▲{rd}" if isinstance(rd, int) and rd > 0 else (
               f" ▼{abs(rd)}" if isinstance(rd, int) and rd < 0 else "")
        ttl = f"#{rank} {r.get('name')} — momentum {mom}"
        body = f"#{rank} · momentum {mom}/100 · {cat}{move} · {r.get('stars')} stars"
        items.append(
            "    <item>\n"
            f"      <title>{_esc(ttl)}</title>\n"
            f"      <link>{_esc(url)}</link>\n"
            f'      <guid isPermaLink="true">{_esc(url)}</guid>\n'
            f"      <category>{_esc(cat)}</category>\n"
            f"      <description>{_esc(body)}</description>\n"
            f"      <pubDate>{rfc}</pubDate>\n"
            "    </item>")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{_esc(title)}</title>\n"
        f"    <link>{BASE}</link>\n"
        f'    <atom:link href="{BASE}/rss.xml" rel="self" type="application/rss+xml"/>\n'
        f"    <description>{_esc(desc)}</description>\n"
        "    <language>en</language>\n"
        f"    <lastBuildDate>{rfc}</lastBuildDate>\n"
        f"    <generator>{_esc(ORG)}</generator>\n"
        + "\n".join(items) + "\n"
        "  </channel>\n</rss>\n")
    with open(os.path.join(here, "rss.xml"), "w", encoding="utf-8") as f:
        f.write(xml)


# ── shared chrome (matches index.html exactly) ──
HEAD_COMMON = """<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<link rel="icon" href="/favicon.svg">
<link rel="stylesheet" href="/style.css">
<script>(function(){try{var s=localStorage.getItem("theme");var t=s||(window.matchMedia&&window.matchMedia("(prefers-color-scheme:light)").matches?"light":"dark");document.documentElement.dataset.theme=t;}catch(e){document.documentElement.dataset.theme="dark";}})();</script>"""

NAV = """<nav id="nav"><div class="wrap nav-in">
  <a class="brand" href="/">
    <span class="mark"><svg width="26" height="14" viewBox="0 0 26 14" fill="none"><path d="M1 7 H5 L7 2 L10 12 L13 4 L15 7 H25" stroke="#3dffa6" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
    StackTracker <span class="by">// Kymata Labs</span>
  </a>
  <div class="nav-links">
    <a href="/#index">The index</a>
    <a href="/#how" class="hidem">How it's made</a>
    <a href="https://kymatalabs.com/" class="hidem">Kymata Labs &#8599;</a>
    <button class="theme-toggle" id="themeToggle" type="button" aria-label="Toggle light/dark theme" title="Toggle theme">
      <svg class="i-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/><path d="M12 2v2.5M12 19.5V22M4.2 4.2l1.8 1.8M18 18l1.8 1.8M2 12h2.5M19.5 12H22M4.2 19.8 6 18M18 6l1.8-1.8"/></svg>
      <svg class="i-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.6 6.6 0 0 0 9.8 9.8z"/></svg>
    </button>
  </div>
</div></nav>"""

FOOTER = """<footer><div class="wrap">
  <span class="mono" style="color:var(--phos)">How it's made</span>
  <h2>A self-updating intelligence instrument, <em>built and run by an AI agent.</em></h2>
  <p>Every figure on this page traces to a live GitHub API response, sampled daily by an autonomous agent that recomputes the momentum score and redeploys &mdash; no human in the loop. Same agent stack that runs <a href="https://kymatalabs.com/" style="color:var(--phos)">Kymata Labs</a>.</p>
  <div class="how">
    <div><div class="mono">01 &middot; Sample</div><p>Daily GitHub API fetch: stars, releases, and commit history for every tracked repo.</p></div>
    <div><div class="mono">02 &middot; Score</div><p>Momentum = commit velocity (55%) + release recency (25%) + 6-month trend (20%).</p></div>
    <div><div class="mono">03 &middot; Sweep</div><p>A GitHub Action recomputes <code>data.json</code> and redeploys &mdash; no human in the loop.</p></div>
  </div>
  <div class="foot-row">
    <span>Data regenerated daily</span>
    <span>&copy; 2026 Kymata Labs &middot; StackTracker</span>
    <a href="https://kymatalabs.com/">kymatalabs &#8599;</a>
  </div>
</div></footer>"""

THEME_SCRIPT = """<script>
/* theme toggle + nav scroll state (shared with index.html) */
(function(){
  var btn=document.getElementById("themeToggle");
  if(btn){btn.addEventListener("click",function(){
    var cur=document.documentElement.dataset.theme==="light"?"light":"dark";
    var next=cur==="light"?"dark":"light";
    document.documentElement.dataset.theme=next;
    try{localStorage.setItem("theme",next);}catch(e){}
    var mc=document.querySelector('meta[name="theme-color"]'); if(mc) mc.setAttribute("content",next==="light"?"#eef3f0":"#070a09");
    window.dispatchEvent(new CustomEvent("themechange",{detail:next}));
  });}
  var nav=document.getElementById("nav");
  if(nav){var on=function(){nav.classList.toggle("scrolled",window.scrollY>20)};window.addEventListener("scroll",on,{passive:true});on();}
})();
/* count-up for the momentum score (respects reduced-motion) */
(function(){
  if(window.matchMedia && window.matchMedia("(prefers-reduced-motion:reduce)").matches) return;
  var el=document.querySelector(".score[data-count]"); if(!el) return;
  var target=parseFloat(el.getAttribute("data-count"))||0; if(target<=0){return;}
  var start=null, dur=850;
  function step(now){ if(start===null)start=now; var t=Math.min((now-start)/dur,1);
    var e=1-Math.pow(1-t,3); el.textContent=Math.round(target*e); if(t<1)requestAnimationFrame(step); else el.textContent=target; }
  el.textContent="0"; requestAnimationFrame(step);
})();
/* oscilloscope hero — phosphor trace, theme-aware (mirrors index.html) */
(function(){
  if(window.matchMedia && window.matchMedia("(prefers-reduced-motion:reduce)").matches) return;
  var cv=document.getElementById("scope"); if(!cv) return;
  var ctx=cv.getContext("2d"), W=0,H=0,dpr=Math.min(window.devicePixelRatio||1,2), t=0, raf;
  var BG="#070a09", TRACE="61,255,166", DOT="#9affd0";
  function hexToRGB(h){h=h.trim();if(h[0]!=="#")return null;if(h.length===4)h="#"+h[1]+h[1]+h[2]+h[2]+h[3]+h[3];var n=parseInt(h.slice(1),16);return (n>>16&255)+","+(n>>8&255)+","+(n&255);}
  function readTheme(){var cs=getComputedStyle(document.documentElement);
    BG=(cs.getPropertyValue("--scope-bg")||"#070a09").trim()||"#070a09";
    TRACE=hexToRGB((cs.getPropertyValue("--scope-trace")||"#3dffa6").trim())||"61,255,166";
    DOT=(cs.getPropertyValue("--scope-dot")||"#9affd0").trim()||"#9affd0";}
  function fadeRGB(){var rgb=hexToRGB(BG)||"7,10,9";return "rgba("+rgb+",0.16)";}
  function size(){W=cv.clientWidth;H=cv.clientHeight;cv.width=W*dpr;cv.height=H*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.fillStyle=BG;ctx.fillRect(0,0,W,H);}
  function wave(x){var k=x/W;return Math.sin(k*6.0+t*1.1)*0.46+Math.sin(k*15.0-t*1.7)*0.18+Math.sin(k*31.0+t*2.3)*0.07;}
  function frame(){ctx.globalCompositeOperation="source-over";ctx.fillStyle=fadeRGB();ctx.fillRect(0,0,W,H);
    var midY=H*0.52,amp=H*0.30;ctx.globalCompositeOperation="lighter";
    for(var pass=0;pass<2;pass++){ctx.beginPath();
      for(var x=0;x<=W;x+=2){var y=midY-wave(x)*amp;if(x===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}
      ctx.lineWidth=pass===0?7:1.6;ctx.strokeStyle=pass===0?"rgba("+TRACE+",0.07)":"rgba("+TRACE+",0.85)";
      ctx.shadowColor="rgba("+TRACE+",0.7)";ctx.shadowBlur=pass===0?0:12;ctx.stroke();}
    var bx=(t*120)%W,by=midY-wave(bx)*amp;ctx.beginPath();ctx.arc(bx,by,2.6,0,6.2832);ctx.fillStyle=DOT;ctx.shadowBlur=16;ctx.fill();ctx.shadowBlur=0;
    t+=0.016;raf=requestAnimationFrame(frame);}
  readTheme();size();window.addEventListener("resize",size);
  window.addEventListener("themechange",function(){readTheme();ctx.fillStyle=BG;ctx.fillRect(0,0,W,H);});
  document.addEventListener("visibilitychange",function(){if(document.hidden){cancelAnimationFrame(raf);}else{raf=requestAnimationFrame(frame);}});
  ctx.fillStyle=BG;ctx.fillRect(0,0,W,H);raf=requestAnimationFrame(frame);
})();
</script>"""


def detail_html(r: dict, all_repos: list | None = None) -> str:
    all_repos = all_repos or []
    slug = slugify(r["owner"], r["name"])
    url = f"{BASE}/p/{slug}/"
    # embeddable rank badge — the viral loop (repos display their rank, link back here)
    badge_url = f"{BASE}/badge/{slug}.svg"
    embed_md = f"[![StackTracker rank]({badge_url})]({url})"
    embed_html = f'<a href="{url}"><img src="{badge_url}" alt="StackTracker rank"></a>'
    title = f"{r['name']} by {r['owner']} — momentum {r.get('momentum',0)}/100 · StackTracker"
    blurb = r.get("blurb") or f"{r['owner']}/{r['name']} — tracked AI-infra project."
    desc = f"{r['owner']}/{r['name']}: {blurb} {fmt_int(r.get('stars',0))} stars, momentum {r.get('momentum',0)}/100, {r.get('recent4w_commits',0)} commits in the last 30 days. Live GitHub velocity, recomputed daily."
    desc = desc[:300]
    cat = r.get("category", "AI infrastructure")
    mom = r.get("momentum", 0)
    delta = r.get("commit_delta", 0)
    recent4 = r.get("recent4w_commits", 0)
    prior4 = r.get("prior4w_commits", 0)
    rank = r.get("rank")
    total_n = len(all_repos) or r.get("rank") or 0
    if delta > 3:
        dcls, dtxt = "up", f"&#9650; +{delta} vs prior month"
    elif delta < -3:
        dcls, dtxt = "dn", f"&#9660; {delta} vs prior month"
    else:
        dcls, dtxt = "", "&#8594; steady"
    rel_at = r.get("last_release_at")
    rel_line = (
        f"{_esc(r['last_release'])} &middot; {rel_date(rel_at) or '—'}"
        if r.get("last_release") else "no published release"
    )
    pushed = rel_date(r.get("pushed_at")) or "—"
    homepage = (r.get("homepage") or "").strip()
    home_btn = (
        f'<a class="dt-btn" href="{_esc(homepage)}" target="_blank" rel="noopener">Homepage &#8599;</a>'
        if homepage else ""
    )
    archived = '<span class="arch">archived</span>' if r.get("archived") else ""

    # ── race-position movement: the climbed/slipped badge + an inverted rank-over-
    # time trace (rank #1 at the top, so "up = climbing"). rank_delta > 0 == climbed. ──
    rank_delta = r.get("rank_delta")
    rhist = r.get("rank_history") or []
    if isinstance(rank_delta, int) and rank_delta > 0:
        move_badge = f'<span class="d-move up" title="Climbed {rank_delta} since prior run">&#9650; {rank_delta}</span>'
        move_word = f"climbed {rank_delta} position{'s' if rank_delta != 1 else ''}"
    elif isinstance(rank_delta, int) and rank_delta < 0:
        move_badge = f'<span class="d-move dn" title="Slipped {abs(rank_delta)} since prior run">&#9660; {abs(rank_delta)}</span>'
        move_word = f"slipped {abs(rank_delta)} position{'s' if abs(rank_delta) != 1 else ''}"
    elif isinstance(rank_delta, int):
        move_badge = '<span class="d-move flat" title="Held position">&#8594;</span>'
        move_word = "held position"
    else:
        move_badge = '<span class="d-move new" title="New to the tracked board">NEW</span>'
        move_word = "new to the board"
    peak = r.get("peak_rank", rank)
    if len([p for p in rhist if isinstance(p.get("rank"), int)]) >= 2:
        rank_panel = rank_chart(rhist)
        rank_note = f"Position over the last {len(rhist)} days tracked &middot; best: #{peak}."
    else:
        rank_panel = '<div class="dt-chart-empty"><span class="ph">— position movement fills in as the board runs daily —</span></div>'
        rank_note = "Position movement fills in as the board runs daily."

    # ── momentum score breakdown (recomputed from the same inputs) ──
    d_rel = _days_since(rel_at)
    mc = momentum_components(recent4, prior4, d_rel)
    act_raw = f"{recent4} commits / 30d"
    if d_rel is None:
        rel_raw = "no release (floor)"
    else:
        rel_raw = f"released {int(round(d_rel))}d ago"
    if prior4 > 0:
        pct_mom = (recent4 - prior4) / prior4 * 100
        tr_raw = f"{'+' if pct_mom>=0 else ''}{pct_mom:.0f}% vs prior 30d"
    else:
        tr_raw = "no prior-month baseline"
    breakdown = (
        _component_row("Commit velocity", "How hard the repo is shipping right now (caps at ~400 commits/30d).",
                       mc["comps"]["act"], mc["weights"]["act"], mc["points"]["act"], act_raw)
        + _component_row("Release recency", "How recently a stable release shipped (full credit < 30d, decays to ~270d).",
                         mc["comps"]["rel"], mc["weights"]["rel"], mc["points"]["rel"], rel_raw)
        + _component_row("Commit trend", "This 30-day window versus the one before it — acceleration or cool-off.",
                         mc["comps"]["tr"], mc["weights"]["tr"], mc["points"]["tr"], tr_raw)
    )

    # ── category peers (same category, by rank, excluding self) ──
    peers = [p for p in all_repos if p.get("category") == cat and p.get("repo") != r.get("repo")]
    peers.sort(key=lambda p: p.get("rank", 9999))
    peer_cards = ""
    for p in peers[:6]:
        pslug = slugify(p["owner"], p["name"])
        pd = p.get("commit_delta", 0)
        pcls = "up" if pd > 3 else ("dn" if pd < -3 else "flat")
        psign = "&#9650;" if pd > 3 else ("&#9660;" if pd < -3 else "&#8594;")
        peer_cards += (
            f'<a class="peer" href="/p/{_esc(pslug)}/">'
            f'<div class="peer-top"><span class="peer-rank">#{p.get("rank","—")}</span>'
            f'<span class="peer-mom">{p.get("momentum",0)}</span></div>'
            f'<div class="peer-name">{_esc(p["name"])}</div>'
            f'<div class="peer-meta"><span>{fmt_stars(p.get("stars",0))}&#9733;</span>'
            f'<span class="peer-d {pcls}">{psign} {abs(pd)}/mo</span></div></a>'
        )
    peers_section = (
        f'''  <section class="dt-panel" id="peers">
    <h2>Category peers &middot; {_esc(cat)}</h2>
    <p class="dt-note">Other tracked {_esc(cat)} projects, ranked by live momentum. The fastest way to see where {_esc(r["name"])} sits in its lane.</p>
    <div class="peer-grid">{peer_cards}</div>
  </section>'''
        if peer_cards else ""
    )

    # rank context line
    if rank and total_n:
        rank_ctx = f"#{rank} of {total_n} tracked"
        cat_peer_n = len([p for p in all_repos if p.get("category") == cat])
        cat_rank = sorted([p for p in all_repos if p.get("category") == cat],
                          key=lambda p: p.get("rank", 9999))
        cat_pos = next((i + 1 for i, p in enumerate(cat_rank) if p.get("repo") == r.get("repo")), None)
        rank_cat_ctx = f"#{cat_pos} of {cat_peer_n} in {cat}" if cat_pos else cat
    else:
        rank_ctx, rank_cat_ctx = "—", cat

    breadcrumb = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{BASE}/"},
            {"@type": "ListItem", "position": 2, "name": "StackTracker", "item": f"{BASE}/#index"},
            {"@type": "ListItem", "position": 3, "name": f"{r['owner']}/{r['name']}", "item": url},
        ],
    }
    software = {
        "@context": "https://schema.org", "@type": "SoftwareSourceCode",
        "name": r["name"], "codeRepository": r.get("html_url"),
        "url": url, "description": blurb,
        "programmingLanguage": r.get("language") or "—",
        "author": {"@type": "Organization", "name": r["owner"]},
        "isAccessibleForFree": True,
        "applicationCategory": cat,
        "interactionStatistic": {
            "@type": "InteractionCounter",
            "interactionType": "https://schema.org/LikeAction",
            "userInteractionCount": int(r.get("stars", 0)),
        },
        "publisher": {"@type": "Organization", "name": ORG, "url": "https://kymatalabs.com/"},
    }
    ld = json.dumps([breadcrumb, software], separators=(",", ":"))

    stat = lambda v, l, accent="": f'<div class="s{accent}"><b>{v}</b><span>{l}</span></div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{url}">
<meta name="theme-color" content="#070a09">
<meta property="og:type" content="website">
<meta property="og:title" content="{_esc(r['name'])} — momentum {r.get('momentum',0)}/100 · StackTracker">
<meta property="og:description" content="{_esc(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{BASE}/og.png">
<meta property="og:site_name" content="StackTracker">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{_esc(r['name'])} — momentum {r.get('momentum',0)}/100 · StackTracker">
<meta name="twitter:description" content="{_esc(desc)}">
<meta name="twitter:image" content="{BASE}/og.png">
{HEAD_COMMON}
<script type="application/ld+json">{ld}</script>
</head>
<body>
<canvas id="scope" aria-hidden="true"></canvas>
<div class="vig"></div>
{NAV}
<main class="detail"><div class="wrap">
  <a class="backlink" href="/">&#8592; Back to the index</a>
  <div class="dt-head">
    <div>
      <div class="dcat"><span style="width:7px;height:7px;background:var(--phos);border-radius:50%;display:inline-block;box-shadow:0 0 10px var(--phos)"></span> {_esc(cat)}</div>
      <h1>{_esc(r['name'])} <span class="downer">/ {_esc(r['owner'])}</span> {archived} {move_badge}</h1>
      <p class="dblurb">{_esc(blurb)}</p>
    </div>
    <div class="dt-out">
      <a class="dt-btn primary" href="{_esc(r.get('html_url'))}" target="_blank" rel="noopener">View on GitHub &#8599;</a>
      {home_btn}
    </div>
  </div>

  <div class="statgrid">
    {stat(mom, 'Momentum', ' accent')}
    {stat('#'+str(rank) if rank else '—', 'Overall rank')}
    {stat(fmt_stars(r.get('stars',0)), 'Stars')}
    {stat(fmt_int(recent4), 'Commits / 30d')}
  </div>

  <section class="dt-panel hero-panel">
    <h2>Momentum signal</h2>
    <div class="dt-momentum">
      <div class="score-wrap"><span class="score" data-count="{mom}">{mom}</span><span class="score-of">/ 100</span></div>
      <div class="dt-momentum-body">
        <div class="bar" role="meter" aria-valuenow="{mom}" aria-valuemin="0" aria-valuemax="100" aria-label="Momentum score {mom} of 100"><i style="width:{mom}%"></i></div>
        <div class="rank-ctx"><span class="rc">{rank_ctx}</span><span class="rc">{rank_cat_ctx}</span></div>
      </div>
    </div>
    <div class="dt-meta" style="margin-top:24px">
      <div><span class="k">Commits &middot; last 30d</span><span class="v">{fmt_int(recent4)}</span></div>
      <div><span class="k">Commits &middot; prior 30d</span><span class="v">{fmt_int(prior4)}</span></div>
      <div><span class="k">Month-over-month</span><span class="v {dcls}">{dtxt}</span></div>
    </div>
  </section>

  <section class="dt-panel">
    <h2>Score breakdown</h2>
    <p class="dt-note">Momentum is a weighted blend of three live GitHub signals. Each bar shows that signal's normalized strength (0&ndash;100) and the points it contributes to the {mom}/100 total.</p>
    <div class="cmp-list">{breakdown}</div>
    <div class="cmp-total"><span class="ct-eq">0.55 &middot; velocity &nbsp;+&nbsp; 0.25 &middot; recency &nbsp;+&nbsp; 0.20 &middot; trend</span><span class="ct-val">= {mom} / 100</span></div>
  </section>

  <section class="dt-panel">
    <h2>Commit volume &middot; last 6 months</h2>
    <p class="dt-note">Six rolling 30-day windows of commit counts, pulled straight from the GitHub commits API &mdash; the same series that drives the velocity and trend signals above.</p>
    {commit_chart(r.get('monthly_commits') or [])}
  </section>

  <section class="dt-panel">
    <h2>Race position over time</h2>
    <p class="dt-note">Where {_esc(r['name'])} sits on the board, tracked daily &mdash; {move_word} since the prior run. {rank_note} The trace is inverted so a climb reads as an upward line.</p>
    {rank_panel}
    <div class="statgrid" style="margin-top:24px">
      {stat('#'+str(rank) if rank else '—', 'Current rank', ' accent')}
      {stat('#'+str(peak) if peak else '—', 'Best rank')}
      {stat(move_badge, 'Since prior run')}
      {stat(r.get('tracked_days', 1), 'Days tracked')}
    </div>
  </section>

  <section class="dt-panel">
    <h2>Latest release</h2>
    <div class="release">
      <div class="rel-tag">{_esc(r['last_release']) if r.get('last_release') else '<span class="rel-none">No published release</span>'}</div>
      <div class="rel-when">{('shipped '+(rel_date(rel_at) or '—')) if r.get('last_release') else 'Momentum uses a recency floor for repos without a tagged release.'}</div>
    </div>
    <div class="dt-meta" style="margin-top:20px">
      <div><span class="k">Release recency signal</span><span class="v">{mc['points']['rel']:.1f} of 25 pts</span></div>
      <div><span class="k">Last code push</span><span class="v">{pushed}</span></div>
      <div><span class="k">Release tag</span><span class="v">{_esc(r['last_release']) if r.get('last_release') else '—'}</span></div>
    </div>
  </section>

{peers_section}

  <section class="dt-panel" id="embed">
    <h2>Embed this badge</h2>
    <p class="dt-note">Show your live StackTracker rank in your README &mdash; it updates daily and links back here.</p>
    <p style="margin:16px 0"><img src="{badge_url}" alt="StackTracker rank badge for {_esc(r['name'])}" style="vertical-align:middle"></p>
    <div class="embed-snip">
      <span class="k">Markdown</span>
      <pre class="embed-code"><code>{_esc(embed_md)}</code></pre>
      <span class="k" style="margin-top:14px;display:block">HTML</span>
      <pre class="embed-code"><code>{_esc(embed_html)}</code></pre>
    </div>
  </section>

  <section class="dt-panel">
    <h2>Repository</h2>
    <div class="dt-meta">
      <div><span class="k">Language</span><span class="v">{_esc(r.get('language') or '—')}</span></div>
      <div><span class="k">Category</span><span class="v">{_esc(cat)}</span></div>
      <div><span class="k">Stars</span><span class="v">{fmt_int(r.get('stars',0))}</span></div>
      <div><span class="k">Forks</span><span class="v">{fmt_int(r.get('forks',0))}</span></div>
      <div><span class="k">Open issues</span><span class="v">{fmt_int(r.get('open_issues',0))}</span></div>
      <div><span class="k">Last pushed</span><span class="v">{pushed}</span></div>
      <div><span class="k">Last release</span><span class="v">{rel_line}</span></div>
      <div><span class="k">Archived</span><span class="v">{'yes' if r.get('archived') else 'no'}</span></div>
    </div>
    <div class="dt-links">
      <a class="dt-btn primary" href="{_esc(r.get('html_url'))}" target="_blank" rel="noopener">View on GitHub &#8599;</a>
      {home_btn}
    </div>
  </section>
</div></main>
{FOOTER}
{THEME_SCRIPT}
</body>
</html>
"""


def generate_details(data: dict, here: str = HERE) -> list[str]:
    """Write p/<slug>/index.html for every repo, regenerate sitemap.xml + llms.txt.
    Returns the list of slugs generated. Stale /p subdirs are pruned."""
    repos = data.get("repos", [])
    p_root = os.path.join(here, "p")

    # prune stale detail dirs (repos that left the index)
    fresh = {slugify(r["owner"], r["name"]) for r in repos}
    if os.path.isdir(p_root):
        for name in os.listdir(p_root):
            if name not in fresh and os.path.isdir(os.path.join(p_root, name)):
                shutil.rmtree(os.path.join(p_root, name), ignore_errors=True)

    slugs = []
    for r in repos:
        slug = slugify(r["owner"], r["name"])
        d = os.path.join(p_root, slug)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.html"), "w") as f:
            f.write(detail_html(r, repos))
        slugs.append(slug)

    _write_sitemap(here, slugs)
    _write_llms(here, data, slugs)
    generate_badges(data, here)
    generate_feed(data, here)
    generate_rss(data, here)
    return slugs


def _write_sitemap(here: str, slugs: list[str]) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = [f'  <url><loc>{BASE}/</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>']
    for s in slugs:
        rows.append(f'  <url><loc>{BASE}/p/{s}/</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq><priority>0.7</priority></url>')
    body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(rows) + "\n</urlset>\n"
    with open(os.path.join(here, "sitemap.xml"), "w") as f:
        f.write(body)


def _write_llms(here: str, data: dict, slugs: list[str]) -> None:
    today = data.get("generated_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    repos = data.get("repos", [])
    lines = [
        "# StackTracker",
        "",
        "> A live, momentum-ranked index of open-source AI-infrastructure projects — agent frameworks, inference engines, vector databases, gateways, and LLMOps tooling. Built and operated by an autonomous AI agent at Kymata Labs.",
        "",
        "## What it is",
        "StackTracker reads the open-source AI-infra stack like an instrument and answers one question: who is actually shipping, and who is flatlining. Each project gets a 0–100 momentum score.",
        "",
        "## How the score works",
        "Momentum = commit velocity (55%) + release recency (25%) + 6-month commit trend (20%). Every number traces to a real GitHub API response — no fabricated figures.",
        "",
        "## Source & cadence",
        "- Source: GitHub REST API (stars, releases, commit history).",
        f"- Cadence: recomputed daily by a GitHub Action; last build {today}.",
        f"- Coverage: {len(repos)} tracked repositories across {len(data.get('categories', []))} categories.",
        "- Operator: Kymata Labs (https://kymatalabs.com/).",
        "",
        "## Routes",
        "- `/` — the full momentum-ranked index. Filter by category; sort by momentum, stars, commits/mo, 4-week trend, or name; instant client-side search.",
        "- `/p/<slug>` — per-repo deep-dive: stat grid (momentum, rank, stars, commits/30d), the weighted score breakdown (velocity 55% + release recency 25% + commit trend 20%), a 6-month commit-volume chart, latest-release detail, category peers (linked), full repository metadata, and outbound links. Slug is the lowercased `owner-name`.",
        "",
        "## Index (current ranking)",
    ]
    for r in repos:
        slug = slugify(r["owner"], r["name"])
        lines.append(f"- [{r['owner']}/{r['name']}]({BASE}/p/{slug}/) — {r.get('category','')}, momentum {r.get('momentum',0)}/100, {fmt_int(r.get('stars',0))}★")
    lines.append("")
    with open(os.path.join(here, "llms.txt"), "w") as f:
        f.write("\n".join(lines))


def _selfcheck_momentum() -> None:
    """Guard: momentum_components(...)['total'] MUST equal build_data.momentum(...).
    If build_data's scoring drifts, fail loudly so the breakdown can't go stale."""
    try:
        from build_data import momentum as _bd_momentum
    except Exception:
        return  # build_data not importable (e.g. shipped dir) — skip silently
    cases = [(847, 391, 5), (41, 112, 19), (0, 0, None), (500, 10, 400), (12, 0, None), (300, 300, 95)]
    for recent4, prior4, d_rel in cases:
        want = _bd_momentum(recent4, prior4, d_rel)
        got = momentum_components(recent4, prior4, d_rel)["total"]
        assert got == want, (
            f"momentum breakdown drift for (recent4={recent4}, prior4={prior4}, "
            f"days_release={d_rel}): gen_details={got} vs build_data={want}. "
            f"Re-sync momentum_components() with build_data.momentum()."
        )


def main() -> int:
    _selfcheck_momentum()
    data_path = os.path.join(HERE, "data.json")
    if not os.path.exists(data_path):
        print("data.json not found; run build_data.py first", flush=True)
        return 1
    data = json.load(open(data_path))
    slugs = generate_details(data, HERE)
    print(f"generated {len(slugs)} detail pages, sitemap.xml ({len(slugs)+1} urls), llms.txt", flush=True)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
