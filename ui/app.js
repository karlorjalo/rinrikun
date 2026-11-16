const $ = (s) => document.querySelector(s);
const esc = (s) => (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function displayTitles(r) {
  const native = (r.title_native || "").trim();
  const romaji = (r.title || "").trim();
  if (native) {
    const isDiff = romaji && romaji.toLowerCase() !== native.toLowerCase();
    return {
      main: native,
      sub: isDiff ? romaji : null
    };
  }
  return {
    main: romaji || "Unknown",
    sub: null
  };
}

function card(r, why) {
  const d = document.createElement("div");
  d.className = "card";
  d.dataset.id = r.id;

  const { main, sub } = displayTitles(r);
  const metaParts = [];
  if (sub) metaParts.push(esc(sub));
  if (r.year) metaParts.push(r.year);
  if (r.genres && r.genres.length) metaParts.push(esc(r.genres.slice(0, 2).join(", ")));

  const simVal = r.similarity != null ? Math.round(r.similarity) : null;
  const scoreVal = r.score != null ? Number(r.score).toFixed(1) : null;

  const statParts = [];
  if (simVal != null) statParts.push(`<span class="affinity">${simVal}% match</span>`);
  if (scoreVal) statParts.push(`<span class="score">★ ${scoreVal}</span>`);

  let tagHtml = "";
  if (why) {
    tagHtml = `<span class="chip chip-why">${esc(why)}</span>`;
  } else if (r.matched_favorite) {
    const matchChip = `<span class="chip chip-matched" title="Matches your favorite: ${esc(r.matched_favorite)}">✦ ${esc(r.matched_favorite)}</span>`;
    const linkChip = r.linked_favorite
      ? `<span class="chip chip-linked" title="AniList users recommend this show to people who like: ${esc(r.linked_favorite)}">⇄ ${esc(r.linked_favorite)}</span>`
      : "";
    const otherChips = (r.tags || []).slice(0, linkChip ? 1 : 2).map((t) => `<span class="chip">${esc(t)}</span>`).join("");
    tagHtml = matchChip + linkChip + otherChips;
  } else if (r.shared_tags && r.shared_tags.length) {
    tagHtml = r.shared_tags.slice(0, 3).map((t) => `<span class="chip chip-shared" title="Shared tag">${esc(t)}</span>`).join("");
  } else if (r.tags && r.tags.length) {
    tagHtml = r.tags.slice(0, 3).map((t) => `<span class="chip">${esc(t)}</span>`).join("");
  }

  const posterHtml = r.poster
    ? `<img src="${esc(r.poster)}" loading="lazy" alt="${esc(main)}" onerror="this.style.display='none'; this.nextElementSibling.classList.add('show');">
       <div class="poster-fallback" aria-hidden="true">${esc(main[0] || "?")}</div>`
    : `<div class="poster-fallback show" aria-hidden="true">${esc(main[0] || "?")}</div>`;

  let badgeHtml = "";
  if (r.manual_watched) {
    badgeHtml = '<span class="badge badge-manual">watched</span>';
  } else if (r.owned) {
    badgeHtml = '<span class="badge">owned</span>';
  } else if (r.franchise_owned) {
    badgeHtml = '<span class="badge badge-franchise" title="You own another show of this franchise">franchise owned</span>';
  }

  let tierHtml = "";
  if (r.tier) {
    tierHtml = `<span class="tier-pill tier-${r.tier.toLowerCase()}" title="Tier ${r.tier}">${r.tier}</span>`;
  }

  d.innerHTML = `
    <div class="poster-box">
      ${posterHtml}
    </div>
    <div class="card-content">
      <div class="t">${esc(main)} ${tierHtml} ${badgeHtml}</div>
      <div class="m submeta">${metaParts.join(" · ")}</div>
      <div class="m stats">${statParts.join(" · ")}</div>
      <div class="simbar" title="${simVal ?? 0}% match"><i style="width:${Math.max(0, Math.min(100, simVal ?? 0))}%"></i></div>
      <div class="m tagrow">${tagHtml}</div>
    </div>`;

  const quick = document.createElement("button");
  quick.className = "card-quick-seed";
  quick.title = "Recommend like this";
  quick.innerHTML = "✦";
  quick.onclick = (e) => {
    e.stopPropagation();
    useSeed(r);
  };
  d.appendChild(quick);

  d.onclick = () => openModal(r);
  return d;
}

let currentModalShow = null;

function formatOverview(text) {
  if (!text) return '<p style="color:var(--muted);font-style:italic;">No synopsis available.</p>';
  return esc(text)
    .replace(/&lt;br\s*\/?&gt;/gi, "<br>")
    .replace(/&lt;i&gt;/gi, "<i>")
    .replace(/&lt;\/i&gt;/gi, "</i>")
    .replace(/\n\n+/g, "<br><br>")
    .replace(/\n/g, "<br>");
}

async function openModal(r) {
  if (r.overview === undefined && r.id) {
    try {
      const full = await (await fetch(`/api/show/${encodeURIComponent(r.id)}`)).json();
      r = { ...r, ...full };
    } catch (e) {}
  }
  currentModalShow = r;
  const modal = $("#detail-modal");
  const { main, sub } = displayTitles(r);
  const simVal = r.similarity != null ? Math.round(r.similarity) : null;
  const scoreVal = r.score != null ? Number(r.score).toFixed(1) : null;

  const posterHtml = r.poster
    ? `<img src="${esc(r.poster)}" loading="lazy" alt="${esc(main)}" onerror="this.style.display='none'; this.nextElementSibling.classList.add('show');">
       <div class="poster-fallback" aria-hidden="true">${esc(main[0] || "?")}</div>`
    : `<div class="poster-fallback show" aria-hidden="true">${esc(main[0] || "?")}</div>`;

  const metaItems = [];
  if (r.source === "library" || (r.owned && !r.manual_watched)) {
    metaItems.push('<span class="badge">library</span>');
  } else if (r.manual_watched) {
    metaItems.push('<span class="badge badge-manual">watched</span>');
  } else {
    metaItems.push('<span class="badge badge-unowned">pool</span>');
  }
  if (r.format) metaItems.push(`<span>${esc(r.format.toUpperCase())}</span>`);
  if (r.year) metaItems.push(`<span>${r.year}</span>`);
  if (r.genres && r.genres.length) metaItems.push(`<span>${esc(r.genres.slice(0, 3).join(", "))}</span>`);

  const statItems = [];
  if (scoreVal) statItems.push(`<span class="score">★ ${scoreVal}</span>`);
  if (simVal != null) statItems.push(`<span class="affinity">${simVal}% match</span>`);

  const tags = (r.tags || []).map((t, idx) => {
    const rank = r.tag_ranks && r.tag_ranks[idx] ? `<span class="trank">${r.tag_ranks[idx]}%</span>` : "";
    return `<span class="modal-tag">${esc(t)}${rank}</span>`;
  }).join("");

  const anilistLink = r.anilist_id
    ? `<a href="https://anilist.co/anime/${r.anilist_id}" target="_blank" rel="noopener noreferrer" class="btn-action">AniList ↗</a>`
    : "";

  const isLibrary = r.source === "library";
  const watchedBtn = isLibrary
    ? ""
    : `<button class="btn-action btn-watched ${r.manual_watched ? 'active' : ''}" id="modal-toggle-watched">
         ${r.manual_watched ? 'Watched · Remove' : '+ Add to Watched'}
       </button>`;

  // A show that the user does not own can go out of the recommendations
  const dismissBtn = r.owned
    ? ""
    : `<button class="btn-action btn-dismiss ${r.dismissed ? 'active' : ''}" id="modal-toggle-dismiss"
         title="${r.dismissed ? 'Put this show back in the recommendations' : 'Remove this show from the recommendations. Shows like it get a lower score.'}">
         ${r.dismissed ? '✕ Not interested · Undo' : '✕ Not interested'}
       </button>`;

  const tierPills = ["S", "A", "B", "C", "D"].map((t) => {
    const active = r.tier === t ? "active" : "";
    return `<button class="btn-modal-tier tier-${t.toLowerCase()} ${active}" data-tier="${t}">${t}</button>`;
  }).join("");

  const clearTierBtn = r.tier
    ? `<button class="btn-modal-tier tier-clear" id="modal-clear-tier">Clear</button>`
    : "";

  const tierSection = `
    <div class="modal-tier-section">
      <span class="modal-tier-label">Preference tier:</span>
      <div class="modal-tier-pills">
        ${tierPills}
        ${clearTierBtn}
      </div>
    </div>`;

  modal.innerHTML = `
    <div class="modal-inner">
      <button class="modal-close" onclick="closeModal()" aria-label="Close dialog">✕</button>
      <div class="modal-head">
        <div class="modal-poster poster-box">${posterHtml}</div>
        <div class="modal-info">
          <div class="modal-meta-row">${metaItems.join(" · ")}</div>
          <h3 class="modal-title">${esc(main)}</h3>
          ${sub ? `<div class="modal-native">${esc(sub)}</div>` : ""}
          ${r.studios && r.studios.length ? `<div class="modal-studio">Studio: <b>${esc(r.studios.join(", "))}</b></div>` : ""}
          <div class="modal-score-row">${statItems.join(" · ")}</div>
          <div class="modal-actions">
            <button class="btn-action primary" id="modal-find-sim">Find Similar</button>
            <button class="btn-action" id="modal-seed-rec">Recommend Like This</button>
            ${watchedBtn}
            ${dismissBtn}
            ${anilistLink}
          </div>
          ${tierSection}
        </div>
      </div>
      <div class="modal-body">
        <h4>Synopsis</h4>
        <div class="modal-overview">${formatOverview(r.overview)}</div>
        ${tags ? `<h4>Tags</h4><div class="modal-tags">${tags}</div>` : ""}
      </div>
    </div>`;

  modal.querySelectorAll(".btn-modal-tier[data-tier]").forEach((btn) => {
    btn.onclick = async () => {
      const tier = btn.dataset.tier;
      await setTier(r, tier);
      openModal(r);
    };
  });
  if ($("#modal-clear-tier")) {
    $("#modal-clear-tier").onclick = async () => {
      await clearTier(r);
      openModal(r);
    };
  }

  if ($("#modal-toggle-watched")) {
    $("#modal-toggle-watched").onclick = async () => {
      const next = !r.manual_watched;
      await toggleWatched(r, next);
      openModal(r);
    };
  }

  if ($("#modal-toggle-dismiss")) {
    $("#modal-toggle-dismiss").onclick = async () => {
      if (r.dismissed) {
        await restoreRecommendation(r);
      } else {
        await dismissRecommendation(r);
      }
      if (!$("#tab-ratings").hidden) loadRatings();
      openModal(r);
    };
  }

  $("#modal-find-sim").onclick = () => {
    closeModal();
    runSimilar(r);
    $('[data-tab="similar"]').click();
  };
  $("#modal-seed-rec").onclick = () => {
    closeModal();
    useSeed(r);
  };

  modal.showModal();
}

async function toggleWatched(r, next) {
  try {
    await apiWrite("/api/watched", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: r.id, watched: next })
    });
    r.manual_watched = next ? 1 : 0;
    r.owned = next ? 1 : 0;
    const t = titles.find((x) => x.id === r.id);
    if (t) {
      t.manual_watched = r.manual_watched;
      t.owned = r.owned;
    }
    if (!$("#tab-ratings").hidden) {
      loadRatings();
    }
    if (!$("#tab-profile").hidden) {
      profile();
    }
  } catch (e) {
    console.error("Failed to toggle watched status", e);
  }
}

