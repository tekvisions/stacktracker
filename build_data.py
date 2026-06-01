#!/usr/bin/env python3
"""StackTracker data builder.

Fetches REAL GitHub signals for each curated AI-infra repo and computes a
momentum score (0-100) from commit velocity + release recency + trend.
No fabricated numbers — every value traces to a GitHub API response.

Auth: reads GITHUB_TOKEN from env (GitHub Actions provides it). Falls back to
`gh auth token` for local runs. Writes data.json next to this script.

The `stars_history` is appended to on every run (the prior data.json is read
back in), so the star sparkline builds a real day-over-day series over time.
"""
import json, os, subprocess, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://api.github.com"


def token() -> str:
    t = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if t:
        return t.strip()
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


TOKEN = token()
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "stacktracker"}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"


def gh(path: str, *, retries: int = 4):
    """GET a GitHub API path. Returns (status, json|None). Handles 202 (stats
    still computing) with backoff, and 404 (no release) without raising."""
    url = API + path
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                if r.status == 202:  # stats being computed server-side
                    time.sleep(2 + attempt * 2)
                    continue
                return r.status, json.loads(r.read() or "null")
        except urllib.error.HTTPError as e:
            if e.code == 202:
                time.sleep(2 + attempt * 2)
                continue
            if e.code == 404:
                return 404, None
            if e.code in (403, 429):  # rate limit — back off once
                time.sleep(5)
                continue
            return e.code, None
        except Exception:
            time.sleep(1)
    return 0, None


def commit_count(full: str, since_iso: str, until_iso: str | None = None) -> int:
    """Reliable commit count in a window via the commits endpoint's Link header
    (per_page=1 → last-page number == commit count). No 202, fast. Caps at 500."""
    q = f"/repos/{full}/commits?per_page=1&since={since_iso}"
    if until_iso:
        q += f"&until={until_iso}"
    url = API + q
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            link = r.headers.get("Link", "") or ""
            body = json.loads(r.read() or "[]")
    except urllib.error.HTTPError as e:
        return 0
    except Exception:
        return 0
    if 'rel="last"' in link:
        import re
        for part in link.split(","):
            if 'rel="last"' in part:
                m = re.search(r"[?&]page=(\d+)", part)
                if m:
                    return min(int(m.group(1)), 3000)
    return len(body) if isinstance(body, list) else 0


def days_since(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    except Exception:
        return None


def momentum(recent4: int, prior4: int, days_release: float | None) -> int:
    """Momentum 0-100 from real commit velocity + release recency + trend.
    recent4 = commits in last 28d, prior4 = commits in the prior 28d."""
    # activity: 400 commits / 28d ≈ very hot
    act = min(recent4 / 400.0, 1.0)
    # release recency: <30d full, decays to 0 by 270d; no release → low floor
    if days_release is None:
        rel = 0.2
    else:
        rel = max(0.0, 1.0 - max(0.0, days_release - 30) / 240.0)
    # trend: ratio of recent vs prior, centered at 0.5 (flat)
    if prior4 > 0:
        tr = min(max((recent4 - prior4) / prior4 * 0.5 + 0.5, 0.0), 1.0)
    else:
        tr = 0.7 if recent4 > 0 else 0.5
    score = round(100 * (0.55 * act + 0.25 * rel + 0.20 * tr))
    return max(0, min(100, score))


def main() -> int:
    cfg = json.load(open(os.path.join(HERE, "repos.json")))
    # read prior data.json to extend the star history series
    prior_stars = {}
    out_path = os.path.join(HERE, "data.json")
    if os.path.exists(out_path):
        try:
            prev = json.load(open(out_path))
            for r in prev.get("repos", []):
                prior_stars[r["repo"]] = r.get("stars_history", [])
        except Exception:
            pass

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    # 6 monthly (30d) windows, oldest→newest. Built from the commits endpoint
    # (reliable, no 202). This is BOTH the momentum velocity and the sparkline,
    # so every repo has a real commit-trend curve on day one.
    def iso(dt):
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    windows = [(iso(now - timedelta(days=30 * (i + 1))), iso(now - timedelta(days=30 * i))) for i in range(6)][::-1]

    items = []
    for entry in cfg["repos"]:
        full = entry.get("repo")
        if not full or "/" not in full:
            print(f"  skip malformed entry: {entry!r}", file=sys.stderr)
            continue
        category = entry.get("category", "Uncategorized")
        blurb = entry.get("blurb", "")
        st, core = gh(f"/repos/{full}")
        if st != 200 or not core:
            print(f"  skip {full} (repo status {st})", file=sys.stderr)
            continue
        _, rel = gh(f"/repos/{full}/releases/latest")  # stable only (avoids prereleases)
        # monthly commit buckets (sparkline) + recent/prior 30d velocity (momentum)
        monthly = [commit_count(full, s, until_iso=u) for (s, u) in windows]
        recent4 = monthly[-1]
        prior4 = monthly[-2]
        rel_tag = rel.get("tag_name") if isinstance(rel, dict) else None
        rel_at = rel.get("published_at") if isinstance(rel, dict) else None
        d_rel = days_since(rel_at)
        score = momentum(recent4, prior4, d_rel)

        stars = int(core.get("stargazers_count", 0))
        hist = list(prior_stars.get(full, []))
        if not hist or hist[-1].get("date") != today:
            hist.append({"date": today, "stars": stars})
        hist = hist[-90:]  # cap 90 days

        items.append({
            "repo": full,
            "name": full.split("/")[-1],
            "owner": full.split("/")[0],
            "category": category,
            "blurb": blurb,
            "stars": stars,
            "forks": int(core.get("forks_count", 0)),
            "open_issues": int(core.get("open_issues_count", 0)),
            "language": core.get("language"),
            "archived": bool(core.get("archived")),
            "homepage": (core.get("homepage") or "").strip() or None,
            "html_url": core.get("html_url"),
            "pushed_at": core.get("pushed_at"),
            "last_release": rel_tag,
            "last_release_at": rel_at,
            "monthly_commits": monthly,         # 6 × 30d buckets, real
            "recent4w_commits": recent4,
            "prior4w_commits": prior4,
            "commit_delta": recent4 - prior4,
            "momentum": score,
            "stars_history": hist,
        })
        print(f"  {full}: {stars}★ momentum={score} recent4w={recent4}", file=sys.stderr)
        time.sleep(0.2)  # be polite to the API

    items.sort(key=lambda x: x["momentum"], reverse=True)
    for i, it in enumerate(items):
        it["rank"] = i + 1
    trending = sorted([x for x in items if x["commit_delta"] > 0],
                      key=lambda x: x["commit_delta"], reverse=True)[:3]

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_date": today,
        "repo_count": len(items),
        "categories": cfg["categories"],
        "trending": [t["repo"] for t in trending],
        "repos": items,
    }
    json.dump(data, open(out_path, "w"), indent=2)
    series_len = len(items[0]["monthly_commits"]) if items else 0
    print(f"wrote {out_path}: {len(items)} repos, {series_len}-month series", file=sys.stderr)
    # resilience guard: a partial/rate-limited run (most repos missing) must FAIL so
    # the cron skips commit+deploy and the last-good page stays live, not a half-empty one.
    expected = len(cfg.get("repos", []))
    floor = max(5, int(expected * 0.6))
    if len(items) < floor:
        print(f"GUARD: only {len(items)}/{expected} repos fetched (< {floor}); refusing to publish.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
