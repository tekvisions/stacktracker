/* StackTracker — render the live index from data.json.
   Vanilla JS, no deps. Drives: category filter, multi-key sort, instant search,
   animated stat counters, scroll-reveal, and sparkline tooltips. */
(function(){
  "use strict";
  var W = window, D = document;
  var REDUCED = W.matchMedia && W.matchMedia("(prefers-reduced-motion:reduce)").matches;

  var nav = D.getElementById("nav");
  if(nav){ var onScroll=function(){nav.classList.toggle("scrolled",W.scrollY>20)}; W.addEventListener("scroll",onScroll,{passive:true}); onScroll(); }

  function fmtStars(n){
    if(n>=1000) return (n/1000).toFixed(n>=10000?0:1).replace(/\.0$/,"")+"k";
    return String(n);
  }
  function relDate(iso){
    if(!iso) return null;
    var d=(Date.now()-new Date(iso).getTime())/86400000;
    if(d<1) return "today";
    if(d<2) return "yesterday";
    if(d<30) return Math.round(d)+"d ago";
    if(d<365) return Math.round(d/30)+"mo ago";
    return Math.round(d/365)+"y ago";
  }
  function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c];}); }
  // slug: lowercase, url-safe, from "owner-name" — MUST match build_data.py's slugify()
  function slugify(owner,name){ return (owner+"-"+name).toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,""); }

  // SVG sparkline from a numeric array, with per-point hover targets (tooltip via app-level handler).
  function sparkline(arr, w, h){
    if(!arr || arr.length < 2) return '<div class="spark"><span class="ph">— warming up —</span></div>';
    var max=Math.max.apply(null,arr), min=Math.min.apply(null,arr);
    var range=(max-min)||1, n=arr.length, pad=2;
    var coords=arr.map(function(v,i){
      var x=pad + i*(w-2*pad)/(n-1);
      var y=h-pad - ((v-min)/range)*(h-2*pad);
      return [x,y];
    });
    var pts=coords.map(function(c){return c[0].toFixed(1)+","+c[1].toFixed(1);}).join(" ");
    var last=coords[n-1];
    // invisible-ish hit dots carry the data for the shared tooltip (no per-svg listeners)
    var hits="";
    for(var i=0;i<n;i++){
      var monthsAgo=n-1-i;
      var lbl = monthsAgo===0 ? "this month" : (monthsAgo===1 ? "1 mo ago" : monthsAgo+" mo ago");
      hits+='<circle class="spk-hit" cx="'+coords[i][0].toFixed(1)+'" cy="'+coords[i][1].toFixed(1)+'" r="6" data-v="'+arr[i]+'" data-l="'+lbl+'"></circle>';
    }
    return '<svg class="spark" viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none" role="img" aria-label="Monthly commit volume, last 6 months">'
      + '<polyline points="'+pts+'" fill="none" stroke="var(--scope-trace)" stroke-width="1.3" stroke-linejoin="round" stroke-linecap="round" opacity="0.92"/>'
      + '<circle cx="'+last[0].toFixed(1)+'" cy="'+last[1].toFixed(1)+'" r="2" fill="var(--scope-dot)"/>'
      + hits + '</svg>';
  }

  function trendArrow(delta){
    if(delta > 3) return '<span class="trend up">▲ '+delta+'/mo</span>';
    if(delta < -3) return '<span class="trend dn">▼ '+Math.abs(delta)+'/mo</span>';
    return '<span class="trend flat">→ steady</span>';
  }
  // small inline trend cell for the dedicated "4-wk trend" column
  function trendCell(delta){
    if(delta > 3) return '<span class="tcell up">▲ +'+delta+'</span>';
    if(delta < -3) return '<span class="tcell dn">▼ '+delta+'</span>';
    return '<span class="tcell flat">→ 0</span>';
  }

  // ── view state ──
  var ALL_REPOS=[];
  var curFilter="All";
  var query="";
  var sortKey="momentum", sortDir="desc";
  var SORT_VAL={
    momentum:function(r){return r.momentum||0;},
    stars:function(r){return r.stars||0;},
    commits:function(r){return r.recent4w_commits||0;},
    trend:function(r){return r.commit_delta||0;},
    name:function(r){return (r.name||"").toLowerCase();}
  };
  var SORT_LABEL={momentum:"momentum",stars:"stars",commits:"commits/mo",trend:"4-week trend",name:"name"};

  function matchesQuery(r,q){
    if(!q) return true;
    return (r.name+" "+r.owner+" "+r.category+" "+(r.language||"")+" "+(r.blurb||"")).toLowerCase().indexOf(q)!==-1;
  }
  function matchesFilter(r){ return curFilter==="All" || r.category===curFilter; }

  /* position movement vs the prior daily run: ▲N climbed, ▼N slipped, → held.
     rank_delta>0 means a smaller (better) rank number — i.e. climbed the board.
     null == no prior history yet (shows nothing; fills in as the board runs daily). */
  function moveBadge(r){
    var d=r.rank_delta;
    if(d==null) return '';
    if(d>0) return '<span class="mv up" title="Climbed '+d+' since the prior run">▲'+d+'</span>';
    if(d<0) return '<span class="mv dn" title="Slipped '+Math.abs(d)+' since the prior run">▼'+Math.abs(d)+'</span>';
    return '<span class="mv flat" title="Held position">→</span>';
  }

  function rowHTML(r){
    var capped = r.recent4w_commits>=3000 ? "3000+" : r.recent4w_commits;
    var rel = r.last_release ? '<div class="rel">'+esc(r.last_release)+' · '+relDate(r.last_release_at)+'</div>' : '';
    var arch = r.archived ? '<span class="arch">archived</span>' : '';
    var slug = slugify(r.owner, r.name);
    return '<a class="row" data-cat="'+esc(r.category)+'" href="/p/'+esc(slug)+'/">'
      +'<span class="rank'+(r.rank<=3?' top':'')+'">'+r.rank+moveBadge(r)+'</span>'
      +'<div class="name"><h3>'+esc(r.name)+' <span class="owner">/ '+esc(r.owner)+'</span> '+arch+'</h3>'
        +'<p>'+esc(r.blurb)+'</p>'+rel+'</div>'
      +'<div class="mom"><div class="bar"><i style="width:'+r.momentum+'%"></i></div>'
        +'<div class="val"><b>'+r.momentum+'</b><span>'+capped+' commits/mo</span></div></div>'
      +'<div class="spk">'+sparkline(r.monthly_commits, 132, 34)+'</div>'
      +'<div class="trendcol">'+trendCell(r.commit_delta)+'</div>'
      +'<div class="stars"><b>'+fmtStars(r.stars)+'</b>'+trendArrow(r.commit_delta)+'</div>'
      +'<span class="go" aria-hidden="true">↗</span></a>';
  }

  function visibleRepos(){
    return ALL_REPOS.filter(function(r){ return matchesFilter(r) && matchesQuery(r,query); });
  }

  function applySort(){
    var get=SORT_VAL[sortKey]||SORT_VAL.momentum;
    var rows=visibleRepos().sort(function(a,b){
      var av=get(a), bv=get(b), d;
      if(typeof av==="string"){ d=av<bv?-1:(av>bv?1:0); }
      else { d=av-bv; }
      if(d===0) d=(a.rank||0)-(b.rank||0); // stable tiebreak by canonical rank
      return sortDir==="asc"? d : -d;
    });

    var host=D.getElementById("rows");
    host.innerHTML = rows.map(rowHTML).join("");
    host.setAttribute("aria-busy","false");

    // header indicators + aria-sort
    D.querySelectorAll(".colhead .sortable").forEach(function(btn){
      var k=btn.getAttribute("data-sort"), ind=btn.querySelector(".ind");
      if(k===sortKey){ btn.setAttribute("aria-sort", sortDir==="asc"?"ascending":"descending"); if(ind) ind.textContent=sortDir==="asc"?"▲":"▼"; }
      else { btn.setAttribute("aria-sort","none"); if(ind) ind.textContent="▾"; }
    });

    // empty state + live result note
    var none=D.getElementById("noresults");
    var note=D.getElementById("sortnote");
    if(rows.length===0){
      if(none){ none.hidden=false; var nq=D.getElementById("nr-q"); if(nq) nq.textContent = query ? '"'+query+'"' : "this filter"; }
      if(note) note.textContent="0 of "+ALL_REPOS.length+" projects";
    } else {
      if(none) none.hidden=true;
      var scope = (curFilter==="All" && !query) ? ("all "+ALL_REPOS.length) : (rows.length+" of "+ALL_REPOS.length);
      if(note) note.textContent="Showing "+scope+" · sorted by "+(SORT_LABEL[sortKey]||sortKey)+" "+(sortDir==="asc"?"↑":"↓");
    }
  }

  // count-up animation for the hero stat numbers (respects reduced-motion)
  function animateCount(el, target){
    var isK = /k$/.test(String(target));
    var num = parseFloat(String(target).replace(/[^0-9.]/g,""));
    if(REDUCED || !isFinite(num) || num===0){ el.textContent=target; return; }
    var start=performance.now(), dur=900;
    function step(now){
      var t=Math.min((now-start)/dur,1);
      var e=1-Math.pow(1-t,3); // easeOutCubic
      var cur=num*e;
      el.textContent = isK ? (cur>=10? Math.round(cur)+"k" : cur.toFixed(1).replace(/\.0$/,"")+"k") : String(Math.round(cur));
      if(t<1) requestAnimationFrame(step); else el.textContent=target;
    }
    requestAnimationFrame(step);
  }

  // shared sparkline tooltip — one floating node, delegated over the rows container
  function initSparkTooltip(){
    var host=D.getElementById("rows"); if(!host) return;
    var tip=D.createElement("div"); tip.className="spk-tip"; tip.setAttribute("role","status"); tip.hidden=true;
    D.body.appendChild(tip);
    function show(target){
      var v=target.getAttribute("data-v"), l=target.getAttribute("data-l");
      tip.innerHTML='<b>'+esc(v)+'</b> commits <span>· '+esc(l)+'</span>';
      tip.hidden=false;
      var rb=target.getBoundingClientRect();
      tip.style.left=(rb.left+rb.width/2)+"px";
      tip.style.top=(rb.top-8)+"px";
    }
    host.addEventListener("mouseover",function(e){ var t=e.target.closest&&e.target.closest(".spk-hit"); if(t) show(t); });
    host.addEventListener("mouseout",function(e){ if(e.target.closest&&e.target.closest(".spk-hit")) tip.hidden=true; });
    W.addEventListener("scroll",function(){ tip.hidden=true; },{passive:true});
  }

  function render(data){
    var repos=data.repos||[];
    ALL_REPOS=repos;
    var byKey={}; repos.forEach(function(r){byKey[r.repo]=r;});

    // meta (numbers animate from 0 on first paint)
    var totalStars=repos.reduce(function(a,r){return a+(r.stars||0);},0);
    var topMom=repos.length?Math.max.apply(null,repos.map(function(r){return r.momentum||0;})):0;
    var updated=relDate(data.generated_at)||data.generated_date;
    D.getElementById("metarow").innerHTML =
      meta(data.repo_count, "Projects tracked", true) +
      meta(fmtStars(totalStars), "Combined stars", true) +
      meta(topMom, "Top momentum", true) +
      meta(updated, "Last updated", false);
    D.getElementById("liveline").textContent = "Live · last recomputed "+updated;
    var fg=D.getElementById("footgen"); if(fg) fg.textContent="Data regenerated "+updated;
    // fire the counters
    D.querySelectorAll("#metarow .m b[data-count]").forEach(function(el){ animateCount(el, el.getAttribute("data-count")); });

    // trending
    var tr=(data.trending||[]).map(function(k){return byKey[k];}).filter(Boolean);
    D.getElementById("trending").innerHTML = tr.length ? tr.map(function(r){
      return '<a class="trend-card" href="/p/'+esc(slugify(r.owner,r.name))+'/">'
        +'<div class="tn">'+esc(r.name)+'</div>'
        +'<div class="delta">▲ +'+r.commit_delta+' commits vs prior month</div>'
        +'<div class="tcat">'+esc(r.category)+'</div></a>';
    }).join("") : '<div class="sortnote">No upward movers this cycle.</div>';

    // movers strip — biggest climbers since the prior run (rank_delta), or top
    // commit-surge repos on day one before position history exists.
    renderMovers(data.movers||[]);

    // filters (with live per-category counts)
    var counts={}; repos.forEach(function(r){counts[r.category]=(counts[r.category]||0)+1;});
    var cats=["All"].concat(data.categories||[]);
    D.getElementById("filters").innerHTML = cats.map(function(c,i){
      var n = c==="All" ? repos.length : (counts[c]||0);
      return '<button class="chip'+(i===0?' active':'')+'" data-filter="'+esc(c)+'" aria-pressed="'+(i===0)+'">'
        +esc(c)+' <span class="cn">'+n+'</span></button>';
    }).join("");

    // rows (filtered + sorted) — default momentum desc
    applySort();
    initSparkTooltip();

    // ItemList JSON-LD for home (top ~50 by rank) — SEO/AEO/GEO
    try{
      var list=repos.slice(0,50).map(function(r,i){
        return {"@type":"ListItem","position":i+1,"url":"https://stacktracker.kymatalabs.com/p/"+slugify(r.owner,r.name)+"/","name":r.owner+"/"+r.name};
      });
      var ld={"@context":"https://schema.org","@type":"ItemList","name":"StackTracker — AI-infra momentum index","numberOfItems":list.length,"itemListOrder":"https://schema.org/ItemListOrderDescending","itemListElement":list};
      var el=D.getElementById("ld-itemlist");
      if(!el){ el=D.createElement("script"); el.type="application/ld+json"; el.id="ld-itemlist"; D.head.appendChild(el); }
      el.textContent=JSON.stringify(ld);
    }catch(e){}

    // filter behavior — re-render so sort + count stay correct
    var chips=D.querySelectorAll(".chip");
    chips.forEach(function(chip){
      chip.addEventListener("click", function(){
        chips.forEach(function(c){var on=c===chip;c.classList.toggle("active",on);c.setAttribute("aria-pressed",on);});
        curFilter=chip.getAttribute("data-filter");
        applySort();
      });
    });

    // sort behavior — click toggles asc/desc; native <button> = keyboard accessible
    D.querySelectorAll(".colhead .sortable").forEach(function(btn){
      btn.addEventListener("click", function(){
        var k=btn.getAttribute("data-sort");
        if(k===sortKey){ sortDir = sortDir==="asc"?"desc":"asc"; }
        else { sortKey=k; sortDir = (k==="name") ? "asc" : "desc"; } // names default A→Z, metrics high→low
        applySort();
      });
    });

    // instant search
    var box=D.getElementById("search");
    var clr=D.getElementById("searchClear");
    if(box){
      var onInput=function(){
        query=box.value.trim().toLowerCase();
        if(clr) clr.hidden = !box.value;
        applySort();
      };
      box.addEventListener("input", onInput);
      // "/" focuses search; Esc clears
      D.addEventListener("keydown", function(e){
        if(e.key==="/" && D.activeElement!==box && !/^(INPUT|TEXTAREA)$/.test((D.activeElement||{}).tagName||"")){ e.preventDefault(); box.focus(); }
        else if(e.key==="Escape" && D.activeElement===box && box.value){ box.value=""; onInput(); }
      });
    }
    if(clr){ clr.addEventListener("click", function(){ if(box){ box.value=""; query=""; clr.hidden=true; applySort(); box.focus(); } }); }

    // reset-all from the empty state
    var reset=D.getElementById("nr-reset");
    if(reset){ reset.addEventListener("click", function(){
      curFilter="All"; query=""; if(box) box.value=""; if(clr) clr.hidden=true;
      chips.forEach(function(c){var on=c.getAttribute("data-filter")==="All";c.classList.toggle("active",on);c.setAttribute("aria-pressed",on);});
      applySort();
    }); }

    // scroll-reveal for the major sections (skipped under reduced-motion)
    initReveal();
  }

  /* movers strip: horizontally-scrollable chips linking to detail pages. Each shows
     the position climb (▲N) when tracked, else the commit surge (+N commits/mo). */
  function renderMovers(movers){
    var el=D.getElementById("movers"); if(!el) return;
    if(!movers.length){ el.hidden=true; return; }
    var chips=movers.map(function(m,i){
      var climbed=(typeof m.rank_delta==="number" && m.rank_delta>0);
      var tag=climbed
        ? '<span class="mv up">▲'+m.rank_delta+'</span>'
        : '<span class="mv up">+'+(m.commit_delta||0)+'</span>';
      var sub=climbed?("now #"+m.rank):((m.commit_delta||0)+" commits/mo");
      return '<a class="mover" href="/p/'+esc(slugify(m.owner,m.name))+'/" style="--d:'+(i*50)+'ms">'
        +tag+'<span class="mvn">'+esc(m.name)+'</span><span class="mvs">'+esc(sub)+'</span></a>';
    }).join("");
    el.innerHTML='<span class="movers-l">Movers</span><div class="movers-track">'+chips+'</div>';
    el.hidden=false;
  }

  function initReveal(){
    if(REDUCED || !("IntersectionObserver" in W)) return;
    var els=D.querySelectorAll("[data-reveal]");
    var io=new IntersectionObserver(function(entries){
      entries.forEach(function(en){ if(en.isIntersecting){ en.target.classList.add("in"); io.unobserve(en.target); } });
    },{threshold:0.12, rootMargin:"0px 0px -8% 0px"});
    els.forEach(function(el){ io.observe(el); });
  }

  function meta(v,l,count){
    var b = count ? '<b data-count="'+esc(v)+'">0</b>' : '<b>'+esc(v)+'</b>';
    return '<div class="m">'+b+'<span>'+esc(l)+'</span></div>';
  }

  fetch("data.json", {cache:"no-store"}).then(function(r){return r.json();}).then(render).catch(function(e){
    var host=D.getElementById("rows");
    host.setAttribute("aria-busy","false");
    host.innerHTML='<div class="loading">Could not load the index. '+esc(e.message||e)+'</div>';
  });
})();