async function setTier(r, tier) {
  try {
    await apiWrite("/api/weights", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: r.id, tier: tier })
    });
    r.tier = tier;
    const t = titles.find((x) => x.id === r.id);
    if (t) t.tier = tier;
    document.querySelectorAll(`.card[data-id="${r.id}"]`).forEach((c) => {
      const tEl = c.querySelector(".t");
      if (tEl) {
        let pill = tEl.querySelector(".tier-pill");
        if (!pill) {
          pill = document.createElement("span");
          tEl.insertBefore(pill, tEl.querySelector(".badge") || null);
        }
        pill.className = `tier-pill tier-${tier.toLowerCase()}`;
        pill.title = `Tier ${tier}`;
        pill.textContent = tier;
      }
    });
    if (typeof reviewQueue !== "undefined" && reviewQueue[reviewIndex] && reviewQueue[reviewIndex].id === r.id) {
      reviewQueue[reviewIndex].tier = tier;
      if (typeof updateActiveTierButton === "function") updateActiveTierButton(tier);
      const wrapPill = document.querySelector("#deck-wrap .tier-pill");
      if (wrapPill) {
        wrapPill.className = `tier-pill tier-${tier.toLowerCase()}`;
        wrapPill.textContent = tier;
      }
    }
    if (!$("#tab-profile").hidden) {
      profile();
    }
    if (!$("#tab-ratings").hidden) {
      loadRatings();
    }
  } catch (e) {
    console.error("Failed to set tier", e);
  }
}

async function clearTier(r) {
  try {
    await apiWrite(`/api/weights?id=${encodeURIComponent(r.id)}`, { method: "DELETE" });
    r.tier = null;
    const t = titles.find((x) => x.id === r.id);
    if (t) t.tier = null;
    document.querySelectorAll(`.card[data-id="${r.id}"]`).forEach((c) => {
      const pill = c.querySelector(".tier-pill");
      if (pill) pill.remove();
    });
    if (typeof reviewQueue !== "undefined" && reviewQueue[reviewIndex] && reviewQueue[reviewIndex].id === r.id) {
      reviewQueue[reviewIndex].tier = null;
      if (typeof updateActiveTierButton === "function") updateActiveTierButton(null);
      const wrapPill = document.querySelector("#deck-wrap .tier-pill");
      if (wrapPill) wrapPill.remove();
    }
    if (!$("#tab-profile").hidden) {
      profile();
    }
    if (!$("#tab-ratings").hidden) {
      loadRatings();
    }
  } catch (e) {
    console.error("Failed to clear tier", e);
  }
}

function closeModal() {
  const m = $("#detail-modal");
  if (m.open) m.close();
}

$("#detail-modal").onclick = (e) => {
  if (e.target === $("#detail-modal")) closeModal();
};

let profileData = null;

async function profile() {
  profileData = await (await fetch("/api/profile")).json();
  renderProfile();
}

function renderProfile() {
  const p = profileData;
  const el = $("#tab-profile");
  if (!p) return;

  // Build the tab only one time. A later call changes only the numbers. If each call built the
  // tab again, the map would be new after each edit, and the user would lose the zoom and the position.
  if (!$("#profile-vector-canvas")) buildProfile(el);

  const tiers = p.tier_summary || {};
  // A show in the library is not always a show that the user watched. Thus the text does not say "watched" for it.
  const inLibrary = p.library_count ?? p.owned_count;
  const marked = p.owned_count - inLibrary;
  const counts = [`${inLibrary} in your library`];
  if (marked > 0) counts.push(`${marked} marked as watched`);
  counts.push(`${p.total_count.toLocaleString()} in the catalog`);
  $("#profile-counts").textContent = counts.join(" · ");
  el.querySelectorAll("[data-tier-count]").forEach((node) => {
    node.textContent = tiers[node.dataset.tierCount] || 0;
  });
}

function buildProfile(el) {
  const tierItem = (t) => `
            <div class="tier-summary-item clickable" data-filter-tier="${t}" title="View ${t} tier ratings"><span class="tier-pill tier-${t.toLowerCase()}">${t}</span> <span class="tier-summary-count" data-tier-count="${t}"></span></div>`;

  el.innerHTML = `
    <div class="hero-dna">
      <div class="hero-dna-top">
        <h2 class="hero-dna-title">Taste profile</h2>
        <span class="hero-dna-counts" id="profile-counts"></span>
      </div>
      <div class="tier-summary-box">
        <div class="tier-summary-title">
          <span>Your ratings</span>
        </div>
        <div class="tier-summary-row">${["S", "A", "B", "C", "D"].map(tierItem).join("")}
          <div class="tier-summary-item" style="color:var(--muted);"><span style="font-size:11.5px;">Unrated:</span> <span class="tier-summary-count" data-tier-count="unrated"></span></div>
        </div>
      </div>
    </div>

    <div class="vector-map-wrap" id="profile-vector-map-wrap">
      <div class="vector-map-header">
        <div class="vector-map-title">
          <span>Taste Map</span>
          <span class="vector-map-sub">2D Vector Space</span>
        </div>
        <div class="vector-map-legend">
          <div class="vector-view-pills" data-canvas="profile-vector-canvas">
            <button class="pill active" data-view="posters">Posters</button>
            <button class="pill" data-view="dots">Dots</button>
          </div>
          <span class="legend-item"><i class="legend-dot dot-catalog"></i> Catalog</span>
          <span class="legend-item"><i class="legend-dot dot-library"></i> Your shows</span>
          <span class="legend-item legend-tiers" title="A show of yours with a tier has the color of its tier"><i class="legend-dot dot-tier-s"></i>S <i class="legend-dot dot-tier-a"></i>A <i class="legend-dot dot-tier-b"></i>B <i class="legend-dot dot-tier-c"></i>C <i class="legend-dot dot-tier-d"></i>D</span>
        </div>
      </div>
      <div class="vector-canvas-box">
        <canvas id="profile-vector-canvas"></canvas>
        <div class="vector-map-tooltip" id="profile-vector-tooltip" hidden></div>
      </div>
    </div>
  `;

  el.querySelectorAll(".tier-summary-item[data-filter-tier]").forEach((btn) => {
    btn.onclick = () => {
      ratingsTierFilter = btn.dataset.filterTier;
      document.querySelector('[data-tab="ratings"]').click();
    };
  });

  // The map shows the S-tier shows as posters
  getVectorMap().then(() => {
    initVectorMap("profile-vector-canvas", "profile-vector-tooltip", sTierIds(), "S tier", "tier");
  });
}

let vectorMapData = null;
let vectorMapLoading = null;
// The points of the loaded map, by the id of the show
const vectorMapPoints = new Map();
// The changes that the user makes while the map data loads. That data can be older than these changes.
let lateMapChanges = [];

// Download the map data one time. All maps use the same data.
function getVectorMap() {
  if (!vectorMapLoading) {
    lateMapChanges = [];
    vectorMapLoading = fetch("/api/vector-map")
      .then((res) => res.json())
      .then((data) => {
        vectorMapPoints.clear();
        (data.points || []).forEach((pt) => vectorMapPoints.set(pt.id, pt));
        vectorMapData = data;
        lateMapChanges.forEach(changeMapPoints);
        lateMapChanges = [];
        return data;
      })
      .catch((e) => {
        console.error("Failed to load vector map data", e);
        vectorMapLoading = null;
        return null;
      });
  }
  return vectorMapLoading;
}

// Change the points of the loaded map in their positions. `change` is the answer of the server
// to a change of a tier or of the watched state.
function changeMapPoints(change) {
  (change.ids || [change.id]).forEach((id) => {
    const pt = vectorMapPoints.get(id);
    if (!pt) return;
    if ("tier" in change) pt.tier = change.tier;
    if ("owned" in change) pt.owned = change.owned;
  });
}

function sTierIds() {
  return ((vectorMapData && vectorMapData.points) || [])
    .filter((pt) => pt.owned && pt.tier === "S")
    .map((pt) => pt.id);
}

// Draw the open maps again after a change. A map keeps its zoom and its position.
function refreshOpenMaps() {
  const profileMap = activeVectorMaps.get("profile-vector-canvas");
  if (profileMap) profileMap.setHighlight(sTierIds());
  activeVectorMaps.forEach((ctrl) => ctrl.scheduleDraw());
}

// Send a change of a tier or of the watched state to the server. The map shows tiers and the
// watched state, thus the open maps get the change immediately. The map data is not downloaded
// again: a new download would build the maps again.
async function apiWrite(url, options) {
  const res = await fetch(url, options);
  if (res.ok) {
    const change = await res.clone().json();
    if (vectorMapData) changeMapPoints(change);
    else lateMapChanges.push(change);
    refreshOpenMaps();
  }
  return res;
}

const posterImgCache = new Map();
const posterListeners = new Map();
// The cache keeps this number of posters. The close view of the map asks for the posters of all
// shows in view (about 700 when the posters appear), and the catalog has thousands of shows.
const POSTER_CACHE_MAX = 1600;

function getPosterImage(url, onLoaded) {
  if (!url) return null;
  if (posterImgCache.has(url)) {
    const entry = posterImgCache.get(url);
    if (entry && entry.complete && entry.naturalWidth > 0) {
      // Move the poster to the end: the cache drops the posters that were not used for the longest time
      posterImgCache.delete(url);
      posterImgCache.set(url, entry);
      return entry;
    }
    if (entry === false) return null;
    if (onLoaded) {
      // A set, so that a map that draws 60 times in one second is in the list one time
      if (!posterListeners.has(url)) posterListeners.set(url, new Set());
      posterListeners.get(url).add(onLoaded);
    }
    return null;
  }

  const img = new Image();
  if (onLoaded) {
    posterListeners.set(url, new Set([onLoaded]));
  }
  img.onload = () => {
    posterImgCache.set(url, img);
    const list = posterListeners.get(url) || [];
    posterListeners.delete(url);
    list.forEach((cb) => {
      try { cb(); } catch (e) {}
    });
  };
  img.onerror = () => {
    posterImgCache.set(url, false);
    posterListeners.delete(url);
  };
  img.src = url;

  if (img.complete && img.naturalWidth > 0) {
    posterImgCache.set(url, img);
    return img;
  }
  posterImgCache.set(url, img);
  while (posterImgCache.size > POSTER_CACHE_MAX) {
    posterImgCache.delete(posterImgCache.keys().next().value);
  }
  return null;
}

const activeVectorMaps = new Map();

