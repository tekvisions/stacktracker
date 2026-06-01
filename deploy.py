#!/usr/bin/env python3
"""Deploy this static directory to Vercel via the REST API.

Used both for manual ships and by the daily GitHub Action. Avoids the Vercel
CLI (which hangs in some headless/CC environments). Uploads each file by SHA,
then creates a production deployment.

Env:
  VERCEL_TOKEN   (required)
  VERCEL_TEAM_ID (default: techtalevisions-projects team)
  VERCEL_PROJECT (default: stacktracker)
"""
import hashlib, json, os, sys, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
TOKEN = os.environ.get("VERCEL_TOKEN", "").strip()
TEAM = os.environ.get("VERCEL_TEAM_ID", "team_L6hpqgg8pEHznOzrnU66JuoW").strip()
PROJECT = os.environ.get("VERCEL_PROJECT", "stacktracker").strip()
SKIP = {".git", ".vercel", "node_modules", "__pycache__"}
SKIP_FILES = {".DS_Store"}
# only ship what the site needs — never the build scripts or workflow
INCLUDE_EXT = {".html", ".css", ".js", ".json", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico", ".txt", ".xml"}


def req(url, data=None, headers=None, method=None):
    r = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main():
    if not TOKEN:
        print("VERCEL_TOKEN not set", file=sys.stderr)
        return 1
    files = []
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in SKIP]
        for f in fn:
            if f in SKIP_FILES:
                continue
            if os.path.splitext(f)[1].lower() not in INCLUDE_EXT:
                continue  # skip build_data.py / deploy.py / repos.json-adjacent tooling
            rel = os.path.relpath(os.path.join(dp, f), ROOT)
            files.append(rel)

    payload = []
    for rel in files:
        body = open(os.path.join(ROOT, rel), "rb").read()
        sha = hashlib.sha1(body).hexdigest()
        st, _ = req(f"https://api.vercel.com/v2/files?teamId={TEAM}", data=body,
                    headers={"Authorization": f"Bearer {TOKEN}",
                             "Content-Type": "application/octet-stream",
                             "x-vercel-digest": sha}, method="POST")
        print(f"  upload {rel}: {st}", file=sys.stderr)
        payload.append({"file": rel, "sha": sha, "size": len(body)})

    dep = {"name": PROJECT, "project": PROJECT, "target": "production", "files": payload,
           "projectSettings": {"framework": None, "buildCommand": None,
                               "installCommand": None, "outputDirectory": None}}
    st, resp = req(f"https://api.vercel.com/v13/deployments?teamId={TEAM}&forceNew=1",
                   data=json.dumps(dep).encode(),
                   headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
                   method="POST")
    d = json.loads(resp)
    if st >= 400:
        print("deploy error:", json.dumps(d, indent=2)[:600], file=sys.stderr)
        return 1
    print(f"deployed: https://{d.get('url')}  state={d.get('readyState')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
