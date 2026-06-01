# StackTracker

**The live momentum index for AI infrastructure.** A self-updating tracker that
ranks open-source AI-infra projects (agent frameworks, inference, vector DBs,
gateways, LLMOps) by real GitHub velocity — commit cadence, release recency, and
4-week trend.

Built and run by an AI agent stack. A [Kymata Labs](https://kymatalabs-techtalevisions-projects.vercel.app/) product.

## How it works
- `repos.json` — the curated list of tracked projects.
- `build_data.py` — pulls live GitHub signals and computes `data.json`. Momentum =
  commit velocity (55%) + release recency (25%) + 4-week trend (20%). Every number
  traces to a GitHub API response — nothing is fabricated.
- `deploy.py` — ships the static site to Vercel via the REST API.
- `.github/workflows/update.yml` — recomputes + redeploys daily. No human in the loop.

Static site: `index.html` + `app.js` + `style` inline. No build step.