async function initVectorMap(canvasId, tooltipId, highlightIds = [], highlightLabel = "Highlighted", highlightKind = "recommended") {
  const canvas = document.getElementById(canvasId);
  const tooltip = document.getElementById(tooltipId);
  if (!canvas || !tooltip) return;

  const data = await getVectorMap();
  if (!data || !data.points) return;

  // The highlighted shows are posters also in the far view. On the Recommendations map they are
  // the recommendations (kind "recommended"). On the Profile map they are the S-tier shows
  // (kind "tier"), and they have the look of their tier.
  const highlightSet = new Set(highlightIds);
  const points = data.points;
  const regions = data.regions || [];
  const n = points.length;
  // In the close view each show has its own cell of a grid, so that no poster covers another
  // poster. `cell` is the size of one cell in map units.
  const cell = data.cell && data.cell.w > 0 ? data.cell : null;

  if (activeVectorMaps.has(canvasId)) {
    activeVectorMaps.get(canvasId).destroy();
  }

  const box = canvas.parentElement;
  let hoveredPoint = null;

  // Zoom & Pan state
  let scale = 1.0;
  let panX = 0;
  let panY = 0;
  let isDragging = false;
  let hasDragged = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let pinchStartDist = 0;
  let pinchStartScale = 1.0;
  let animFrame = null;
  let destroyed = false;

  const PAD = 24;
  // The width of a cell in pixels at the largest zoom. The zoom stops there: each show in view
  // has a large poster with its title, and a larger zoom shows nothing more.
  const CELL_MAX = 112;
  // The posters appear when their width is CARD_MIN pixels
  const CARD_MIN = 18;
  // The width of a poster as a part of the width of its cell
  const CARD_FILL = 0.9;
  const POSTER_ASPECT = 1.45;
  // A poster shows its title from this width
  const TITLE_MIN = 72;
  // The area labels have three levels. The labels of a level appear from this zoom.
  const REGION_MIN_SCALE = [0, 1.7, 4];

  // The map positions and the grid positions of the shows, and their screen positions in the last draw
  const mapX = new Float32Array(n);
  const mapY = new Float32Array(n);
  const gridX = new Float32Array(n);
  const gridY = new Float32Array(n);
  const sx = new Float32Array(n);
  const sy = new Float32Array(n);
  const indexOf = new Map();
  for (let i = 0; i < n; i++) {
    const pt = points[i];
    mapX[i] = pt.x;
    mapY[i] = pt.y;
    gridX[i] = pt.gx ?? pt.x;
    gridY[i] = pt.gy ?? pt.y;
    indexOf.set(pt.id, i);
  }
  const fontFamily = getComputedStyle(document.body).fontFamily;

  function viewMode() {
    return canvas.dataset.view || "posters";
  }

  function viewSize() {
    const rect = box.getBoundingClientRect();
    return { w: rect.width, h: rect.height, side: Math.max(1, Math.min(rect.width, rect.height) - 2 * PAD) };
  }

  // The width of one cell in pixels at a zoom of 1
  function cellBase(side) {
    return cell ? cell.w * side : 0;
  }

  // The zoom at which the posters appear
  function cardScale(side) {
    return cell ? CARD_MIN / CARD_FILL / cellBase(side) : Infinity;
  }

  function maxScale(side) {
    return cell ? Math.max(4, CELL_MAX / cellBase(side)) : 12;
  }

  // The close view: each show in view is a poster in its cell
  function cardsOn(side) {
    return viewMode() === "posters" && scale >= cardScale(side);
  }

  // 0 = the map positions, 1 = the grid positions. In the last part of the zoom before the
  // posters appear, the shows move from their map positions to their cells.
  function gridBlend(side) {
    if (!cell || viewMode() !== "posters") return 0;
    const end = cardScale(side);
    const start = end * 0.55;
    const t = Math.max(0, Math.min(1, (scale - start) / (end - start)));
    return t * t * (3 - 2 * t);
  }

  // Compute the screen position of each show. One scale is used for the two axes: a stretched
  // map gives false distances.
  function project(w, h, side) {
    const t = gridBlend(side);
    const k = side * scale;
    const bx = ((w - side) / 2 - w / 2) * scale + w / 2 + panX;
    const by = ((h - side) / 2 - h / 2) * scale + h / 2 + panY;
    for (let i = 0; i < n; i++) {
      const x = mapX[i] + (gridX[i] - mapX[i]) * t;
      const y = mapY[i] + (gridY[i] - mapY[i]) * t;
      sx[i] = x * k + bx;
      sy[i] = (1 - y) * k + by;
    }
  }

  function toScreen(x, y, w, h, side) {
    return {
      x: ((w - side) / 2 + x * side - w / 2) * scale + w / 2 + panX,
      y: ((h - side) / 2 + (1 - y) * side - h / 2) * scale + h / 2 + panY,
    };
  }

  // A dot grows with the zoom, so that it stays a target for the pointer
  function dotRadius(owned) {
    return owned
      ? Math.max(2.4, Math.min(10, 2.6 * Math.pow(scale, 0.6)))
      : Math.max(1.3, Math.min(7, 1.5 * Math.pow(scale, 0.6)));
  }

  // The radius of a highlighted show in the Dots view
  function highlightDotRadius() {
    return Math.max(4.2, dotRadius(true) + 1);
  }

  // The width of the poster of a highlighted show in the far view. It gets the size of the other
  // posters at the zoom where these appear, so that it does not change its size suddenly.
  function markerWidth(side) {
    const base = 24 * Math.max(1.0, Math.min(1.8, Math.sqrt(scale)));
    const end = cardScale(side);
    if (!isFinite(end) || end <= 3.24 || scale <= 3.24) return base;
    const t = Math.min(1, (scale - 3.24) / (end - 3.24));
    return base + (CARD_MIN - base) * t;
  }

  function scheduleDraw() {
    // A poster that loads late must not draw a map that is replaced
    if (destroyed) return;
    if (!animFrame) {
      animFrame = requestAnimationFrame(() => {
        animFrame = null;
        draw();
      });
    }
  }

  // Inject Zoom Controls into canvas box if not present
  let zoomBox = box.querySelector(".vector-zoom-controls");
  if (!zoomBox) {
    zoomBox = document.createElement("div");
    zoomBox.className = "vector-zoom-controls";
    zoomBox.innerHTML = `
      <button class="vector-zoom-btn btn-zoom-in" title="Zoom in (+)" aria-label="Zoom in">+</button>
      <button class="vector-zoom-btn btn-zoom-out" title="Zoom out (−)" aria-label="Zoom out">−</button>
      <button class="vector-zoom-btn btn-zoom-reset" title="Reset view (↺)" aria-label="Reset view">↺</button>
      <div class="vector-zoom-level">100%</div>
    `;
    box.appendChild(zoomBox);
  }
  const zoomLevelEl = zoomBox.querySelector(".vector-zoom-level");
  const btnZoomIn = zoomBox.querySelector(".btn-zoom-in");
  const btnZoomOut = zoomBox.querySelector(".btn-zoom-out");
  const btnZoomReset = zoomBox.querySelector(".btn-zoom-reset");

  let hintPill = box.querySelector(".vector-hint-pill");
  if (!hintPill) {
    hintPill = document.createElement("div");
    hintPill.className = "vector-hint-pill";
    hintPill.textContent = "Scroll to zoom · Drag to pan · Zoom in to see the posters";
    box.appendChild(hintPill);
  }

  function dismissHint() {
    if (hintPill) hintPill.classList.add("fade-out");
  }
  setTimeout(dismissHint, 3500);

  function applyZoom(factor, mx, my) {
    const { w, h, side } = viewSize();
    if (w === 0 || h === 0) return;
    const newScale = Math.max(0.65, Math.min(maxScale(side), scale * factor));
    if (Math.abs(newScale - scale) < 0.001) return;
    panX = mx - w / 2 - ((mx - panX - w / 2) / scale) * newScale;
    panY = my - h / 2 - ((my - panY - h / 2) / scale) * newScale;
    scale = newScale;
    dismissHint();
    scheduleDraw();
  }

  btnZoomIn.onclick = (e) => {
    e.stopPropagation();
    const rect = box.getBoundingClientRect();
    applyZoom(1.5, rect.width / 2, rect.height / 2);
  };
  btnZoomOut.onclick = (e) => {
    e.stopPropagation();
    const rect = box.getBoundingClientRect();
    applyZoom(1 / 1.5, rect.width / 2, rect.height / 2);
  };
  btnZoomReset.onclick = (e) => {
    e.stopPropagation();
    scale = 1.0;
    panX = 0;
    panY = 0;
    dismissHint();
    scheduleDraw();
  };

  // View toggle pills (Posters vs Dots)
  const viewPills = box.parentElement.querySelectorAll(`.vector-view-pills[data-canvas="${canvasId}"] button`);
  viewPills.forEach((btn) => {
    btn.onclick = () => {
      viewPills.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      canvas.dataset.view = btn.dataset.view;
      scheduleDraw();
    };
  });

  function getThemeAccent() {
    const raw = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
    return raw || "#b35c72";
  }

  function roundedRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(x, y, w, h, r);
    else ctx.rect(x, y, w, h);
  }

  // The frame and the badge of a poster tell what the show is for the user:
  // a recommendation, a show with a tier, a show of the user without a tier, or a show of the catalog.
  function pointLook(pt, colors) {
    if (highlightSet.has(pt.id) && highlightKind === "recommended") {
      return { stroke: colors.accent, strong: true, glow: true, badge: "✦", badgeColor: colors.accent };
    }
    if (pt.owned && pt.tier) {
      const color = colors.tier[pt.tier] || colors.library;
      return { stroke: color, strong: true, glow: false, badge: pt.tier, badgeColor: color };
    }
    if (pt.owned) {
      return { stroke: colors.library, strong: true, glow: false, badge: null };
    }
    return { stroke: colors.neutral, strong: false, glow: false, badge: null };
  }

  // A large poster uses the larger image file. The small file is 100 pixels wide.
  function posterImage(pt, pw) {
    if (!pt.poster) return null;
    const dpr = window.devicePixelRatio || 1;
    if (pw * dpr > 110 && pt.poster.includes("/cover/small/")) {
      const large = getPosterImage(pt.poster.replace("/cover/small/", "/cover/medium/"), scheduleDraw);
      if (large) return large;
    }
    return getPosterImage(pt.poster, scheduleDraw);
  }

  // Divide a title into lines of the given width. A title that is too long ends with "…".
  function wrapTitle(ctx, text, maxWidth, maxLines) {
    const chars = Array.from(text || "");
    const lines = [];
    let line = "";
    let i = 0;
    for (; i < chars.length; i++) {
      const next = line + chars[i];
      if (line && ctx.measureText(next).width > maxWidth) {
        if (lines.length === maxLines - 1) break;
        lines.push(line);
        line = chars[i] === " " ? "" : chars[i];
      } else {
        line = next;
      }
    }
    if (i < chars.length) {
      const cut = Array.from(line);
      while (cut.length && ctx.measureText(cut.join("") + "…").width > maxWidth) cut.pop();
      line = cut.join("") + "…";
    }
    if (line) lines.push(line);
    return lines;
  }

  const titleLines = new Map();

  function drawTitle(ctx, pt, x, y, pw, ph) {
    const fontSize = Math.max(10, Math.min(13, pw * 0.118));
    ctx.font = `600 ${fontSize}px ${fontFamily}`;
    const key = `${pt.id}|${Math.round(pw)}`;
    let lines = titleLines.get(key);
    if (!lines) {
      lines = wrapTitle(ctx, displayTitles(pt).main, pw - 8, 2);
      if (titleLines.size > 4000) titleLines.clear();
      titleLines.set(key, lines);
    }
    if (!lines.length) return;
    const lineHeight = fontSize * 1.25;
    const band = lines.length * lineHeight + 22;
    // A dark band behind the title, so that the text is readable on each poster
    const shade = ctx.createLinearGradient(0, y + ph - band, 0, y + ph);
    shade.addColorStop(0, "rgba(0, 0, 0, 0)");
    shade.addColorStop(0.5, "rgba(0, 0, 0, 0.66)");
    shade.addColorStop(1, "rgba(0, 0, 0, 0.88)");
    ctx.fillStyle = shade;
    ctx.fillRect(x, y + ph - band, pw, band);
    ctx.fillStyle = "#ffffff";
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
    for (let k = 0; k < lines.length; k++) {
      ctx.fillText(lines[k], x + 4, y + ph - 6 - (lines.length - 1 - k) * lineHeight);
    }
  }

  function drawBadge(ctx, look, x, y, pw, colors) {
    const size = Math.max(8, Math.min(30, pw * 0.3));
    if (pw < 30) {
      // A small poster has a dot in the color of the badge
      ctx.beginPath();
      ctx.arc(x + size * 0.2, y + size * 0.2, size * 0.5, 0, Math.PI * 2);
      ctx.fillStyle = look.badgeColor;
      ctx.fill();
      ctx.lineWidth = 1;
      ctx.strokeStyle = colors.paper;
      ctx.stroke();
      return;
    }
    const bx = x - size * 0.2;
    const by = y - size * 0.2;
    roundedRect(ctx, bx, by, size, size, size * 0.25);
    ctx.fillStyle = look.badgeColor;
    ctx.fill();
    ctx.lineWidth = Math.max(1, size * 0.08);
    ctx.strokeStyle = colors.paper;
    ctx.stroke();
    ctx.fillStyle = "#ffffff";
    ctx.font = `700 ${Math.round(size * 0.62)}px ${fontFamily}`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(look.badge, bx + size / 2, by + size / 2 + size * 0.04);
  }

  // Draw the poster of a show with its center at (cx, cy)
  function drawCard(ctx, pt, cx, cy, pw, colors, isHovered) {
    const ph = pw * POSTER_ASPECT;
    const x = cx - pw / 2;
    const y = cy - ph / 2;
    const radius = Math.max(2, pw * 0.06);
    const look = pointLook(pt, colors);
    // The frame grows with the poster, so that the color of the tier stays visible
    const frame = look.strong ? Math.max(1.5, pw * 0.05) : 1;

    if (look.glow || isHovered) {
      ctx.save();
      ctx.shadowColor = isHovered ? colors.shadow : look.stroke;
      ctx.shadowBlur = isHovered ? Math.max(12, pw * 0.22) : Math.max(6, pw * 0.14);
      ctx.fillStyle = colors.paper;
      roundedRect(ctx, x, y, pw, ph, radius);
      ctx.fill();
      ctx.restore();
    }

    ctx.save();
    roundedRect(ctx, x, y, pw, ph, radius);
    ctx.clip();
    const img = posterImage(pt, pw);
    if (img) {
      // Fill the poster area, and cut the part of the image that does not fit
      const k = Math.max(pw / img.naturalWidth, ph / img.naturalHeight);
      const sw = pw / k;
      const sh = ph / k;
      ctx.drawImage(img, (img.naturalWidth - sw) / 2, (img.naturalHeight - sh) / 2, sw, sh, x, y, pw, ph);
    } else {
      // The image is not loaded: show the first character of the title
      ctx.fillStyle = colors.empty;
      ctx.fillRect(x, y, pw, ph);
      if (pw >= 28) {
        ctx.fillStyle = look.strong ? look.stroke : colors.muted;
        ctx.font = `700 ${Math.round(pw * 0.42)}px ${fontFamily}`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText((pt.title_native || pt.title || "?").trim()[0] || "?", cx, cy);
      }
    }
    if (pw >= TITLE_MIN) drawTitle(ctx, pt, x, y, pw, ph);
    ctx.restore();

    ctx.strokeStyle = isHovered ? colors.ink : look.stroke;
    ctx.lineWidth = isHovered ? Math.max(2.5, frame) : frame;
    roundedRect(ctx, x, y, pw, ph, radius);
    ctx.stroke();

    if (look.badge) drawBadge(ctx, look, x, y, pw, colors);
  }

  function draw() {
    if (!canvas.isConnected) return;
    const { w, h, side } = viewSize();
    if (w === 0 || h === 0) return;

    if (zoomLevelEl) {
      zoomLevelEl.textContent = `${Math.round(scale * 100)}%`;
    }

    const dpr = window.devicePixelRatio || 1;
    if (canvas.width !== Math.floor(w * dpr) || canvas.height !== Math.floor(h * dpr)) {
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
    }

    const ctx = canvas.getContext("2d");
    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    project(w, h, side);

    const isDark = document.documentElement.dataset.theme === "dark" ||
      (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
    const rootStyle = getComputedStyle(document.documentElement);
    const colors = {
      accent: getThemeAccent(),
      catalog: isDark ? "rgba(168, 162, 158, 0.28)" : "rgba(120, 113, 108, 0.24)",
      library: isDark ? "rgba(235, 230, 220, 0.75)" : "rgba(40, 36, 33, 0.62)",
      neutral: isDark ? "rgba(168, 162, 158, 0.55)" : "rgba(120, 113, 108, 0.5)",
      muted: isDark ? "#a8a29e" : "#78716c",
      empty: isDark ? "#3a3833" : "#efede6",
      paper: isDark ? "#262624" : "#ffffff",
      ink: isDark ? "#f5f2ea" : "#1c1917",
      shadow: isDark ? "rgba(0, 0, 0, 0.7)" : "rgba(28, 25, 23, 0.45)",
      tier: {},
    };
    for (const t of ["S", "A", "B", "C", "D"]) {
      colors.tier[t] = rootStyle.getPropertyValue(`--tier-${t.toLowerCase()}`).trim();
    }
    const view = viewMode();
    const cards = cardsOn(side);
    let shown = 0;
    let cardWidth = 0;

    if (cards) {
      // The close view. Each show in view is a poster in its cell: catalog first, then the shows
      // of the user, then the highlighted shows, and the show under the pointer last.
      cardWidth = Math.min(CELL_MAX, cellBase(side) * scale) * CARD_FILL;
      const cardHeight = cardWidth * POSTER_ASPECT;
      const layers = [[], [], []];
      for (let i = 0; i < n; i++) {
        if (sx[i] < -cardWidth || sx[i] > w + cardWidth || sy[i] < -cardHeight || sy[i] > h + cardHeight) continue;
        const pt = points[i];
        if (hoveredPoint && pt.id === hoveredPoint.id) continue;
        layers[highlightSet.has(pt.id) ? 2 : pt.owned ? 1 : 0].push(i);
      }
      for (const layer of layers) {
        for (const i of layer) {
          drawCard(ctx, points[i], sx[i], sy[i], cardWidth, colors, false);
          shown++;
        }
      }
      const hi = hoveredPoint ? indexOf.get(hoveredPoint.id) : undefined;
      if (hi !== undefined) {
        drawCard(ctx, hoveredPoint, sx[hi], sy[hi], cardWidth * 1.12, colors, true);
        shown++;
      }
    } else {
      // The far view. A highlighted show is a poster (Posters view) or a larger dot (Dots view).
      const markers = view === "posters";
      const special = (pt) => highlightSet.has(pt.id) && (markers || highlightKind === "recommended");

      // 1. The dots of the catalog
      ctx.fillStyle = colors.catalog;
      ctx.beginPath();
      const catR = dotRadius(false);
      for (let i = 0; i < n; i++) {
        const pt = points[i];
        if (pt.owned || special(pt)) continue;
        if (sx[i] < -20 || sx[i] > w + 20 || sy[i] < -20 || sy[i] > h + 20) continue;
        ctx.moveTo(sx[i] + catR, sy[i]);
        ctx.arc(sx[i], sy[i], catR, 0, Math.PI * 2);
      }
      ctx.fill();

      // 2. The dots of the shows of the user. A rated show has the color of its tier. S is last, on top.
      const libR = dotRadius(true);
      for (const tier of [null, "D", "C", "B", "A", "S"]) {
        ctx.fillStyle = (tier && colors.tier[tier]) || colors.library;
        ctx.beginPath();
        for (let i = 0; i < n; i++) {
          const pt = points[i];
          if (!pt.owned || special(pt) || (pt.tier || null) !== tier) continue;
          if (sx[i] < -20 || sx[i] > w + 20 || sy[i] < -20 || sy[i] > h + 20) continue;
          ctx.moveTo(sx[i] + libR, sy[i]);
          ctx.arc(sx[i], sy[i], libR, 0, Math.PI * 2);
        }
        ctx.fill();
      }

      // 3. The highlighted shows
      if (markers) {
        const width = markerWidth(side);
        let hovered = -1;
        for (let i = 0; i < n; i++) {
          const pt = points[i];
          if (!highlightSet.has(pt.id)) continue;
          if (sx[i] < -60 || sx[i] > w + 60 || sy[i] < -90 || sy[i] > h + 90) continue;
          if (hoveredPoint && hoveredPoint.id === pt.id) {
            hovered = i;
            continue;
          }
          drawCard(ctx, pt, sx[i], sy[i], width, colors, false);
          shown++;
        }
        if (hovered >= 0) {
          drawCard(ctx, points[hovered], sx[hovered], sy[hovered], width * 1.3, colors, true);
          shown++;
        }
      } else if (highlightKind === "recommended") {
        const hiR = highlightDotRadius();
        for (let i = 0; i < n; i++) {
          if (!highlightSet.has(points[i].id)) continue;
          if (sx[i] < -20 || sx[i] > w + 20 || sy[i] < -20 || sy[i] > h + 20) continue;
          ctx.fillStyle = colors.accent;
          ctx.globalAlpha = 0.25;
          ctx.beginPath();
          ctx.arc(sx[i], sy[i], hiR * 2, 0, Math.PI * 2);
          ctx.fill();
          ctx.globalAlpha = 1.0;
          ctx.beginPath();
          ctx.arc(sx[i], sy[i], hiR, 0, Math.PI * 2);
          ctx.fill();
          ctx.strokeStyle = colors.paper;
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }
      }

      // 4. A ring around the dot under the pointer
      const hi = hoveredPoint ? indexOf.get(hoveredPoint.id) : undefined;
      if (hi !== undefined && !(markers && highlightSet.has(hoveredPoint.id))) {
        const ringR = special(hoveredPoint) ? highlightDotRadius() * 2 + 2 : dotRadius(hoveredPoint.owned) + 6;
        ctx.strokeStyle = colors.ink;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(sx[hi], sy[hi], Math.max(9, ringR), 0, Math.PI * 2);
        ctx.stroke();
      }
    }

    // The area labels: the typical tags of each part of the map, on three levels. Level 0 has the
    // large areas. The smaller areas of the levels 1 and 2 get their labels when the user zooms in.
    // The labels are above the posters, and they go away when the posters are large enough to read.
    // A label is not drawn if it is too near a label that is there: the large areas go first,
    // then the areas with the most shows.
    let regionCount = 0;
    if (regions.length && cardWidth < 50) {
      ctx.save();
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.lineJoin = "round";
      ctx.lineWidth = 3.5;
      ctx.strokeStyle = isDark ? "rgba(38, 38, 36, 0.9)" : "rgba(252, 251, 249, 0.9)";
      const ink = isDark ? "235, 230, 220" : "40, 36, 33";
      // The look of each level: the weight, the smallest size, the largest size, the opacity
      const looks = [[600, 10.5, 15, 0.82], [600, 10.5, 12.5, 0.7], [500, 10, 11.5, 0.62]];
      const blend = gridBlend(side);
      const placed = [];
      for (const region of regions) {
        const level = Math.min(region.level || 0, looks.length - 1);
        if (scale < REGION_MIN_SCALE[level]) continue;
        // The shows move from the map to the grid in the close view, and the labels move with them
        const rx = region.x + ((region.gx ?? region.x) - region.x) * blend;
        const ry = region.y + ((region.gy ?? region.y) - region.y) * blend;
        const { x: px, y: py } = toScreen(rx, ry, w, h, side);
        if (px < -80 || px > w + 80 || py < -20 || py > h + 20) continue;
        const [weight, minSize, maxSize, alpha] = looks[level];
        const fontSize = Math.max(minSize, Math.min(maxSize, minSize * Math.sqrt(scale / Math.max(1, REGION_MIN_SCALE[level]))));
        ctx.font = `${weight} ${fontSize}px ${fontFamily}`;
        const halfWidth = ctx.measureText(region.label).width / 2 + 9;
        const halfHeight = fontSize / 2 + 7;
        if (placed.some((box) => Math.abs(box.x - px) < box.w + halfWidth && Math.abs(box.y - py) < box.h + halfHeight)) continue;
        placed.push({ x: px, y: py, w: halfWidth, h: halfHeight });
        ctx.fillStyle = `rgba(${ink}, ${alpha})`;
        ctx.strokeText(region.label, px, py);
        ctx.fillText(region.label, px, py);
      }
      regionCount = placed.length;
      ctx.restore();
    }

    // The number of posters in the last draw, for the tests of the interface
    canvas.dataset.posters = String(shown);
    canvas.dataset.labels = String(regionCount);
    canvas.dataset.cards = cards ? "1" : "0";
    ctx.restore();
  }

  // Return the show under the pointer. It uses the screen positions of the last draw.
  function findNearest(mx, my) {
    const { w, h, side } = viewSize();
    const view = viewMode();

    if (cardsOn(side)) {
      // The close view: the show whose cell is under the pointer
      const cellWidth = Math.min(CELL_MAX, cellBase(side) * scale);
      const cellHeight = cellWidth * (cell.h / cell.w);
      let best = null;
      let bestDist = Infinity;
      for (let i = 0; i < n; i++) {
        const dx = Math.abs(sx[i] - mx);
        const dy = Math.abs(sy[i] - my);
        if (dx > cellWidth / 2 || dy > cellHeight / 2) continue;
        const d = dx * dx + dy * dy;
        if (d < bestDist) {
          bestDist = d;
          best = points[i];
        }
      }
      return best;
    }

    // 1. The highlighted shows
    const markers = view === "posters";
    if (markers || highlightKind === "recommended") {
      const pw = markerWidth(side);
      const ph = pw * POSTER_ASPECT;
      const hitR = (highlightDotRadius() + 4) ** 2;
      for (let i = n - 1; i >= 0; i--) {
        if (!highlightSet.has(points[i].id)) continue;
        if (sx[i] < -60 || sx[i] > w + 60 || sy[i] < -90 || sy[i] > h + 90) continue;
        if (markers) {
          if (Math.abs(sx[i] - mx) <= pw / 2 + 1 && Math.abs(sy[i] - my) <= ph / 2 + 1) return points[i];
        } else if ((sx[i] - mx) ** 2 + (sy[i] - my) ** 2 <= hitR) {
          return points[i];
        }
      }
    }

    // 2. The dots of the shows of the user. The target is larger than the dot, and it grows with the dot.
    let bestOwned = null;
    let bestOwnedDist = Math.max(7, dotRadius(true) + 4) ** 2;
    for (let i = 0; i < n; i++) {
      if (!points[i].owned) continue;
      const d = (sx[i] - mx) ** 2 + (sy[i] - my) ** 2;
      if (d <= bestOwnedDist) {
        bestOwnedDist = d;
        bestOwned = points[i];
      }
    }
    if (bestOwned) return bestOwned;

    // 3. The dots of the catalog (in the Dots view, or from a zoom of 180%)
    if (view === "dots" || scale >= 1.8) {
      let bestCat = null;
      let bestCatDist = Math.max(6, dotRadius(false) + 4) ** 2;
      for (let i = 0; i < n; i++) {
        const d = (sx[i] - mx) ** 2 + (sy[i] - my) ** 2;
        if (d <= bestCatDist) {
          bestCatDist = d;
          bestCat = points[i];
        }
      }
      return bestCat;
    }
    return null;
  }

  function onMouseDown(e) {
    if (e.button !== 0) return;
    isDragging = true;
    hasDragged = false;
    dragStartX = e.clientX;
    dragStartY = e.clientY;
    canvas.classList.add("is-dragging");
    tooltip.hidden = true;
    tooltip.style.display = "none";
  }

  function onMouseMove(e) {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    if (isDragging) {
      const dx = e.clientX - dragStartX;
      const dy = e.clientY - dragStartY;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
        hasDragged = true;
        dismissHint();
      }
      panX += dx;
      panY += dy;
      dragStartX = e.clientX;
      dragStartY = e.clientY;
      tooltip.hidden = true;
      tooltip.style.display = "none";
      scheduleDraw();
      return;
    }

    const pt = findNearest(mx, my);
    if (pt !== hoveredPoint) {
      hoveredPoint = pt;
      scheduleDraw();
    }

    if (pt) {
      canvas.style.cursor = "pointer";
      const titles = displayTitles(pt);
      let badgeHtml = "";
      if (highlightSet.has(pt.id) && highlightKind === "recommended") {
        badgeHtml = `<span class="tt-badge tt-badge-highlight">${esc(highlightLabel)}</span>`;
      } else if (pt.tier) {
        badgeHtml = `<span class="tt-badge tt-badge-highlight" style="color:var(--tier-${pt.tier.toLowerCase()});border-color:currentColor;">Tier ${pt.tier}</span>`;
      } else if (pt.owned) {
        badgeHtml = `<span class="tt-badge tt-badge-library">Yours</span>`;
      } else {
        badgeHtml = `<span class="tt-badge tt-badge-catalog">Catalog</span>`;
      }

      const metaParts = [];
      if (pt.year) metaParts.push(pt.year);
      if (pt.genres && pt.genres.length) metaParts.push(pt.genres.join(", "));

      const posterHtml = pt.poster
        ? `<div class="tt-poster-box"><img src="${esc(pt.poster)}" alt="" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';"><div class="tt-poster-fallback" style="display:none;">${esc((pt.title_native || pt.title || "?")[0])}</div></div>`
        : `<div class="tt-poster-box"><div class="tt-poster-fallback">${esc((pt.title_native || pt.title || "?")[0])}</div></div>`;

      tooltip.innerHTML = `
        ${posterHtml}
        <div class="tt-content">
          <div class="tt-title">${esc(titles.main)}</div>
          ${titles.sub ? `<div class="tt-sub">${esc(titles.sub)}</div>` : ""}
          <div class="tt-meta">${metaParts.join(" · ")} · ${badgeHtml}</div>
        </div>
      `;
      tooltip.hidden = false;
      tooltip.style.display = "flex";

      const boxRect = box.getBoundingClientRect();
      let tx = mx + 16;
      let ty = my + 16;
      if (tx + 280 > boxRect.width) tx = mx - 290;
      if (ty + 75 > boxRect.height) ty = my - 75;
      tooltip.style.left = `${Math.max(8, tx)}px`;
      tooltip.style.top = `${Math.max(8, ty)}px`;
    } else {
      canvas.style.cursor = "grab";
      tooltip.hidden = true;
      tooltip.style.display = "none";
    }
  }

  function onMouseUp() {
    if (!isDragging) return;
    isDragging = false;
    canvas.classList.remove("is-dragging");
    if (!hasDragged && hoveredPoint) {
      openModal(hoveredPoint);
    }
  }

  function onMouseLeave() {
    isDragging = false;
    canvas.classList.remove("is-dragging");
    hoveredPoint = null;
    tooltip.hidden = true;
    tooltip.style.display = "none";
    scheduleDraw();
  }

  function onWheel(e) {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const factor = e.deltaY < 0 ? 1.2 : 1 / 1.2;
    applyZoom(factor, mx, my);
  }

  function onTouchStart(e) {
    if (e.touches.length === 1) {
      isDragging = true;
      hasDragged = false;
      dragStartX = e.touches[0].clientX;
      dragStartY = e.touches[0].clientY;
    } else if (e.touches.length === 2) {
      isDragging = false;
      pinchStartDist = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY
      );
      pinchStartScale = scale;
    }
  }

  function onTouchMove(e) {
    e.preventDefault();
    if (e.touches.length === 1 && isDragging) {
      const dx = e.touches[0].clientX - dragStartX;
      const dy = e.touches[0].clientY - dragStartY;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
        hasDragged = true;
        dismissHint();
      }
      panX += dx;
      panY += dy;
      dragStartX = e.touches[0].clientX;
      dragStartY = e.touches[0].clientY;
      tooltip.hidden = true;
      scheduleDraw();
    } else if (e.touches.length === 2 && pinchStartDist > 0) {
      const dist = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY
      );
      const rect = canvas.getBoundingClientRect();
      const midX = (e.touches[0].clientX + e.touches[1].clientX) / 2 - rect.left;
      const midY = (e.touches[0].clientY + e.touches[1].clientY) / 2 - rect.top;
      const factor = dist / pinchStartDist;
      applyZoom(factor * (pinchStartScale / scale), midX, midY);
      pinchStartDist = dist;
      pinchStartScale = scale;
    }
  }

  function onTouchEnd(e) {
    if (e.touches.length === 0) {
      isDragging = false;
      pinchStartDist = 0;
    }
  }

  canvas.addEventListener("wheel", onWheel, { passive: false });
  canvas.addEventListener("mousedown", onMouseDown);
  canvas.addEventListener("mousemove", onMouseMove);
  canvas.addEventListener("mouseup", onMouseUp);
  canvas.addEventListener("mouseleave", onMouseLeave);
  box.addEventListener("mouseleave", onMouseLeave);
  canvas.addEventListener("touchstart", onTouchStart, { passive: false });
  canvas.addEventListener("touchmove", onTouchMove, { passive: false });
  canvas.addEventListener("touchend", onTouchEnd);

  const ro = new ResizeObserver(() => scheduleDraw());
  ro.observe(box);

  scheduleDraw();

  activeVectorMaps.set(canvasId, {
    draw,
    scheduleDraw,
    setHighlight: (ids) => {
      highlightSet.clear();
      ids.forEach((id) => highlightSet.add(id));
      scheduleDraw();
    },
    destroy: () => {
      destroyed = true;
      if (animFrame) cancelAnimationFrame(animFrame);
      canvas.removeEventListener("wheel", onWheel);
      canvas.removeEventListener("mousedown", onMouseDown);
      canvas.removeEventListener("mousemove", onMouseMove);
      canvas.removeEventListener("mouseup", onMouseUp);
      canvas.removeEventListener("mouseleave", onMouseLeave);
      box.removeEventListener("mouseleave", onMouseLeave);
      canvas.removeEventListener("touchstart", onTouchStart);
      canvas.removeEventListener("touchmove", onTouchMove);
      canvas.removeEventListener("touchend", onTouchEnd);
      ro.disconnect();
    }
  });
}

