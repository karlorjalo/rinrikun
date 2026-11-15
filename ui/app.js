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
         ${r.manual_watched ? '✓ Watched · Remove' : '+ Add to Watched'}
       </button>`;

  const tierOptions = [
    { t: "S", w: "2.0×" },
    { t: "A", w: "1.5×" },
    { t: "B", w: "1.0×" },
    { t: "C", w: "0.3×" },
    { t: "D", w: "0.0×" },
  ];
  const tierPills = tierOptions.map(({ t, w }) => {
    const active = r.tier === t ? "active" : "";
    return `<button class="btn-modal-tier tier-${t.toLowerCase()} ${active}" data-tier="${t}">${t} ${w}</button>`;
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
    await fetch("/api/watched", {
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
    if (!$("#tab-watched").hidden) {
      watched();
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
    await fetch("/api/weights", {
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
  } catch (e) {
    console.error("Failed to set tier", e);
  }
}

async function clearTier(r) {
  try {
    await fetch(`/api/weights?id=${encodeURIComponent(r.id)}`, { method: "DELETE" });
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
          <h2 class="hero-dna-title">Taste profile</h2>
        </div>
        <div class="hero-stats-grid">
          <div class="hero-stat-card">
            <div class="hero-stat-val">${p.owned_count}</div>
            <div class="hero-stat-lbl">Owned</div>
          </div>
          <div class="hero-stat-card">
            <div class="hero-stat-val">${p.total_count.toLocaleString()}</div>
            <div class="hero-stat-lbl">Indexed</div>
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

      <div class="dna-section-title">Dominant tags</div>
      <div class="tagbar" id="profile-tagbar">
        ${p.tag_summary.map(([t, c]) => `
          <button class="chip-interactive ${activeProfileTag === t ? 'active' : ''}" data-tag="${esc(t)}">
            ${esc(t)} <b>${c}</b>
          </button>
        `).join("")}
      </div>

      ${p.genre_summary && p.genre_summary.length ? `
        <div class="dna-section-title" style="margin-top:16px;">Genres</div>
        <div class="tagbar" id="profile-genrebar">
          ${p.genre_summary.map(([g, c]) => `
            <button class="chip-interactive ${activeProfileTag === g ? 'active' : ''}" data-tag="${esc(g)}">
              ${esc(g)} <b>${c}</b>
            </button>
          `).join("")}
        </div>
      ` : ""}

      ${p.tier_summary ? `
        <div class="tier-summary-box">
          <div class="tier-summary-title">
            <span>Preference distribution</span>
            <span style="font-weight:400;color:var(--muted);font-size:12px;">S 2.0× · A 1.5× · B 1.0× · C 0.3× · D 0.0×</span>
          </div>
          <div class="tier-summary-row">
            <div class="tier-summary-item"><span class="tier-pill tier-s">S</span> <span class="tier-summary-count">${p.tier_summary.S || 0}</span></div>
            <div class="tier-summary-item"><span class="tier-pill tier-a">A</span> <span class="tier-summary-count">${p.tier_summary.A || 0}</span></div>
            <div class="tier-summary-item"><span class="tier-pill tier-b">B</span> <span class="tier-summary-count">${p.tier_summary.B || 0}</span></div>
            <div class="tier-summary-item"><span class="tier-pill tier-c">C</span> <span class="tier-summary-count">${p.tier_summary.C || 0}</span></div>
            <div class="tier-summary-item"><span class="tier-pill tier-d">D</span> <span class="tier-summary-count">${p.tier_summary.D || 0}</span></div>
            <div class="tier-summary-item" style="color:var(--muted);"><span style="font-size:11.5px;">Unrated:</span> <span class="tier-summary-count">${p.tier_summary.unrated || 0}</span></div>
          </div>
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
      <h2>Defining shows</h2>
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

