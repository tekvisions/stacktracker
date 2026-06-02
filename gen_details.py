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


def sparkline_svg(arr, w=720, h=140) -> str:
    """Larger monthly_commits sparkline for the detail page."""
    if not arr or len(arr) < 2:
        return '<div class="dt-spark"><span class="ph">— sparkline warming up —</span></div>'
    mx, mn = max(arr), min(arr)
    rng = (mx - mn) or 1
    n = len(arr)
    pad = 6
    pts = []
    for i, v in enumerate(arr):
        x = pad + i * (w - 2 * pad) / (n - 1)
        y = h - pad - ((v - mn) / rng) * (h - 2 * pad)
        pts.append(f"{x:.1f},{y:.1f}")
    poly = " ".join(pts)
    area = f"{pad},{h-pad} " + poly + f" {w-pad},{h-pad}"
    lx = w - pad
    ly = h - pad - ((arr[-1] - mn) / rng) * (h - 2 * pad)
    dots = ""
    for i, v in enumerate(arr):
        x = pad + i * (w - 2 * pad) / (n - 1)
        y = h - pad - ((v - mn) / rng) * (h - 2 * pad)
        dots += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.2" fill="var(--scope-trace)" opacity=".7"/>'
    return (
        f'<svg class="dt-spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" role="img" aria-label="Monthly commit volume, last 6 months">'
        f'<polygon points="{area}" fill="var(--phos-trail)" stroke="none"/>'
        f'<polyline points="{poly}" fill="none" stroke="var(--scope-trace)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        f'{dots}<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.4" fill="var(--scope-dot)"/></svg>'
    )


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
(function(){
  var btn=document.getElementById("themeToggle"); if(!btn) return;
  btn.addEventListener("click",function(){
    var cur=document.documentElement.dataset.theme==="light"?"light":"dark";
    var next=cur==="light"?"dark":"light";
    document.documentElement.dataset.theme=next;
    try{localStorage.setItem("theme",next);}catch(e){}
    var mc=document.querySelector('meta[name="theme-color"]'); if(mc) mc.setAttribute("content",next==="light"?"#eef3f0":"#070a09");
  });
  var nav=document.getElementById("nav");
  if(nav){var on=function(){nav.classList.toggle("scrolled",window.scrollY>20)};window.addEventListener("scroll",on,{passive:true});on();}
})();
</script>"""


def detail_html(r: dict) -> str:
    slug = slugify(r["owner"], r["name"])
    url = f"{BASE}/p/{slug}/"
    title = f"{r['name']} by {r['owner']} — momentum {r.get('momentum',0)}/100 · StackTracker"
    blurb = r.get("blurb") or f"{r['owner']}/{r['name']} — tracked AI-infra project."
    desc = f"{r['owner']}/{r['name']}: {blurb} {fmt_int(r.get('stars',0))} stars, momentum {r.get('momentum',0)}/100, {r.get('recent4w_commits',0)} commits in the last 30 days. Live GitHub velocity, recomputed daily."
    desc = desc[:300]
    cat = r.get("category", "AI infrastructure")
    delta = r.get("commit_delta", 0)
    if delta > 3:
        dcls, dtxt = "up", f"&#9650; +{delta} vs prior month"
    elif delta < -3:
        dcls, dtxt = "dn", f"&#9660; {delta} vs prior month"
    else:
        dcls, dtxt = "", "&#8594; steady"
    rel_line = (
        f"{_esc(r['last_release'])} &middot; {rel_date(r.get('last_release_at')) or '—'}"
        if r.get("last_release") else "no published release"
    )
    pushed = rel_date(r.get("pushed_at")) or "—"
    homepage = (r.get("homepage") or "").strip()
    home_btn = (
        f'<a class="dt-btn" href="{_esc(homepage)}" target="_blank" rel="noopener">Homepage &#8599;</a>'
        if homepage else ""
    )
    archived = '<span class="arch">archived</span>' if r.get("archived") else ""

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
      <h1>{_esc(r['name'])} <span class="downer">/ {_esc(r['owner'])}</span> {archived}</h1>
      <p class="dblurb">{_esc(blurb)}</p>
    </div>
    <div class="dt-out">
      <a class="dt-btn primary" href="{_esc(r.get('html_url'))}" target="_blank" rel="noopener">View on GitHub &#8599;</a>
      {home_btn}
    </div>
  </div>

  <div class="statgrid">
    {stat(r.get('momentum',0), 'Momentum', ' accent')}
    {stat(fmt_stars(r.get('stars',0)), 'Stars')}
    {stat(fmt_int(r.get('forks',0)), 'Forks')}
    {stat(fmt_int(r.get('open_issues',0)), 'Open issues')}
  </div>

  <section class="dt-panel">
    <h2>Momentum signal</h2>
    <div class="dt-momentum">
      <span class="score">{r.get('momentum',0)}</span>
      <div class="bar"><i style="width:{r.get('momentum',0)}%"></i></div>
    </div>
    <div class="dt-meta" style="margin-top:22px">
      <div><span class="k">Commits · last 30d</span><span class="v">{fmt_int(r.get('recent4w_commits',0))}</span></div>
      <div><span class="k">Commits · prior 30d</span><span class="v">{fmt_int(r.get('prior4w_commits',0))}</span></div>
      <div><span class="k">Month-over-month</span><span class="v {dcls}">{dtxt}</span></div>
    </div>
  </section>

  <section class="dt-panel">
    <h2>Commit volume · last 6 months</h2>
    {sparkline_svg(r.get('monthly_commits') or [])}
  </section>

  <section class="dt-panel">
    <h2>Repository</h2>
    <div class="dt-meta">
      <div><span class="k">Language</span><span class="v">{_esc(r.get('language') or '—')}</span></div>
      <div><span class="k">Category</span><span class="v">{_esc(cat)}</span></div>
      <div><span class="k">Last release</span><span class="v">{rel_line}</span></div>
      <div><span class="k">Last pushed</span><span class="v">{pushed}</span></div>
      <div><span class="k">Stars</span><span class="v">{fmt_int(r.get('stars',0))}</span></div>
      <div><span class="k">Forks</span><span class="v">{fmt_int(r.get('forks',0))}</span></div>
      <div><span class="k">Open issues</span><span class="v">{fmt_int(r.get('open_issues',0))}</span></div>
      <div><span class="k">Archived</span><span class="v">{'yes' if r.get('archived') else 'no'}</span></div>
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
            f.write(detail_html(r))
        slugs.append(slug)

    _write_sitemap(here, slugs)
    _write_llms(here, data, slugs)
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
        "- `/` — the full momentum-ranked index (sortable by momentum, stars, commits/mo; filterable by category).",
        "- `/p/<slug>` — per-repo detail page: full stats, momentum breakdown, 6-month commit sparkline, and outbound links. Slug is the lowercased `owner-name`.",
        "",
        "## Index (current ranking)",
    ]
    for r in repos:
        slug = slugify(r["owner"], r["name"])
        lines.append(f"- [{r['owner']}/{r['name']}]({BASE}/p/{slug}/) — {r.get('category','')}, momentum {r.get('momentum',0)}/100, {fmt_int(r.get('stars',0))}★")
    lines.append("")
    with open(os.path.join(here, "llms.txt"), "w") as f:
        f.write("\n".join(lines))


def main() -> int:
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