let titles = [];
let searchSelectedIndex = -1;
let currentSimilarShow = null;

async function initSearch() {
  titles = await (await fetch("/api/shows")).json();
  const q = $("#q");
  const qlist = $("#qlist");
  const qClear = $("#q-clear");

  // Populate suggestions in empty state
  const ownedSample = titles.filter((t) => t.owned && (t.title_native || t.title));
  const shuffled = ownedSample.sort(() => 0.5 - Math.random()).slice(0, 5);
  const suggBox = $("#similar-suggestions");
  if (suggBox) {
    suggBox.innerHTML = shuffled.map((t) => `<button class="suggestion-chip">${esc(displayTitles(t).main)}</button>`).join("");
    suggBox.querySelectorAll("button").forEach((btn, idx) => {
      btn.onclick = () => {
        runSimilar(shuffled[idx]);
      };
    });
  }

  function renderDropdown(matches) {
    qlist.innerHTML = "";
    searchSelectedIndex = -1;
    if (!matches.length) {
      qlist.innerHTML = `<div class="qitem" style="color:var(--muted);cursor:default;">No titles found</div>`;
      qlist.hidden = false;
      return;
    }
    matches.forEach((t, i) => {
      const item = document.createElement("div");
      item.className = "qitem";
      item.dataset.idx = i;

      const { main, sub } = displayTitles(t);
      const subParts = [];
      if (sub) subParts.push(esc(sub));
      if (t.year) subParts.push(t.year);

      let badge = "";
      if (t.manual_watched) {
        badge = '<span class="badge badge-manual">watched</span>';
      } else if (t.owned) {
        badge = '<span class="badge">owned</span>';
      }

      const thumbHtml = t.poster
        ? `<img src="${esc(t.poster)}" alt="" loading="lazy" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
           <div class="qitem-fallback" style="display:none;">${esc(main[0] || "?")}</div>`
        : `<div class="qitem-fallback">${esc(main[0] || "?")}</div>`;

      item.innerHTML = `
        <div class="qitem-thumb">${thumbHtml}</div>
        <div class="qitem-info">
          <div class="qitem-title">${esc(main)} ${badge}</div>
          ${subParts.length ? `<div class="qitem-sub">${subParts.join(" · ")}</div>` : ""}
        </div>`;

      item.onclick = () => {
        runSimilar(t);
        closeSearch();
      };
      qlist.appendChild(item);
    });
    qlist.hidden = false;
  }

  function updateSearchSelection(newIdx) {
    const items = qlist.querySelectorAll(".qitem");
    if (!items.length) return;
    items.forEach((it) => it.classList.remove("selected"));
    if (newIdx >= 0 && newIdx < items.length) {
      items[newIdx].classList.add("selected");
      items[newIdx].scrollIntoView({ block: "nearest" });
      searchSelectedIndex = newIdx;
    } else {
      searchSelectedIndex = -1;
    }
  }

  function closeSearch() {
    qlist.hidden = true;
    qlist.innerHTML = "";
    searchSelectedIndex = -1;
  }

  let currentMatches = [];
  q.oninput = () => {
    const v = q.value.trim().toLowerCase();
    qClear.hidden = !v;
    if (v.length < 2) {
      closeSearch();
      return;
    }
    currentMatches = titles
      .filter((t) => (t.title + " " + (t.title_native || "")).toLowerCase().includes(v))
      .slice(0, 10);
    renderDropdown(currentMatches);
  };

  q.onkeydown = (e) => {
    if (qlist.hidden) return;
    const items = qlist.querySelectorAll(".qitem");
    if (e.key === "ArrowDown") {
      e.preventDefault();
      const next = searchSelectedIndex < items.length - 1 ? searchSelectedIndex + 1 : 0;
      updateSearchSelection(next);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const prev = searchSelectedIndex > 0 ? searchSelectedIndex - 1 : items.length - 1;
      updateSearchSelection(prev);
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (searchSelectedIndex >= 0 && currentMatches[searchSelectedIndex]) {
        runSimilar(currentMatches[searchSelectedIndex]);
        closeSearch();
      } else if (currentMatches.length > 0) {
        runSimilar(currentMatches[0]);
        closeSearch();
      }
    } else if (e.key === "Escape") {
      closeSearch();
    }
  };

  qClear.onclick = () => {
    q.value = "";
    qClear.hidden = true;
    closeSearch();
    q.focus();
  };

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".search-wrap")) {
      closeSearch();
    }
  });
}