async function runSimilar(t) {
  currentSimilarShow = t;
  const { main } = displayTitles(t);
  $("#qlist").hidden = true;
  $("#q").value = main;
  $("#q-clear").hidden = false;

  const empty = $("#similar-empty");
  if (empty) empty.hidden = true;

  const header = $("#similar-header");
  if (header) {
    header.hidden = false;
    const simBadge = t.manual_watched ? '<span class="badge badge-manual">watched</span>' : (t.owned ? '<span class="badge">owned</span>' : "");
    header.innerHTML = `
      <div class="result-seed-bar">
        <div class="seed-info">
          <h3 class="seed-title">${esc(main)} ${simBadge}</h3>
        </div>
        <div class="seed-actions">
          <button class="btn-action" id="sim-view-details">Details</button>
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
let rawRecs = [];
let recsFormatFilter = "all";
let recsMinScore = 0;

function useSeed(r) {
  seed = r;
  document.querySelector('[data-tab="recs"]').click();
}

function renderRecsSeedBar() {
  const bar = $("#recs-seed-bar");
  if (!bar) return;
  if (seed) {
    const { main } = displayTitles(seed);
    bar.innerHTML = `
      <div class="recs-seed-card">
        <div class="recs-seed-left">
          <span class="seed-badge">Seed</span>
          <span class="seed-text"><b>${esc(main)}</b></span>
        </div>
        <button id="recenter-btn" class="btn-action">Reset to center ↺</button>
      </div>`;
    $("#recenter-btn").onclick = () => {
      seed = null;
      recs();
    };
  } else {
    bar.innerHTML = "";
  }
}

function initRecsFilters() {
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

  filtered.forEach((r) => box.appendChild(card(r)));
}

async function recs() {
  renderRecsSeedBar();
  const url = seed ? `/api/recommend?k=40&seed=${encodeURIComponent(seed.id)}` : "/api/recommend?k=40";
  rawRecs = await (await fetch(url)).json();
  renderRecsGrid();
}

async function watched() {
  const list = await (await fetch("/api/watched")).json();
  const badge = $("#watched-count-badge");
  if (badge) badge.textContent = `${list.length} ${list.length === 1 ? "show" : "shows"}`;
  const box = $("#wresults");
  box.innerHTML = "";
  if (!list.length) {
    box.innerHTML = `<p style="grid-column:1/-1;color:var(--muted);text-align:center;padding:48px 20px;">No manually added shows yet. When you watch a show outside your local library, find it and click "+ Add to Watched".</p>`;
    return;
  }
  list.forEach((r) => {
    box.appendChild(card(r, "manually added"));
  });
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
            ${reviewFilter === "unrated" ? "You have reviewed all unrated watched shows." : "You have reached the end of the review queue."}
          </p>
          <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;">
            ${reviewFilter === "unrated" ? '<button class="btn-action" id="deck-review-all-btn">Review all watched</button>' : ''}
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
    await fetch("/api/weights", {
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
      await fetch("/api/weights", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: show.id, tier: last.prevTier })
      });
    } else {
      await fetch(`/api/weights?id=${encodeURIComponent(show.id)}`, { method: "DELETE" });
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
    if (key === "1" || key === "S") {
      e.preventDefault();
      rateReviewShow("S");
    } else if (key === "2" || key === "A") {
      e.preventDefault();
      rateReviewShow("A");
    } else if (key === "3" || key === "B") {
      e.preventDefault();
      rateReviewShow("B");
    } else if (key === "4" || key === "C") {
      e.preventDefault();
      rateReviewShow("C");
    } else if (key === "5" || key === "D") {
      e.preventDefault();
      rateReviewShow("D");
    } else if (e.key === "Backspace" || e.key === "ArrowLeft") {
      e.preventDefault();
      undoReview();
    } else if (e.key === " " || e.key === "ArrowRight") {
      e.preventDefault();
      skipReview();
    }
  });
}

document.querySelectorAll("nav button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll("nav button").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
    for (const s of document.querySelectorAll("main section")) s.hidden = true;
    $(`#tab-${b.dataset.tab}`).hidden = false;
    if (b.dataset.tab === "review") loadReviewQueue();
    if (b.dataset.tab === "recs") recs();
    if (b.dataset.tab === "watched") watched();
    if (b.dataset.tab === "profile") profile();
  };
});

profile();
initSearch();
initRecsFilters();
initReviewDeck();

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
