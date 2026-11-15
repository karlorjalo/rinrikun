const $ = (s) => document.querySelector(s);
const esc = (s) => (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function card(r, why) {
  const d = document.createElement("div");
  d.className = "card";

  const showNative = r.title_native && r.title_native.trim().toLowerCase() !== (r.title || "").trim().toLowerCase();
  const metaParts = [];
  if (showNative) metaParts.push(esc(r.title_native));
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
  } else if (r.shared_tags && r.shared_tags.length) {
    tagHtml = r.shared_tags.slice(0, 3).map((t) => `<span class="chip chip-shared" title="Shared tag">${esc(t)}</span>`).join("");
  } else if (r.tags && r.tags.length) {
    tagHtml = r.tags.slice(0, 3).map((t) => `<span class="chip">${esc(t)}</span>`).join("");
  }

  const posterHtml = r.poster
    ? `<img src="${esc(r.poster)}" loading="lazy" alt="${esc(r.title)}" onerror="this.style.display='none'; this.nextElementSibling.classList.add('show');">
       <div class="poster-fallback" aria-hidden="true">${esc((r.title || "?")[0])}</div>`
    : `<div class="poster-fallback show" aria-hidden="true">${esc((r.title || "?")[0])}</div>`;

  d.innerHTML = `
    <div class="poster-box">
      ${posterHtml}
    </div>
    <div class="card-content">
      <div class="t">${esc(r.title)} ${r.owned ? '<span class="badge">owned</span>' : ""}</div>
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
  const showNative = r.title_native && r.title_native.trim().toLowerCase() !== (r.title || "").trim().toLowerCase();
  const simVal = r.similarity != null ? Math.round(r.similarity) : null;
  const scoreVal = r.score != null ? Number(r.score).toFixed(1) : null;

  const posterHtml = r.poster
    ? `<img src="${esc(r.poster)}" loading="lazy" alt="${esc(r.title)}" onerror="this.style.display='none'; this.nextElementSibling.classList.add('show');">
       <div class="poster-fallback" aria-hidden="true">${esc((r.title || "?")[0])}</div>`
    : `<div class="poster-fallback show" aria-hidden="true">${esc((r.title || "?")[0])}</div>`;

  const metaItems = [];
  metaItems.push(r.owned ? '<span class="badge">owned</span>' : '<span class="badge badge-unowned">in pool</span>');
  if (r.format) metaItems.push(`<span>${esc(r.format.toUpperCase())}</span>`);
  if (r.year) metaItems.push(`<span>${r.year}</span>`);
  if (r.genres && r.genres.length) metaItems.push(`<span>${esc(r.genres.slice(0, 3).join(", "))}</span>`);

  const statItems = [];
  if (scoreVal) statItems.push(`<span class="score">★ ${scoreVal}</span>`);
  if (simVal != null) statItems.push(`<span class="affinity">${simVal}% taste match</span>`);

  const tags = (r.tags || []).map((t, idx) => {
    const rank = r.tag_ranks && r.tag_ranks[idx] ? `<span class="trank">${r.tag_ranks[idx]}%</span>` : "";
    return `<span class="modal-tag">${esc(t)}${rank}</span>`;
  }).join("");

  const anilistLink = r.anilist_id
    ? `<a href="https://anilist.co/anime/${r.anilist_id}" target="_blank" rel="noopener noreferrer" class="btn-action">AniList ↗</a>`
    : "";

  modal.innerHTML = `
    <div class="modal-inner">
      <button class="modal-close" onclick="closeModal()" aria-label="Close dialog">✕</button>
      <div class="modal-head">
        <div class="modal-poster poster-box">${posterHtml}</div>
        <div class="modal-info">
          <div class="modal-meta-row">${metaItems.join(" · ")}</div>
          <h3 class="modal-title">${esc(r.title)}</h3>
          ${showNative ? `<div class="modal-native">${esc(r.title_native)}</div>` : ""}
          ${r.studios && r.studios.length ? `<div class="modal-studio">Studio: <b>${esc(r.studios.join(", "))}</b></div>` : ""}
          <div class="modal-score-row">${statItems.join(" · ")}</div>
          <div class="modal-actions">
            <button class="btn-action primary" id="modal-find-sim">Find Similar</button>
            <button class="btn-action" id="modal-seed-rec">Recommend Like This</button>
            ${anilistLink}
          </div>
        </div>
      </div>
      <div class="modal-body">
        <h4>Synopsis</h4>
        <div class="modal-overview">${formatOverview(r.overview)}</div>
        ${tags ? `<h4>Tags & Themes</h4><div class="modal-tags">${tags}</div>` : ""}
      </div>
    </div>`;

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

function closeModal() {
  const m = $("#detail-modal");
  if (m.open) m.close();
}

$("#detail-modal").onclick = (e) => {
  if (e.target === $("#detail-modal")) closeModal();
};

let activeProfileTag = null;
let profileData = null;

async function profile() {
  profileData = await (await fetch("/api/profile")).json();
  renderProfile();
}

function renderProfile() {
  const p = profileData;
  const el = $("#tab-profile");
  if (!p) return;

  const topGenre = (p.genre_summary && p.genre_summary[0]) ? p.genre_summary[0][0] : "Anime";
  const topEra = (p.era_summary && p.era_summary[0]) ? p.era_summary[0][0] : "Modern";

  let displayedShows = p.defining_shows;
  if (activeProfileTag) {
    displayedShows = p.defining_shows.filter((r) =>
      (r.tags || []).concat(r.genres || []).map((x) => x.toLowerCase()).includes(activeProfileTag.toLowerCase())
    );
  }

  el.innerHTML = `
    <div class="hero-dna">
      <div class="hero-dna-top">
        <div class="hero-dna-title-wrap">
          <div class="hero-dna-tagline">Taste DNA & Collection Map</div>
          <h2 class="hero-dna-title">Personal Anime Profile</h2>
          <p class="hero-dna-desc">Centroid computed from your <b>${p.owned_count}</b> library titles, embedded into the <b>${p.total_count.toLocaleString()}</b> anime vector universe.</p>
        </div>
        <div class="hero-stats-grid">
          <div class="hero-stat-card">
            <div class="hero-stat-val">${p.owned_count}</div>
            <div class="hero-stat-lbl">Owned Shows</div>
          </div>
          <div class="hero-stat-card">
            <div class="hero-stat-val">${p.total_count.toLocaleString()}</div>
            <div class="hero-stat-lbl">Mapped Pool</div>
          </div>
          <div class="hero-stat-card">
            <div class="hero-stat-val">${esc(topEra)}</div>
            <div class="hero-stat-lbl">Dominant Era</div>
          </div>
          <div class="hero-stat-card">
            <div class="hero-stat-val">${esc(topGenre)}</div>
            <div class="hero-stat-lbl">Top Genre</div>
          </div>
        </div>
      </div>

      <div class="dna-section-title">Dominant Thematic Tags <span style="font-size:12px;color:var(--muted);font-weight:normal;">Click a tag to filter defining shows</span></div>
      <div class="tagbar" id="profile-tagbar">
        ${p.tag_summary.map(([t, c]) => `
          <button class="chip-interactive ${activeProfileTag === t ? 'active' : ''}" data-tag="${esc(t)}">
            ${esc(t)} <b>${c}</b>
          </button>
        `).join("")}
      </div>

      ${p.genre_summary && p.genre_summary.length ? `
        <div class="dna-section-title" style="margin-top:16px;">Top Genres</div>
        <div class="tagbar" id="profile-genrebar">
          ${p.genre_summary.map(([g, c]) => `
            <button class="chip-interactive ${activeProfileTag === g ? 'active' : ''}" data-tag="${esc(g)}">
              ${esc(g)} <b>${c}</b>
            </button>
          `).join("")}
        </div>
      ` : ""}
    </div>

    ${activeProfileTag ? `
      <div class="active-filter-bar">
        <span>Filtered by: <b>${esc(activeProfileTag)}</b> (${displayedShows.length} of ${p.defining_shows.length} defining shows match)</span>
        <button id="clear-profile-filter">Clear filter ✕</button>
      </div>
    ` : ""}

    <div class="defining-header-wrap">
      <h2>Defining Shows</h2>
      <div class="defining-desc">Titles mathematically nearest to your taste center. These anchor your personal collection's identity.</div>
    </div>
    <div class="cards" id="profile-cards"></div>
  `;

  el.querySelectorAll(".chip-interactive").forEach((btn) => {
    btn.onclick = () => {
      const tag = btn.dataset.tag;
      activeProfileTag = (activeProfileTag === tag) ? null : tag;
      renderProfile();
    };
  });

  const clearBtn = $("#clear-profile-filter");
  if (clearBtn) {
    clearBtn.onclick = () => {
      activeProfileTag = null;
      renderProfile();
    };
  }

  const cardsContainer = $("#profile-cards");
  if (!displayedShows.length) {
    cardsContainer.innerHTML = `<p style="grid-column:1/-1;color:var(--muted);text-align:center;padding:30px 0;">No defining shows contain the tag "${esc(activeProfileTag)}". Try another tag!</p>`;
  } else {
    displayedShows.forEach((r) => cardsContainer.appendChild(card(r, `${r.similarity}% to center`)));
  }
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
  const ownedSample = titles.filter((t) => t.owned && t.title);
  const shuffled = ownedSample.sort(() => 0.5 - Math.random()).slice(0, 5);
  const suggBox = $("#similar-suggestions");
  if (suggBox) {
    suggBox.innerHTML = shuffled.map((t) => `<button class="suggestion-chip">${esc(t.title)}</button>`).join("");
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

      const showNative = t.title_native && t.title_native.trim().toLowerCase() !== (t.title || "").trim().toLowerCase();
      const sub = [showNative ? esc(t.title_native) : null, t.year || null, t.owned ? "owned" : null].filter(Boolean).join(" · ");

      const thumbHtml = t.poster
        ? `<img src="${esc(t.poster)}" alt="" loading="lazy" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
           <div class="qitem-fallback" style="display:none;">${esc((t.title || "?")[0])}</div>`
        : `<div class="qitem-fallback">${esc((t.title || "?")[0])}</div>`;

      item.innerHTML = `
        <div class="qitem-thumb">${thumbHtml}</div>
        <div class="qitem-info">
          <div class="qitem-title">${esc(t.title)} ${t.owned ? '<span class="badge">owned</span>' : ""}</div>
          ${sub ? `<div class="qitem-sub">${sub}</div>` : ""}
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

async function runSimilar(t) {
  currentSimilarShow = t;
  $("#qlist").hidden = true;
  $("#q").value = t.title;
  $("#q-clear").hidden = false;

  const empty = $("#similar-empty");
  if (empty) empty.hidden = true;

  const header = $("#similar-header");
  if (header) {
    header.hidden = false;
    header.innerHTML = `
      <div class="result-seed-bar">
        <div class="seed-info">
          <div class="seed-label">Showing nearest neighbors for</div>
          <h3 class="seed-title">${esc(t.title)} ${t.owned ? '<span class="badge">owned</span>' : ""}</h3>
        </div>
        <div class="seed-actions">
          <button class="btn-action" id="sim-view-details">Show Details</button>
        </div>
      </div>`;
    $("#sim-view-details").onclick = () => openModal(t);
  }

  const res = await (await fetch(`/api/similar?id=${encodeURIComponent(t.id)}`)).json();
  const box = $("#sresults");
  box.innerHTML = "";
  res.forEach((r) => box.appendChild(card(r)));
}

let seed = null;
function useSeed(r) {
  seed = r;
  $("#seedlabel").textContent = `seeding from: ${r.title}`;
  document.querySelector('[data-tab="recs"]').click();
}

async function recs() {
  const url = seed ? `/api/recommend?seed=${encodeURIComponent(seed.id)}` : "/api/recommend";
  const res = await (await fetch(url)).json();
  const box = $("#rresults");
  box.innerHTML = "";
  res.forEach((r) => box.appendChild(card(r)));
}

document.querySelectorAll("nav button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll("nav button").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    for (const s of document.querySelectorAll("main section")) s.hidden = true;
    $(`#tab-${b.dataset.tab}`).hidden = false;
    if (b.dataset.tab === "recs") recs();
  };
});
$("#recenter").onclick = () => { seed = null; $("#seedlabel").textContent = ""; recs(); };

profile();
initSearch();

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
};
paintTheme();