let rawSimilar = [];
let similarFilter = "all";
let similarCount = 24;

function renderSimilarGrid() {
  const box = $("#sresults");
  if (!box) return;
  box.innerHTML = "";

  const filtered = rawSimilar.filter((r) => {
    if (similarFilter === "unowned") return !r.owned && !r.manual_watched;
    return true;
  });

  if (!filtered.length) {
    box.innerHTML = `<p style="grid-column:1/-1;color:var(--muted);text-align:center;padding:40px 0;">No similar titles match the selected filter.</p>`;
    return;
  }

  filtered.forEach((r) => box.appendChild(card(r)));
}

async function fetchSimilarShows(t) {
  const res = await (await fetch(`/api/similar?id=${encodeURIComponent(t.id)}&k=${similarCount}`)).json();
  if (Array.isArray(res)) {
    rawSimilar = res;
  } else {
    rawSimilar = [];
  }
}

async function runSimilar(t) {
  currentSimilarShow = t;
  const { main } = displayTitles(t);
  $("#qlist").hidden = true;
  $("#q").value = main;
  $("#q-clear").hidden = false;

  const empty = $("#similar-empty");
  if (empty) empty.hidden = true;

  await fetchSimilarShows(t);

  const header = $("#similar-header");
  if (header) {
    header.hidden = false;
    const simBadge = t.manual_watched ? '<span class="badge badge-manual">watched</span>' : (t.owned ? '<span class="badge">owned</span>' : "");
    header.innerHTML = `
      <div class="result-seed-bar">
        <div class="seed-info">
          <h3 class="seed-title">${esc(main)} ${simBadge}</h3>
        </div>
        <div class="seed-actions" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
          <div class="filter-pills" id="similar-filter-pills">
            <button class="pill ${similarFilter === 'all' ? 'active' : ''}" data-filter="all">All (${rawSimilar.length})</button>
            <button class="pill ${similarFilter === 'unowned' ? 'active' : ''}" data-filter="unowned">Unowned only</button>
          </div>
          <div class="filter-pills" id="similar-limit-pills">
            <button class="pill ${similarCount === 24 ? 'active' : ''}" data-count="24">24</button>
            <button class="pill ${similarCount === 48 ? 'active' : ''}" data-count="48">48</button>
          </div>
          <button class="btn-action" id="sim-view-details">Details</button>
        </div>
      </div>`;

    const fPills = $("#similar-filter-pills");
    if (fPills) {
      fPills.querySelectorAll(".pill").forEach((btn) => {
        btn.onclick = () => {
          similarFilter = btn.dataset.filter;
          fPills.querySelectorAll(".pill").forEach((b) => b.classList.remove("active"));
          btn.classList.add("active");
          renderSimilarGrid();
        };
      });
    }

    const lPills = $("#similar-limit-pills");
    if (lPills) {
      lPills.querySelectorAll(".pill").forEach((btn) => {
        btn.onclick = async () => {
          similarCount = parseInt(btn.dataset.count, 10);
          lPills.querySelectorAll(".pill").forEach((b) => b.classList.remove("active"));
          btn.classList.add("active");
          await fetchSimilarShows(t);
          if (fPills) {
            const allBtn = fPills.querySelector('[data-filter="all"]');
            if (allBtn) allBtn.textContent = `All (${rawSimilar.length})`;
          }
          renderSimilarGrid();
        };
      });
    }

    $("#sim-view-details").onclick = () => openModal(t);
  }

  renderSimilarGrid();
}

