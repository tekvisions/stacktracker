/* StackTracker — World-Class Design System Implementation
   Vanilla JS, no deps. Features: category filters, multi-key sort, instant search,
   animated stat counters, scroll-reveal, sparklines, command palette, compare mode */

(function() {
  "use strict";

  const W = window;
  const D = document;
  const REDUCED = W.matchMedia && W.matchMedia("(prefers-reduced-motion:reduce)").matches;

  // State
  let ALL_REPOS = [];
  let curFilter = "";
  let sortKey = "momentum";
  let sortDir = "desc";
  let query = "";

  // Nav scroll behavior
  const nav = D.getElementById("nav");
  if (nav) {
    const onScroll = function() { nav.classList.toggle("scrolled", W.scrollY > 20); };
    W.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  // Utility functions
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function(c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[c];
    });
  }

  function slugify(owner, name) {
    return (owner + "-" + name).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  }

  function timeAgo(iso) {
    if (!iso) return "—";
    const d = (Date.now() - Date.parse(iso)) / 86400000;
    if (d < 1) return "today";
    if (d < 2) return "yesterday";
    if (d < 30) return Math.round(d) + "d ago";
    if (d < 365) return Math.round(d / 30) + "mo ago";
    return Math.round(d / 365) + "y ago";
  }

  function kFormat(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + "m";
    if (n >= 1000) return (n / 1000).toFixed(1) + "k";
    return String(n);
  }

  function sparkline(arr, w = 60, h = 24) {
    if (!arr || arr.length < 2) return `<svg width="${w}" height="${h}"><line x1="0" y1="${h/2}" x2="${w}" y2="${h/2}" stroke="var(--line)" stroke-width="1"/></svg>`;

    const min = Math.min(...arr);
    const max = Math.max(...arr);
    const range = max - min;

    if (range === 0) return `<svg width="${w}" height="${h}"><line x1="0" y1="${h/2}" x2="${w}" y2="${h/2}" stroke="var(--accent)" stroke-width="1.5"/></svg>`;

    let path = "";
    for (let i = 0; i < arr.length; i++) {
      const x = (i / (arr.length - 1)) * w;
      const y = h - ((arr[i] - min) / range) * h;
      path += (i === 0 ? `M ${x},${y}` : ` L ${x},${y}`);
    }

    return `<svg width="${w}" height="${h}" class="board-sparkline"><path d="${path}" fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-linejoin="round"/></svg>`;
  }

  function animateCount(el, target) {
    if (REDUCED) { el.textContent = target; return; }
    let current = 0;
    const increment = target / 60;
    const timer = setInterval(() => {
      current += increment;
      if (current >= target) {
        el.textContent = target;
        clearInterval(timer);
      } else {
        el.textContent = Math.floor(current);
      }
    }, 16);
  }

  // Sorting functions
  const SORT_VAL = {
    name: r => r.name.toLowerCase(),
    momentum: r => r.momentum || 0,
    stars: r => r.stars || 0,
    recent4w_commits: r => r.recent4w_commits || 0,
    commit_delta: r => r.commit_delta || 0,
    rank: r => r.rank || 999
  };

  const SORT_LABEL = {
    name: "name",
    momentum: "momentum",
    stars: "stars",
    recent4w_commits: "commits",
    commit_delta: "trend",
    rank: "rank"
  };

  // Filtering
  function matchesFilter(r) {
    return !curFilter || r.category === curFilter;
  }

  function matchesQuery(r, q) {
    if (!q) return true;
    q = q.toLowerCase();
    return (r.name && r.name.toLowerCase().includes(q)) ||
           (r.owner && r.owner.toLowerCase().includes(q)) ||
           (r.category && r.category.toLowerCase().includes(q));
  }

  function visibleRepos() {
    return ALL_REPOS.filter(r => matchesFilter(r) && matchesQuery(r, query));
  }

  // Rendering
  function renderTable() {
    const get = SORT_VAL[sortKey] || SORT_VAL.momentum;
    const rows = visibleRepos().sort((a, b) => {
      const aVal = get(a);
      const bVal = get(b);
      const d = typeof aVal === "string" ? aVal.localeCompare(bVal) : (aVal - bVal);
      return sortDir === "asc" ? d : -d;
    });

    const tbody = D.getElementById("board-tbody");
    const cards = D.getElementById("board-cards");

    if (!tbody && !cards) return;

    // Update sort indicators
    D.querySelectorAll(".board-th.sortable").forEach(btn => {
      const k = btn.getAttribute("data-sort");
      if (k === sortKey) {
        btn.classList.add(`sort-${sortDir}`);
        btn.classList.remove(`sort-${sortDir === "asc" ? "desc" : "asc"}`);
      } else {
        btn.classList.remove("sort-asc", "sort-desc");
      }
    });

    // Handle empty state
    if (!rows.length) {
      const emptyMsg = `No projects match ${query ? `"${query}"` : "this filter"}`;
      if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 2rem; color: var(--ink-muted);">${emptyMsg}</td></tr>`;
      if (cards) cards.innerHTML = `<div style="text-align: center; padding: 2rem; color: var(--ink-muted);">${emptyMsg}</div>`;
      return;
    }

    // Render table rows
    if (tbody) {
      tbody.innerHTML = rows.map((r, i) => {
        const rank = i + 1;
        const commits = r.recent4w_commits || 0;
        const trend = r.commit_delta || 0;
        const trendClass = trend > 0 ? "var(--positive)" : trend < 0 ? "var(--negative)" : "var(--ink-muted)";
        const sparklineHtml = r.monthly_commits ? sparkline(r.monthly_commits) : "";

        return `<tr class="board-row">
          <td class="board-td board-rank">${rank}</td>
          <td class="board-td primary">
            <div class="board-name">${esc(r.name)}</div>
            <div class="board-owner">/${esc(r.owner)}</div>
          </td>
          <td class="board-td">
            <div class="board-momentum">${r.momentum || "—"}</div>
          </td>
          <td class="board-td">${commits}</td>
          <td class="board-td">${kFormat(r.stars || 0)}</td>
          <td class="board-td" style="color: ${trendClass}">${trend > 0 ? "+" : ""}${trend}</td>
          <td class="board-td">${sparklineHtml}</td>
        </tr>`;
      }).join("");
    }

    // Render mobile cards
    if (cards) {
      cards.innerHTML = rows.map((r, i) => {
        const rank = i + 1;
        const commits = r.recent4w_commits || 0;
        const momentum = r.momentum || 0;

        return `<div class="board-card">
          <div class="card-header">
            <div class="card-rank">#${rank}</div>
          </div>
          <div class="card-name">${esc(r.name)}</div>
          <div class="card-owner">/${esc(r.owner)}</div>
          <div class="card-stats">
            <div class="card-stat">
              <div class="card-stat-value">${momentum}</div>
              <div class="card-stat-label">Momentum</div>
            </div>
            <div class="card-stat">
              <div class="card-stat-value">${commits}</div>
              <div class="card-stat-label">Commits</div>
            </div>
          </div>
        </div>`;
      }).join("");
    }
  }

  // Event handlers
  function applySort() {
    renderTable();
  }

  function renderMeta(data) {
    const repoCount = D.getElementById("repo-count");
    const lastUpdated = D.getElementById("last-updated");
    const topMomentum = D.getElementById("top-momentum");
    const footGen = D.getElementById("footgen");

    if (repoCount) {
      repoCount.textContent = data.repo_count || ALL_REPOS.length;
      if (!REDUCED) animateCount(repoCount, data.repo_count || ALL_REPOS.length);
    }

    if (lastUpdated && data.generated_at) {
      lastUpdated.textContent = timeAgo(data.generated_at);
    }

    if (topMomentum && ALL_REPOS.length) {
      const top = Math.max(...ALL_REPOS.map(r => r.momentum || 0));
      topMomentum.textContent = top;
      if (!REDUCED) animateCount(topMomentum, top);
    }

    if (footGen && data.generated_date) {
      footGen.textContent = `Data regenerated ${timeAgo(data.generated_at)}`;
    }
  }

  function renderFilters(data) {
    const filters = D.getElementById("filters");
    if (!filters) return;

    const categories = ["", ...(data.categories || [])];
    const counts = {};

    ALL_REPOS.forEach(r => {
      counts[""] = (counts[""] || 0) + 1;
      if (r.category) counts[r.category] = (counts[r.category] || 0) + 1;
    });

    filters.innerHTML = categories.map((cat, i) => {
      const label = cat || "All";
      const count = counts[cat] || 0;
      const active = (i === 0 && !curFilter) || (cat === curFilter);

      return `<div class="chip ${active ? "active" : ""}" data-category="${esc(cat)}" aria-pressed="${active}">
        ${esc(label)} <span style="opacity: 0.7">(${count})</span>
      </div>`;
    }).join("");

    // Add click handlers
    D.querySelectorAll(".chip").forEach(chip => {
      chip.addEventListener("click", function() {
        D.querySelectorAll(".chip").forEach(c => {
          c.classList.remove("active");
          c.setAttribute("aria-pressed", "false");
        });

        this.classList.add("active");
        this.setAttribute("aria-pressed", "true");
        curFilter = this.getAttribute("data-category");
        applySort();
      });
    });
  }

  function renderMovers(data) {
    const moversSection = D.getElementById("movers-section");
    const moversList = D.getElementById("movers");

    if (!moversSection || !moversList || !data.movers?.length) return;

    moversList.innerHTML = data.movers.map(m => {
      return `<div class="mover-item">
        <div class="mover-name">${esc(m.name)}</div>
        <div class="mover-delta">+${m.rank_delta || 0}</div>
      </div>`;
    }).join("");

    moversSection.hidden = false;
  }

  // Search functionality
  function setupSearch() {
    const searchInput = D.getElementById("search");
    const searchClear = D.getElementById("searchClear");

    if (!searchInput) return;

    const onInput = function() {
      query = searchInput.value.toLowerCase();
      if (searchClear) searchClear.hidden = !query;
      applySort();
    };

    searchInput.addEventListener("input", onInput);

    // Keyboard shortcuts
    D.addEventListener("keydown", function(e) {
      if (e.key === "/" && !e.ctrlKey && !e.metaKey && D.activeElement !== searchInput) {
        e.preventDefault();
        searchInput.focus();
      }
      if (e.key === "Escape" && D.activeElement === searchInput) {
        searchInput.value = "";
        query = "";
        if (searchClear) searchClear.hidden = true;
        applySort();
      }
    });

    if (searchClear) {
      searchClear.addEventListener("click", function() {
        searchInput.value = "";
        query = "";
        searchClear.hidden = true;
        applySort();
        searchInput.focus();
      });
    }
  }

  // Column sorting
  function setupSorting() {
    D.querySelectorAll(".board-th.sortable").forEach(btn => {
      btn.addEventListener("click", function() {
        const k = btn.getAttribute("data-sort");
        if (k === sortKey) {
          sortDir = sortDir === "asc" ? "desc" : "asc";
        } else {
          sortKey = k;
          sortDir = (k === "name") ? "asc" : "desc";
        }
        applySort();
      });
    });
  }

  // Command palette (basic implementation)
  function setupCommandPalette() {
    const cmdBtn = D.getElementById("cmdPalette");
    if (!cmdBtn) return;

    cmdBtn.addEventListener("click", function() {
      // For now, just focus search - can be enhanced later
      const searchInput = D.getElementById("search");
      if (searchInput) searchInput.focus();
    });

    // Keyboard shortcut
    D.addEventListener("keydown", function(e) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        const searchInput = D.getElementById("search");
        if (searchInput) searchInput.focus();
      }
    });
  }

  // Scroll reveal
  function setupScrollReveal() {
    if (REDUCED) return;

    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add("in");
        }
      });
    }, { threshold: 0.1 });

    D.querySelectorAll("[data-reveal]").forEach(el => observer.observe(el));
  }

  // Main render function
  function render(data) {
    try {
      ALL_REPOS = data.repos || [];

      renderMeta(data);
      renderFilters(data);
      renderMovers(data);
      renderTable();

      // Setup interactivity
      setupSearch();
      setupSorting();
      setupCommandPalette();
      setupScrollReveal();

    } catch (e) {
      console.error("Render error:", e);
      const tbody = D.getElementById("board-tbody");
      const cards = D.getElementById("board-cards");
      const errorMsg = `<div style="text-align: center; padding: 2rem; color: var(--negative);">Error loading data</div>`;

      if (tbody) tbody.innerHTML = `<tr><td colspan="7">${errorMsg}</td></tr>`;
      if (cards) cards.innerHTML = errorMsg;
    }
  }

  // Load data
  fetch("data.json", { cache: "no-store" })
    .then(r => r.json())
    .then(render)
    .catch(e => {
      console.error("Data fetch error:", e);
      const tbody = D.getElementById("board-tbody");
      const cards = D.getElementById("board-cards");
      const errorMsg = `<div style="text-align: center; padding: 2rem; color: var(--negative);">Failed to load data</div>`;

      if (tbody) tbody.innerHTML = `<tr><td colspan="7">${errorMsg}</td></tr>`;
      if (cards) cards.innerHTML = errorMsg;
    });

})();