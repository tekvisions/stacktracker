/* StackTracker — render the live index from data.json */
(function(){
  "use strict";
  var W = window;
  var nav = document.getElementById("nav");
  if(nav){ var on=function(){nav.classList.toggle("scrolled",W.scrollY>20)}; W.addEventListener("scroll",on,{passive:true}); on(); }

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

  // SVG sparkline from a numeric array
  function sparkline(arr, w, h){
    if(!arr || arr.length < 2) return '<div class="spark"><span class="ph">— sparkline warming up —</span></div>';
    var max=Math.max.apply(null,arr), min=Math.min.apply(null,arr);
    var range=(max-min)||1, n=arr.length, pad=2;
    var pts=arr.map(function(v,i){
      var x=pad + i*(w-2*pad)/(n-1);
      var y=h-pad - ((v-min)/range)*(h-2*pad);
      return x.toFixed(1)+","+y.toFixed(1);
    }).join(" ");
    var lastX=(w-pad).toFixed(1), lastY=(h-pad-((arr[n-1]-min)/range)*(h-2*pad)).toFixed(1);
    return '<svg class="spark" viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none" aria-hidden="true">'
      + '<polyline points="'+pts+'" fill="none" stroke="#3dffa6" stroke-width="1.3" stroke-linejoin="round" stroke-linecap="round" opacity="0.92"/>'
      + '<circle cx="'+lastX+'" cy="'+lastY+'" r="2" fill="#9affd0"/></svg>';
  }

  function trendArrow(delta){
    if(delta > 3) return '<span class="trend up">▲ '+delta+'/mo</span>';
    if(delta < -3) return '<span class="trend dn">▼ '+Math.abs(delta)+'/mo</span>';
    return '<span class="trend flat">→ steady</span>';
  }

  // ── sort state (default: rank/momentum desc) ──
  var ALL_REPOS=[];
  var curFilter="All";
  var sortKey="momentum", sortDir="desc";
  var SORT_VAL={
    momentum:function(r){return r.momentum||0;},
    stars:function(r){return r.stars||0;},
    commits:function(r){return r.recent4w_commits||0;}
  };
  var SORT_LABEL={momentum:"momentum",stars:"stars",commits:"commits/mo"};

  function rowHTML(r){
    var capped = r.recent4w_commits>=3000 ? "3000+" : r.recent4w_commits;
    var rel = r.last_release ? '<div class="rel">'+esc(r.last_release)+' · '+relDate(r.last_release_at)+'</div>' : '';
    var arch = r.archived ? '<span class="arch">archived</span>' : '';
    var slug = slugify(r.owner, r.name);
    var hidden = (curFilter!=="All" && r.category!==curFilter) ? ' hide' : '';
    return '<a class="row'+hidden+'" data-cat="'+esc(r.category)+'" href="/p/'+esc(slug)+'/">'
      +'<span class="rank'+(r.rank<=3?' top':'')+'">'+r.rank+'</span>'
      +'<div class="name"><h3>'+esc(r.name)+' <span class="owner">/ '+esc(r.owner)+'</span> '+arch+'</h3>'
        +'<p>'+esc(r.blurb)+'</p>'+rel+'</div>'
      +'<div class="mom"><div class="bar"><i style="width:'+r.momentum+'%"></i></div>'
        +'<div class="val"><b>'+r.momentum+'</b><span>'+capped+' commits/mo</span></div></div>'
      +'<div>'+sparkline(r.monthly_commits, 132, 34)+'</div>'
      +'<div class="stars"><b>'+fmtStars(r.stars)+'</b>'+trendArrow(r.commit_delta)+'</div>'
      +'<span class="go">↗</span></a>';
  }

  function applySort(){
    var get=SORT_VAL[sortKey]||SORT_VAL.momentum;
    var sorted=ALL_REPOS.slice().sort(function(a,b){
      var av=get(a), bv=get(b), d=av-bv;
      if(d===0) d=(a.rank||0)-(b.rank||0); // stable tiebreak by rank
      return sortDir==="asc"? d : -d;
    });
    document.getElementById("rows").innerHTML = sorted.map(rowHTML).join("");
    // header indicators + aria-sort
    document.querySelectorAll(".colhead .sortable").forEach(function(btn){
      var k=btn.getAttribute("data-sort"), ind=btn.querySelector(".ind");
      if(k===sortKey){ btn.setAttribute("aria-sort", sortDir==="asc"?"ascending":"descending"); if(ind) ind.textContent=sortDir==="asc"?"▲":"▼"; }
      else { btn.setAttribute("aria-sort","none"); if(ind) ind.textContent="▾"; }
    });
    var note=document.getElementById("sortnote");
    if(note) note.textContent="Sorted by "+(SORT_LABEL[sortKey]||sortKey)+" "+(sortDir==="asc"?"↑":"↓");
  }

  function render(data){
    var repos=data.repos||[];
    ALL_REPOS=repos;
    var byKey={}; repos.forEach(function(r){byKey[r.repo]=r;});

    // meta
    var totalStars=repos.reduce(function(a,r){return a+(r.stars||0);},0);
    var topMom=repos.length?repos[0].momentum:0;
    document.getElementById("metarow").innerHTML =
      meta(data.repo_count, "Projects tracked") +
      meta(fmtStars(totalStars), "Combined stars") +
      meta(topMom, "Top momentum") +
      meta(relDate(data.generated_at)||data.generated_date, "Last updated");
    document.getElementById("liveline").textContent = "Live · last recomputed "+(relDate(data.generated_at)||data.generated_date);
    var fg=document.getElementById("footgen"); if(fg) fg.textContent="Data regenerated "+(relDate(data.generated_at)||data.generated_date);

    // trending
    var tr=(data.trending||[]).map(function(k){return byKey[k];}).filter(Boolean);
    document.getElementById("trending").innerHTML = tr.length ? tr.map(function(r){
      return '<a class="trend-card" href="'+esc(r.html_url)+'" target="_blank" rel="noopener">'
        +'<div class="tn">'+esc(r.name)+'</div>'
        +'<div class="delta">▲ +'+r.commit_delta+' commits vs prior month</div>'
        +'<div class="tcat">'+esc(r.category)+'</div></a>';
    }).join("") : '<div class="sortnote">No upward movers this cycle.</div>';

    // filters
    var cats=["All"].concat(data.categories||[]);
    document.getElementById("filters").innerHTML = cats.map(function(c,i){
      return '<button class="chip'+(i===0?' active':'')+'" data-filter="'+esc(c)+'" aria-pressed="'+(i===0)+'">'+esc(c)+'</button>';
    }).join("");

    // rows (sorted) — default momentum desc
    applySort();

    // ItemList JSON-LD for home (top ~50 by rank) — SEO/AEO/GEO
    try{
      var list=repos.slice(0,50).map(function(r,i){
        return {"@type":"ListItem","position":i+1,"url":"https://stacktracker.kymatalabs.com/p/"+slugify(r.owner,r.name)+"/","name":r.owner+"/"+r.name};
      });
      var ld={"@context":"https://schema.org","@type":"ItemList","name":"StackTracker — AI-infra momentum index","numberOfItems":list.length,"itemListOrder":"https://schema.org/ItemListOrderDescending","itemListElement":list};
      var el=document.getElementById("ld-itemlist");
      if(!el){ el=document.createElement("script"); el.type="application/ld+json"; el.id="ld-itemlist"; document.head.appendChild(el); }
      el.textContent=JSON.stringify(ld);
    }catch(e){}

    // filter behavior
    var chips=document.querySelectorAll(".chip");
    chips.forEach(function(chip){
      chip.addEventListener("click", function(){
        chips.forEach(function(c){var on=c===chip;c.classList.toggle("active",on);c.setAttribute("aria-pressed",on);});
        curFilter=chip.getAttribute("data-filter");
        document.querySelectorAll(".row").forEach(function(row){
          row.classList.toggle("hide", curFilter!=="All" && row.getAttribute("data-cat")!==curFilter);
        });
      });
    });

    // sort behavior — click toggles asc/desc; keyboard accessible (native <button>)
    document.querySelectorAll(".colhead .sortable").forEach(function(btn){
      btn.addEventListener("click", function(){
        var k=btn.getAttribute("data-sort");
        if(k===sortKey){ sortDir = sortDir==="asc"?"desc":"asc"; }
        else { sortKey=k; sortDir="desc"; }
        applySort();
        // re-apply active category filter after re-render
        if(curFilter!=="All"){
          document.querySelectorAll(".row").forEach(function(row){
            row.classList.toggle("hide", row.getAttribute("data-cat")!==curFilter);
          });
        }
      });
    });
  }
  function meta(v,l){ return '<div class="m"><b>'+esc(v)+'</b><span>'+esc(l)+'</span></div>'; }

  fetch("data.json", {cache:"no-store"}).then(function(r){return r.json();}).then(render).catch(function(e){
    document.getElementById("rows").innerHTML='<div class="loading">Could not load the index. '+esc(e.message||e)+'</div>';
  });
})();