let seed = null;
let rawRecs = [];
let recsFormatFilter = "all";
let recsMinScore = 0;
// The list shows only new franchises, with the best scores, until the user turns a switch on
let recsVariety = false;
let recsSequels = false;
// The formula of the list. "usual" gives a higher score to the kinds of shows that the library has
// many of. "all" gives each kind of show the same chance. The browser keeps the selection.
const FORMULA_KEY = "rinrikun-formula";
const FORMULAS = {
  usual: {
    name: "My usual kinds",
    text: "Shows of the kinds that your library has many of move up. The kind of a show is its year, its format and its length. A show with an AniList score below 6.5 moves down. A higher AniList score gives no advantage.",
  },
  all: {
    name: "All kinds",
    text: "The year, the format, the length and the AniList score of a show do not change its position.",
  },
  seed: {
    name: "Similar to the seed",
    text: "The list has the shows that are most similar to the seed show. The two formulas have no effect on this list.",
  },
};
let recsKinds = "usual";
try {
  if (localStorage.getItem(FORMULA_KEY) === "all") recsKinds = "all";
} catch (e) {}
// The number of the last request for a list
let recsRequest = 0;

function useSeed(r) {
  seed = r;
  document.querySelector('[data-tab="recs"]').click();
}

function renderRecsSeedBar() {
  const bar = $("#recs-seed-bar");
  // A seeded list is ordered by the similarity to the seed, so the variety switch has no effect
  const varietyBtn = $("#recs-variety");
  if (varietyBtn) varietyBtn.style.display = seed ? "none" : "";
  // The formula selection also has no effect on a seeded list
  const formulaGroup = $("#recs-formula-group");
  if (formulaGroup) formulaGroup.style.display = seed ? "none" : "";

  if (!bar) return;
  if (seed) {
    const { main } = displayTitles(seed);
    bar.innerHTML = `
      <div class="recs-seed-card">
        <div class="recs-seed-left">
          <span class="seed-badge">Seed</span>
          <span class="seed-text"><b>${esc(main)}</b></span>
        </div>
        <button id="recenter-btn" class="btn-action">Clear seed ✕</button>
      </div>`;
    $("#recenter-btn").onclick = () => {
      seed = null;
      recs();
    };
  } else {
    bar.innerHTML = "";
  }
}

// Tell above the list which formula made it
function renderRecsFormulaNote(applied) {
  const note = $("#recs-formula-note");
  const formula = FORMULAS[applied];
  if (!note || !formula) return;
  note.dataset.formula = applied;
  note.innerHTML = `<b>Formula: ${formula.name}.</b> ${formula.text}`;
}

function paintRecsFormulaPills() {
  document.querySelectorAll("#recs-formula-pills .pill").forEach((btn) => {
    const on = btn.dataset.kinds === recsKinds;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-pressed", String(on));
  });
}

function initRecsFilters() {
  paintRecsFormulaPills();
  document.querySelectorAll("#recs-formula-pills .pill").forEach((btn) => {
    btn.onclick = () => {
      if (btn.dataset.kinds === recsKinds) return;
      recsKinds = btn.dataset.kinds;
      try { localStorage.setItem(FORMULA_KEY, recsKinds); } catch (e) {}
      paintRecsFormulaPills();
      recs();
    };
  });

  const bindSwitch = (id, set) => {
    const btn = $(id);
    if (!btn) return;
    btn.onclick = () => {
      const on = btn.getAttribute("aria-pressed") !== "true";
      btn.setAttribute("aria-pressed", String(on));
      btn.classList.toggle("active", on);
      set(on);
      recs();
    };
  };
  bindSwitch("#recs-variety", (on) => { recsVariety = on; });
  bindSwitch("#recs-sequels", (on) => { recsSequels = on; });

  const fPills = $("#recs-format-pills");
  if (fPills) {
    fPills.querySelectorAll(".pill").forEach((btn) => {
      btn.onclick = () => {
        fPills.querySelectorAll(".pill").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        recsFormatFilter = btn.dataset.format;
        renderRecsGrid();
      };
    });
  }

  const sPills = $("#recs-score-pills");
  if (sPills) {
    sPills.querySelectorAll(".pill").forEach((btn) => {
      btn.onclick = () => {
        sPills.querySelectorAll(".pill").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        recsMinScore = parseFloat(btn.dataset.score);
        renderRecsGrid();
      };
    });
  }
}

// The last show that the user removed from the recommendations, for the undo bar
let lastDismissed = null;

async function setDismissed(r, dismissed) {
  const res = await fetch("/api/dismissed", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: r.id, dismissed })
  });
  if (!res.ok) throw new Error(`dismiss failed: ${res.status}`);
  r.dismissed = dismissed ? 1 : 0;
}

function refreshRecsAfterDismiss() {
  renderRecsGrid();
  renderRecsUndoBar();
  const map = activeVectorMaps.get("recs-vector-canvas");
  if (map && map.setHighlight) map.setHighlight(rawRecs.map((x) => x.id));
}

async function dismissRecommendation(r) {
  try {
    await setDismissed(r, true);
    // The other cards stay in their positions: a new order after each click is hard to read
    const index = rawRecs.findIndex((x) => x.id === r.id);
    if (index >= 0) rawRecs.splice(index, 1);
    lastDismissed = { show: r, index };
    refreshRecsAfterDismiss();
  } catch (e) {
    console.error("Failed to remove the recommendation", e);
  }
}

async function restoreRecommendation(r) {
  try {
    await setDismissed(r, false);
    if (lastDismissed && lastDismissed.show.id === r.id) {
      const index = lastDismissed.index;
      if (index >= 0 && !rawRecs.some((x) => x.id === r.id)) {
        rawRecs.splice(Math.min(index, rawRecs.length), 0, lastDismissed.show);
      }
      lastDismissed = null;
    }
    refreshRecsAfterDismiss();
  } catch (e) {
    console.error("Failed to put the recommendation back", e);
  }
}

function renderRecsUndoBar() {
  const bar = $("#recs-undo-bar");
  if (!bar) return;
  if (!lastDismissed) {
    bar.innerHTML = "";
    return;
  }
  const { main } = displayTitles(lastDismissed.show);
  bar.innerHTML = `
    <div class="recs-undo-card">
      <span>Removed from your recommendations: <b>${esc(main)}</b>. Shows like it get a lower score.</span>
      <button id="recs-undo-btn" class="btn-action">Undo</button>
    </div>`;
  $("#recs-undo-btn").onclick = () => restoreRecommendation(lastDismissed.show);
}

function renderRecsGrid() {
  const box = $("#rresults");
  if (!box) return;
  box.innerHTML = "";

  const filtered = rawRecs.filter((r) => {
    if (recsFormatFilter !== "all") {
      const fmt = (r.format || "").toLowerCase();
      if (recsFormatFilter === "tv" && !fmt.includes("tv") && fmt !== "series") return false;
      if (recsFormatFilter === "movie" && !fmt.includes("movie")) return false;
      if (recsFormatFilter === "ova" && !fmt.includes("ova") && !fmt.includes("special")) return false;
    }
    if (recsMinScore > 0) {
      if (r.score == null || r.score < recsMinScore) return false;
    }
    return true;
  });

  if (!filtered.length) {
    box.innerHTML = `<p style="grid-column:1/-1;color:var(--muted);text-align:center;padding:40px 0;">No recommendations match the selected filters. Try lowering the score threshold or selecting All Formats.</p>`;
    return;
  }

  filtered.forEach((r) => {
    const el = card(r);
    const dismiss = document.createElement("button");
    dismiss.className = "card-dismiss";
    dismiss.title = "Not interested: remove from the recommendations";
    dismiss.setAttribute("aria-label", "Not interested");
    dismiss.textContent = "✕";
    dismiss.onclick = (e) => {
      e.stopPropagation();
      dismissRecommendation(r);
    };
    el.appendChild(dismiss);
    box.appendChild(el);
  });
}

async function recs() {
  lastDismissed = null;
  renderRecsUndoBar();
  renderRecsSeedBar();
  const applied = seed ? "seed" : recsKinds;
  const base = seed
    ? `/api/recommend?k=40&seed=${encodeURIComponent(seed.id)}`
    : `/api/recommend?k=40&mode=${recsVariety ? "diverse" : "hybrid"}&kinds=${recsKinds}`;
  const request = ++recsRequest;
  const list = await (await fetch(`${base}&new_only=${!recsSequels}`)).json();
  // An older request that ends late must not replace the list of a newer request. Thus the
  // note above the list always names the formula of the list that the user sees.
  if (request !== recsRequest) return;
  rawRecs = list;
  renderRecsFormulaNote(applied);
  renderRecsGrid();
  const ids = rawRecs.map((s) => s.id);
  const map = activeVectorMaps.get("recs-vector-canvas");
  // An open map keeps its zoom and its position: only the highlighted shows change
  if (map) map.setHighlight(ids);
  else initVectorMap("recs-vector-canvas", "recs-vector-tooltip", ids, "Recommended");
}

let reviewQueue = [];
let reviewIndex = 0;
let reviewFilter = "unrated";
let reviewUndoStack = [];
let totalWatchedCount = 0;
let totalRatedCount = 0;

async function loadReviewQueue() {
  try {
    const unratedOnly = reviewFilter === "unrated";
    const res = await (await fetch(`/api/review-queue?unrated_only=${unratedOnly}`)).json();
    if (!Array.isArray(res)) {
      console.error("Failed to load review queue:", res);
      const wrap = $("#deck-wrap");
      if (wrap) wrap.innerHTML = `<p style="text-align:center;color:var(--muted);padding:40px 0;">Failed to load review queue. Please ensure the server is updated and running.</p>`;
      return;
    }
    reviewQueue = res;
    reviewIndex = 0;
    reviewUndoStack = [];

    const prof = await (await fetch("/api/profile")).json();
    if (prof && prof.tier_summary) {
      const s = prof.tier_summary;
      totalRatedCount = (s.S || 0) + (s.A || 0) + (s.B || 0) + (s.C || 0) + (s.D || 0);
      totalWatchedCount = totalRatedCount + (s.unrated || 0);
    }
    updateDeckProgress();
    renderDeckCard();
  } catch (e) {
    console.error("Failed to load review queue", e);
  }
}

function updateDeckProgress() {
  const p = $("#deck-progress");
  if (!p) return;
  if (totalWatchedCount > 0) {
    p.textContent = `${totalRatedCount} of ${totalWatchedCount} rated`;
  } else {
    p.textContent = `${reviewQueue.length} shows`;
  }
}

function updateActiveTierButton(tier) {
  document.querySelectorAll(".btn-tier").forEach((b) => {
    if (tier && b.dataset.tier === tier) {
      b.classList.add("active");
    } else {
      b.classList.remove("active");
    }
  });
}

function renderDeckCard() {
  const wrap = $("#deck-wrap");
  if (!wrap) return;

  if (!reviewQueue.length || reviewIndex >= reviewQueue.length) {
    wrap.innerHTML = `
      <div class="deck-card" style="align-items:center;justify-content:center;text-align:center;padding:48px 24px;">
        <div style="max-width:380px;">
          <div style="font-size:36px;margin-bottom:12px;">🎉</div>
          <h3 style="font-family:var(--serif);font-size:20px;margin:0 0 8px;">All caught up</h3>
          <p style="color:var(--muted);font-size:14px;margin:0 0 20px;">
            ${reviewFilter === "unrated" ? "All your shows have a tier." : "You have reached the end of the review queue."}
          </p>
          <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;">
            ${reviewFilter === "unrated" ? '<button class="btn-action" id="deck-review-all-btn">Review all your shows</button>' : ''}
            <button class="btn-action primary" id="deck-view-profile-btn">View taste profile</button>
          </div>
        </div>
      </div>`;

    if ($("#deck-review-all-btn")) {
      $("#deck-review-all-btn").onclick = () => setReviewFilter("all");
    }
    if ($("#deck-view-profile-btn")) {
      $("#deck-view-profile-btn").onclick = () => $('[data-tab="profile"]').click();
    }
    updateActiveTierButton(null);
    return;
  }

  const show = reviewQueue[reviewIndex];
  const { main, sub } = displayTitles(show);
  const scoreVal = show.score != null ? Number(show.score).toFixed(1) : null;
  const tierBadge = show.tier ? `<span class="tier-pill tier-${show.tier.toLowerCase()}">${show.tier}</span>` : "";

  const posterHtml = show.poster
    ? `<img src="${esc(show.poster)}" alt="${esc(main)}" onerror="this.style.display='none'; this.nextElementSibling.classList.add('show');">
       <div class="poster-fallback" aria-hidden="true">${esc(main[0] || "?")}</div>`
    : `<div class="poster-fallback show" aria-hidden="true">${esc(main[0] || "?")}</div>`;

  const metaItems = [];
  if (show.format) metaItems.push(esc(show.format.toUpperCase()));
  if (show.year) metaItems.push(show.year);
  if (show.studios && show.studios.length) metaItems.push(`Studio: <b>${esc(show.studios.slice(0, 2).join(", "))}</b>`);
  if (scoreVal) metaItems.push(`★ ${scoreVal}`);

  const tagsHtml = (show.tags || []).slice(0, 5).map(t => `<span class="chip">${esc(t)}</span>`).join("");

  wrap.innerHTML = `
    <div class="deck-card">
      <div class="deck-poster-wrap poster-box">
        ${posterHtml}
      </div>
      <div class="deck-info">
        <div class="deck-meta-top">
          <span>${show.source === "library" ? "Local library" : "Watched"}</span>
          <div style="display:flex;align-items:center;gap:6px;">
            ${tierBadge}
            <span style="font-size:11.5px;color:var(--muted);">${reviewIndex + 1} / ${reviewQueue.length}</span>
          </div>
        </div>
        <h3 class="deck-title">${esc(main)}</h3>
        ${sub ? `<div class="deck-sub">${esc(sub)}</div>` : ""}
        <div class="deck-meta-details">${metaItems.join(" · ")}</div>
        <div class="deck-synopsis">${formatOverview(show.overview)}</div>
        ${tagsHtml ? `<div class="deck-tags">${tagsHtml}</div>` : ""}
        <div class="deck-bottom-actions">
          <button class="btn-action" id="deck-card-details">Details</button>
        </div>
      </div>
    </div>`;

  $("#deck-card-details").onclick = () => openModal(show);
  updateActiveTierButton(show.tier);
}

async function rateReviewShow(tier) {
  if (!reviewQueue.length || reviewIndex >= reviewQueue.length) return;
  const show = reviewQueue[reviewIndex];
  const prevTier = show.tier || null;

  reviewUndoStack.push({ show, prevTier });
  const wasUnrated = !prevTier;
  show.tier = tier;

  if (wasUnrated) totalRatedCount++;

  const t = titles.find(x => x.id === show.id);
  if (t) t.tier = tier;

  try {
    await apiWrite("/api/weights", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: show.id, tier })
    });
  } catch (e) {
    console.error("Failed to rate review show", e);
  }

  reviewIndex++;
  updateDeckProgress();
  renderDeckCard();
}

async function undoReview() {
  if (!reviewUndoStack.length) return;
  const last = reviewUndoStack.pop();
  const show = last.show;
  const wasRated = !!show.tier;
  const revertedToUnrated = !last.prevTier;

  show.tier = last.prevTier;
  if (wasRated && revertedToUnrated && totalRatedCount > 0) totalRatedCount--;

  const t = titles.find(x => x.id === show.id);
  if (t) t.tier = last.prevTier;

  try {
    if (last.prevTier) {
      await apiWrite("/api/weights", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: show.id, tier: last.prevTier })
      });
    } else {
      await apiWrite(`/api/weights?id=${encodeURIComponent(show.id)}`, { method: "DELETE" });
    }
  } catch (e) {
    console.error("Failed to undo review show", e);
  }

  if (reviewIndex > 0) reviewIndex--;
  updateDeckProgress();
  renderDeckCard();
}

function skipReview() {
  if (reviewIndex < reviewQueue.length) {
    reviewIndex++;
    updateDeckProgress();
    renderDeckCard();
  }
}

function setReviewFilter(filter) {
  reviewFilter = filter;
  $("#deck-filter-unrated").classList.toggle("active", filter === "unrated");
  $("#deck-filter-all").classList.toggle("active", filter === "all");
  loadReviewQueue();
}

function initReviewDeck() {
  $("#deck-filter-unrated").onclick = () => setReviewFilter("unrated");
  $("#deck-filter-all").onclick = () => setReviewFilter("all");

  document.querySelectorAll(".btn-tier").forEach((btn) => {
    btn.onclick = () => {
      const tier = btn.dataset.tier;
      rateReviewShow(tier);
    };
  });

  $("#deck-undo").onclick = () => undoReview();
  $("#deck-skip").onclick = () => skipReview();

  document.addEventListener("keydown", (e) => {
    if ($("#tab-review").hidden) return;
    if ($("#detail-modal").open) return;
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA") return;

    const key = e.key.toUpperCase();
    const code = e.code || "";
    if (key === "1" || code === "Digit1" || code === "Numpad1" || key === "D") {
      e.preventDefault();
      rateReviewShow("D");
    } else if (key === "2" || code === "Digit2" || code === "Numpad2" || key === "C") {
      e.preventDefault();
      rateReviewShow("C");
    } else if (key === "3" || code === "Digit3" || code === "Numpad3" || key === "B") {
      e.preventDefault();
      rateReviewShow("B");
    } else if (key === "4" || code === "Digit4" || code === "Numpad4" || key === "A") {
      e.preventDefault();
      rateReviewShow("A");
    } else if (key === "5" || code === "Digit5" || code === "Numpad5" || key === "S") {
      e.preventDefault();
      rateReviewShow("S");
    } else if (e.key === "Backspace" || e.key === "ArrowLeft") {
      e.preventDefault();
      undoReview();
    } else if (e.key === " " || e.key === "ArrowRight") {
      e.preventDefault();
      skipReview();
    }
  });
}

let ratedShows = [];
// The shows that the user marked as watched and that are not in the library
let manualShows = [];
// The shows that the user removed from the recommendations
let dismissedShows = [];
let ratingsSource = "rated";
let ratingsTierFilter = "all";
let ratingsSort = "tier";

async function loadRatings() {
  try {
    const [res, manual, dismissed] = await Promise.all([
      fetch("/api/ratings").then((r) => r.json()),
      fetch("/api/watched").then((r) => r.json()),
      fetch("/api/dismissed").then((r) => r.json()),
    ]);
    if (!Array.isArray(res)) return;
    ratedShows = res;
    manualShows = Array.isArray(manual) ? manual : [];
    dismissedShows = Array.isArray(dismissed) ? dismissed : [];
    if ($("#count-manual")) $("#count-manual").textContent = manualShows.length;
    if ($("#count-dismissed")) $("#count-dismissed").textContent = dismissedShows.length;

    const counts = { S: 0, A: 0, B: 0, C: 0, D: 0 };
    ratedShows.forEach((s) => {
      if (s.tier && counts[s.tier] !== undefined) counts[s.tier]++;
    });

    const badge = $("#ratings-count-badge");
    if (badge) badge.textContent = `${ratedShows.length} ${ratedShows.length === 1 ? "show" : "shows"}`;

    if ($("#count-tier-s")) $("#count-tier-s").textContent = counts.S;
    if ($("#count-tier-a")) $("#count-tier-a").textContent = counts.A;
    if ($("#count-tier-b")) $("#count-tier-b").textContent = counts.B;
    if ($("#count-tier-c")) $("#count-tier-c").textContent = counts.C;
    if ($("#count-tier-d")) $("#count-tier-d").textContent = counts.D;

    document.querySelectorAll("#ratings-tier-pills .pill").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.tier === ratingsTierFilter);
    });

    renderRatingsGrid();
  } catch (e) {
    console.error("Failed to load ratings", e);
  }
}

function renderRatingsGrid() {
  const box = $("#ratings-grid");
  if (!box) return;
  box.innerHTML = "";

  const source = ratingsSource === "manual" ? manualShows
    : ratingsSource === "dismissed" ? dismissedShows : ratedShows;
  let filtered = source.filter((r) => {
    if (ratingsTierFilter === "all") return true;
    return r.tier === ratingsTierFilter;
  });

  const tierOrder = { S: 0, A: 1, B: 2, C: 3, D: 4 };
  filtered.sort((a, b) => {
    if (ratingsSort === "tier") {
      const diff = (tierOrder[a.tier] ?? 99) - (tierOrder[b.tier] ?? 99);
      if (diff !== 0) return diff;
      return (b.similarity ?? 0) - (a.similarity ?? 0);
    } else if (ratingsSort === "match") {
      return (b.similarity ?? 0) - (a.similarity ?? 0);
    } else if (ratingsSort === "score") {
      return (b.score ?? 0) - (a.score ?? 0);
    } else if (ratingsSort === "title") {
      const aTitle = displayTitles(a).main;
      const bTitle = displayTitles(b).main;
      return aTitle.localeCompare(bTitle);
    }
    return 0;
  });

  if (!filtered.length) {
    if (ratingsSource === "dismissed" && ratingsTierFilter === "all") {
      box.innerHTML = `<p style="grid-column:1/-1;color:var(--muted);text-align:center;padding:48px 20px;">No removed recommendations. In the Recommendations tab, click ✕ on a show that you do not want.</p>`;
    } else if (ratingsSource === "manual" && ratingsTierFilter === "all") {
      box.innerHTML = `<p style="grid-column:1/-1;color:var(--muted);text-align:center;padding:48px 20px;">No manually added shows yet. When you watch a show outside your local library, find it and click "+ Add to Watched".</p>`;
    } else if (!ratedShows.length) {
      box.innerHTML = `
        <div style="grid-column:1/-1;text-align:center;padding:48px 20px;color:var(--muted);">
          <div style="font-size:32px;margin-bottom:8px;">★</div>
          <h3 style="font-family:var(--serif);font-size:18px;margin:0 0 6px;color:var(--text);">No ratings yet</h3>
          <p style="font-size:13.5px;margin:0 0 16px;">Head over to the Review deck or click any show to assign a tier.</p>
          <button class="btn-action primary" id="ratings-go-review">Go to Review →</button>
        </div>`;
      const btn = $("#ratings-go-review");
      if (btn) btn.onclick = () => $('[data-tab="review"]').click();
    } else {
      box.innerHTML = `<p style="grid-column:1/-1;color:var(--muted);text-align:center;padding:40px 0;">No shows rated in Tier ${esc(ratingsTierFilter)}.</p>`;
    }
    return;
  }

  filtered.forEach((r) => box.appendChild(card(r)));
}

function initRatingsControls() {
  const tPills = $("#ratings-tier-pills");
  if (tPills) {
    tPills.querySelectorAll(".pill").forEach((btn) => {
      btn.onclick = () => {
        ratingsTierFilter = btn.dataset.tier;
        tPills.querySelectorAll(".pill").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        renderRatingsGrid();
      };
    });
  }

  const srcPills = $("#ratings-source-pills");
  if (srcPills) {
    srcPills.querySelectorAll(".pill").forEach((btn) => {
      btn.onclick = () => {
        ratingsSource = btn.dataset.source;
        srcPills.querySelectorAll(".pill").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        renderRatingsGrid();
      };
    });
  }

  const sPills = $("#ratings-sort-pills");
  if (sPills) {
    sPills.querySelectorAll(".pill").forEach((btn) => {
      btn.onclick = () => {
        ratingsSort = btn.dataset.sort;
        sPills.querySelectorAll(".pill").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        renderRatingsGrid();
      };
    });
  }
}

document.querySelectorAll("nav button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll("nav button").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    for (const s of document.querySelectorAll("main section")) s.hidden = true;
    $(`#tab-${b.dataset.tab}`).hidden = false;
    if (b.dataset.tab === "review") loadReviewQueue();
    if (b.dataset.tab === "ratings") loadRatings();
    if (b.dataset.tab === "recs") recs();
    if (b.dataset.tab === "profile") profile();
  };
});

// ---- Settings
// Each setting is a choice between options. The first option is the default. The value of a
// setting is an attribute of the root element (data-<key>), so that the style sheet can use it.
// The browser keeps the values. To add a setting: add an entry to this list, and add its rules to
// the style sheet. A setting that needs more than style rules has an `apply` function.
const SETTINGS_KEY = "rinrikun-settings";
const SETTINGS = [
  {
    key: "font",
    title: "Typeface",
    options: [
      { value: "mixed", label: "Serif titles", text: "Titles and headings use Noto Serif JP. The other text uses Noto Sans JP." },
      { value: "sans", label: "Noto Sans JP everywhere", text: "All text uses Noto Sans JP." },
    ],
    apply: applyFontSetting,
  },
];
const settings = {};

// The page loads Noto Sans JP in the weights 400, 500 and 700. Titles and headings have the weight
// 600, thus "Noto Sans JP everywhere" also needs this weight. The style sheet for it is in the page
// head and is off for "Serif titles", so that the look of "Serif titles" stays the same as before.
function applyFontSetting(value) {
  const link = document.getElementById("font-sans-600");
  if (link) link.disabled = value !== "sans";
  // The maps draw their text on a canvas. Draw them again when the typeface is ready.
  const redraw = () => activeVectorMaps.forEach((ctrl) => ctrl.scheduleDraw());
  redraw();
  if (value === "sans" && document.fonts && document.fonts.load) {
    document.fonts.load('600 12px "Noto Sans JP"').then(redraw, () => {});
  }
}

function applySetting(setting) {
  document.documentElement.dataset[setting.key] = settings[setting.key];
  if (setting.apply) setting.apply(settings[setting.key]);
}

function setSetting(key, value) {
  const setting = SETTINGS.find((x) => x.key === key);
  if (!setting || !setting.options.some((o) => o.value === value)) return;
  settings[key] = value;
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings)); } catch (e) {}
  applySetting(setting);
  renderSettings();
}

function renderSettings() {
  const list = $("#settings-list");
  if (!list) return;
  list.innerHTML = SETTINGS.map((setting) => {
    const current = setting.options.find((o) => o.value === settings[setting.key]);
    const pills = setting.options.map((o) => `
          <button class="pill ${o === current ? "active" : ""}" data-key="${setting.key}" data-value="${o.value}" aria-pressed="${o === current}">${esc(o.label)}</button>`).join("");
    return `
      <div class="setting-row" data-setting="${setting.key}">
        <div class="setting-info">
          <div class="setting-title">${esc(setting.title)}</div>
          <div class="setting-text">${esc(current.text)}</div>
        </div>
        <div class="filter-pills setting-options" role="group" aria-label="${esc(setting.title)}">${pills}
        </div>
      </div>`;
  }).join("");
  list.querySelectorAll(".pill").forEach((btn) => {
    btn.onclick = () => setSetting(btn.dataset.key, btn.dataset.value);
  });
}

function initSettings() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}") || {}; } catch (e) {}
  SETTINGS.forEach((setting) => {
    const known = setting.options.some((o) => o.value === saved[setting.key]);
    settings[setting.key] = known ? saved[setting.key] : setting.options[0].value;
    applySetting(setting);
  });
  renderSettings();
}

initSettings();
profile();
initSearch();
initRecsFilters();
initReviewDeck();
initRatingsControls();

const THEME_KEY = "rinrikun-theme";
const SUN = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
const MOON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';

function effectiveTheme() {
  return document.documentElement.dataset.theme ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}
function paintTheme() {
  $("#theme").innerHTML = effectiveTheme() === "dark" ? SUN : MOON;
}
$("#theme").onclick = () => {
  const next = effectiveTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
  paintTheme();
  activeVectorMaps.forEach((ctrl) => ctrl.draw?.());
};
paintTheme();
