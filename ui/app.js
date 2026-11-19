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
  if (matchHtml(r)) statParts.push(matchHtml(r));
  if (guessHtml(r)) statParts.push(guessHtml(r));
  if (similarHtml(r)) statParts.push(similarHtml(r));
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
      ${simVal != null ? `<div class="simbar" title="${simVal}% similar to the seed show"><i style="width:${Math.max(0, Math.min(100, simVal))}%"></i></div>` : ""}
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

// ---- Tooltips
// An element with the attribute data-tip shows its text in a small box, at once, when the pointer
// is on it, when it has the focus, or when the user taps it. The tooltip of the browser (the title
// attribute) appears late, and it does not appear on a touch screen.
//
// An element with the attribute data-tip-rich shows a box with more than text, for example with
// pictures. The attribute is a key of TIP_CONTENT, and the function for the key gets the element
// and returns the HTML of the box. If the element also has the attribute data-tip-pass, it is a
// control: a click on it does the work of the control.
const TIP_CONTENT = {};
const tipBox = document.createElement("div");
tipBox.className = "tip-box";
tipBox.setAttribute("role", "tooltip");
tipBox.hidden = true;
let tipTarget = null;

function tipElement(node) {
  return node && node.closest ? node.closest("[data-tip], [data-tip-rich]") : null;
}

// A small "i" in a circle that shows a text when the pointer is on it
function infoDot(text, label = "More about these numbers") {
  return `<button type="button" class="info-dot" data-tip="${esc(text)}" aria-label="${esc(label)}">i</button>`;
}

// The time at which the box of the element appeared
let tipShownAt = 0;

function showTip(el) {
  if (tipTarget !== el || tipBox.hidden) tipShownAt = performance.now();
  tipTarget = el;
  const make = TIP_CONTENT[el.dataset.tipRich];
  tipBox.classList.toggle("tip-rich", !!make);
  if (make) tipBox.innerHTML = make(el);
  else tipBox.textContent = el.dataset.tip || "";
  // An open dialog is above all other parts of the page. The box must be in the dialog, or the
  // dialog covers it.
  const home = el.closest("dialog[open]") || document.body;
  if (tipBox.parentElement !== home) home.appendChild(tipBox);
  tipBox.hidden = false;
  const rect = el.getBoundingClientRect();
  const width = tipBox.offsetWidth;
  const height = tipBox.offsetHeight;
  // The part of the page that the user sees. On a phone it can be smaller than the window of the
  // page, when a part of the page is wider than the screen.
  const view = window.visualViewport;
  const viewLeft = view ? view.offsetLeft : 0;
  const viewTop = view ? view.offsetTop : 0;
  const viewWidth = view ? view.width : window.innerWidth;
  const viewHeight = view ? view.height : window.innerHeight;
  const left = Math.max(viewLeft + 8, Math.min(viewLeft + viewWidth - width - 8, rect.left + rect.width / 2 - width / 2));
  // Below the element. Above it if there is no space below.
  const top = rect.bottom + 8 + height > viewTop + viewHeight - 8 ? rect.top - height - 8 : rect.bottom + 8;
  tipBox.style.left = `${left}px`;
  tipBox.style.top = `${Math.max(viewTop + 8, top)}px`;
}

function hideTip() {
  tipTarget = null;
  tipBox.hidden = true;
}

document.addEventListener("mouseover", (e) => {
  const el = tipElement(e.target);
  // The pointer can move between the parts of one element: the box stays as it is
  if (el && el === tipTarget && !tipBox.hidden) return;
  if (el) showTip(el);
  else if (tipTarget) hideTip();
});
document.addEventListener("focusin", (e) => {
  const el = tipElement(e.target);
  if (el) showTip(el);
});
document.addEventListener("focusout", hideTip);
// A tap on a touch screen shows the box, and it does not open the show that the element is in
document.addEventListener("click", (e) => {
  const el = tipElement(e.target);
  if (!el) {
    hideTip();
    return;
  }
  // A control with a box does its usual work
  if (el.dataset.tipPass !== undefined) return;
  e.stopPropagation();
  e.preventDefault();
  // A second tap closes the box. The first tap gives the element the focus, which shows the box
  // immediately before this click: that box must stay.
  const fromThisTap = performance.now() - tipShownAt < 500;
  if (tipTarget === el && !tipBox.hidden && e.detail && e.pointerType === "touch" && !fromThisTap) hideTip();
  else showTip(el);
}, true);
window.addEventListener("scroll", hideTip, true);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && tipTarget) hideTip();
});

// The address of a list of recommendations, with the formula of the Recommendations tab
function withFormula(url) {
  return `${url}${url.includes("?") ? "&" : "?"}kinds=${recsKinds}&links=${recsLinks}`;
}

// The match of a show tells how near the show is to the taste of the user. The tier that the tier
// model predicts for the show has a small part in it. The match is the part of the franchises that
// the user does not have, which are less near. It does not use the crowd links or the formula of a
// list. For a show of the user it is the match that the show would have if the user did not have
// its franchise.
function formatMatch(match) {
  if (match == null) return null;
  return match >= 99.95 ? "100" : match >= 99 ? match.toFixed(1) : String(Math.round(match));
}

function matchHtml(r) {
  const text = formatMatch(r.match);
  if (text == null) return "";
  const title = r.owned
    ? `Without this franchise in your list, this show would be nearer to your taste than ${text}% of the franchises that you do not have`
    : `This show is nearer to your taste than ${text}% of the franchises that you do not have`;
  return `<span class="affinity" data-tip="${title}" tabindex="0">${text}% match</span>`;
}

// The tier guess of a show without a tier: the tier that a small model predicts from the tags of
// the rated shows. The guess is weak, and the tooltip says so.
function guessHtml(r) {
  if (!r.tier_guess || r.tier) return "";
  const title = "A guess of the tier that you will give, from the tags of the shows that you rated. " +
    "The guess is weak: in a test, 64% of the shows with the highest guesses were S or A, and 36% of the shows with the lowest guesses.";
  return `<span class="tier-guess" data-tip="${title}" tabindex="0">guess ${r.tier_guess}</span>`;
}

// A list with a seed also has the similarity of each show to the seed
function similarHtml(r) {
  return r.similarity != null ? `<span data-tip="The similarity to the seed show" tabindex="0">${Math.round(r.similarity)}% similar</span>` : "";
}

// Get the match of a show again after a change of a tier or of the watched state
async function refreshMatch(r) {
  try {
    const full = await (await fetch(`/api/show/${encodeURIComponent(r.id)}`)).json();
    r.match = full.match;
    r.tier_guess = full.tier_guess;
  } catch (e) {}
}

// AniList has each cover in a small file (100 pixels wide) and in a larger file. A large picture
// uses the larger file. If the larger file does not load, the picture uses the small file.
function largePoster(url) {
  return url ? url.replace("/cover/small/", "/cover/medium/") : url;
}
const POSTER_ERROR = "if (!this.dataset.retry && this.dataset.small) { this.dataset.retry = '1'; this.src = this.dataset.small; } " +
  "else { this.style.display = 'none'; this.nextElementSibling.classList.add('show'); }";

// The row of the detail window with the crowd score, the match, the tier guess and the similarity
function modalStatsHtml(r) {
  const items = [];
  if (r.score != null) items.push(`<span class="score">★ ${Number(r.score).toFixed(1)}</span>`);
  if (matchHtml(r)) items.push(matchHtml(r));
  if (guessHtml(r)) items.push(guessHtml(r));
  if (similarHtml(r)) items.push(similarHtml(r));
  return items.join(" · ");
}

// A change of a tier in the detail window. The window shows the new tier at once: it does not
// wait for the server. The server needs some time for the new match of the show, thus the match
// comes later, and only its row changes then.
async function changeTierInModal(r, tier) {
  const previous = r.tier || null;
  r.tier = tier;
  openModal(r);
  const ok = tier ? await setTier(r, tier) : await clearTier(r);
  const shown = () => $("#detail-modal").open && currentModalShow && currentModalShow.id === r.id;
  if (!ok) {
    // The server did not save the change: show the tier from before
    r.tier = previous;
    if (shown()) openModal(r);
    return;
  }
  await refreshMatch(r);
  const row = $("#detail-modal .modal-score-row");
  if (shown() && row) row.innerHTML = modalStatsHtml(r);
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
  const scoreVal = r.score != null ? Number(r.score).toFixed(1) : null;

  const posterHtml = r.poster
    ? `<img src="${esc(largePoster(r.poster))}" data-small="${esc(r.poster)}" loading="lazy" alt="${esc(main)}" onerror="${POSTER_ERROR}">
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
    : `<button class="btn-action btn-watched ${r.manual_watched ? 'active' : ''}" id="modal-toggle-watched" aria-pressed="${r.manual_watched ? 'true' : 'false'}">
         ${r.manual_watched ? 'Watched' : '+ Add to Watched'}
       </button>`;

  // A show that the user does not own can go out of the recommendations
  const dismissBtn = r.owned
    ? ""
    : `<button class="btn-action btn-dismiss ${r.dismissed ? 'active' : ''}" id="modal-toggle-dismiss"
         title="${r.dismissed ? 'Put this show back in the recommendations' : 'Remove this show from the recommendations. Shows like it get a lower score.'}">
         ${r.dismissed ? '✕ Not interested · Undo' : '✕ Not interested'}
       </button>`;

  // A show that the user does not own can go on the watch list
  const interestBtn = r.owned
    ? ""
    : `<button class="btn-action btn-interest ${r.interest === 1 ? 'active' : ''}" id="modal-toggle-interest" aria-pressed="${r.interest === 1}"
         title="${r.interest === 1 ? 'Take this show off your watch list' : 'Put this show on your watch list. Shows like it get a higher score.'}">
         ${r.interest === 1 ? '♥ Interested · Undo' : '♥ Interested'}
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
          <div class="modal-score-row">${modalStatsHtml(r)}</div>
          <div class="modal-actions">
            <button class="btn-action primary" id="modal-find-sim">Find Similar</button>
            <button class="btn-action" id="modal-seed-rec">Recommend Like This</button>
            ${watchedBtn}
            ${interestBtn}${dismissBtn}
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
    btn.onclick = () => changeTierInModal(r, btn.dataset.tier);
  });
  if ($("#modal-clear-tier")) {
    $("#modal-clear-tier").onclick = () => changeTierInModal(r, null);
  }

  if ($("#modal-toggle-watched")) {
    $("#modal-toggle-watched").onclick = async () => {
      const next = !r.manual_watched;
      await toggleWatched(r, next);
      await refreshMatch(r);
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

  if ($("#modal-toggle-interest")) {
    $("#modal-toggle-interest").onclick = async () => {
      await setInterest(r, r.interest === 1 ? null : true, "page");
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

// Save a tier on the server. Return true if the server saved it.
async function setTier(r, tier) {
  try {
    const res = await apiWrite("/api/weights", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: r.id, tier: tier })
    });
    if (!res.ok) throw new Error(`the server answered ${res.status}`);
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
      updateRatingsAfterEdit(r);
    }
    return true;
  } catch (e) {
    console.error("Failed to set tier", e);
    return false;
  }
}

// Remove the tier of a show on the server. Return true if the server saved it.
async function clearTier(r) {
  try {
    const res = await apiWrite(`/api/weights?id=${encodeURIComponent(r.id)}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`the server answered ${res.status}`);
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
      updateRatingsAfterEdit(r);
    }
    return true;
  } catch (e) {
    console.error("Failed to clear tier", e);
    return false;
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

// What the user did with the shows that the lists of recommendations gave
let recResults = null;

async function profile() {
  [profileData, recResults, interestResults] = await Promise.all([
    fetch("/api/profile").then((r) => r.json()),
    fetch("/api/rec-log").then((r) => r.json()).catch(() => null),
    fetch("/api/interest/results").then((r) => r.json()).catch(() => null),
  ]);
  renderProfile();
}

// The numbers of the recommendations: the shows that the list gave, and the shows of these that
// the user added later, with their tiers
function renderRecResults() {
  const box = $("#rec-results");
  if (!box) return;
  const res = recResults;
  if (!res || !res.shown) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  const since = new Date(res.since + "T00:00:00").toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "numeric" });
  const tiers = ["S", "A", "B", "C", "D"].filter((t) => res.tiers[t])
    .map((t) => `<span class="tier-summary-item"><span class="tier-pill tier-${t.toLowerCase()}">${t}</span> <span class="tier-summary-count">${res.tiers[t]}</span></span>`);
  if (res.unrated) tiers.push(statItem(res.unrated, "without a tier"));
  // The box has only the numbers. The text is in the tooltip of the "i".
  let about = "The new franchises that the Recommendations tab showed you, and how many of them you added or removed later.";
  // The comparison of the two formulas has a use only after the user saw lists of the two
  const formulas = res.formulas || {};
  if (formulas["no links"] && formulas["no links"].shown && formulas.links) {
    const perFormula = (name, label) => `${label}: ${formulas[name].shown} shown, ${formulas[name].added} added, ${formulas[name].removed} removed.`;
    about += ` ${perFormula("links", "With crowd links")} ${perFormula("no links", "Without crowd links")} A show counts for the first list that gave it.`;
  }
  const shows = res.shows.slice(0, 6).map((show) => {
    const pill = show.tier ? `<span class="tier-pill tier-${show.tier.toLowerCase()}">${show.tier}</span> ` : "";
    return `<span class="rec-results-show">${pill}${esc(displayTitles(show).main)}</span>`;
  }).join("");
  box.innerHTML = `
    <div class="tier-summary-title"><span>Recommendations${infoDot(about)}</span><span class="tier-summary-note">since ${since}</span></div>
    <div class="tier-summary-row">${statItem(res.shown, "shown")}${statItem(res.added, "added")}${statItem(res.removed || 0, "removed")}${tiers.join("")}</div>
    ${shows ? `<div class="rec-results-shows">${shows}</div>` : ""}`;
}

// One number with its name, for the boxes of the Profile tab
function statItem(count, label) {
  return `<span class="tier-summary-item"><span class="tier-summary-count">${Number(count).toLocaleString("en-US")}</span> ${label}</span>`;
}

// The numbers of the Discover deck: the answers of the user, also by the match of the shows
let interestResults = null;

function renderInterestResults() {
  const box = $("#interest-results");
  if (!box) return;
  const res = interestResults;
  if (!res || !res.answers) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  // One item for each group of the match: the number of "interested" answers of all answers
  const groups = (res.groups || []).filter((g) => g.answers).map((g) => {
    const low = Math.round(g.low);
    const high = Math.round(g.high);
    const name = high >= 100 ? `${low}+` : low <= 0 ? `below ${high}` : `${low}–${high}`;
    return `<span class="tier-summary-item"><span class="tier-summary-label">${name}</span> <span class="tier-summary-count">${g.interested}/${g.answers}</span></span>`;
  }).join("");
  // The box has only the numbers. The text is in the tooltip of the "i".
  let about = "Your answers in the Discover deck.";
  if (groups) about += " The second row has the \"interested\" answers of all answers, for each group of the match. If the match is good, a group with a higher match has a larger part of \"interested\".";
  if (groups && res.popular) about += ` This row counts only the cards from the ${Number(res.popular).toLocaleString("en-US")} most popular anime, which are the cards that the deck draws.`;
  if (res.model) about += ` In a test, the taste model put an interested show above a not-interested show in ${Math.round(100 * res.model.auc)}% of the pairs. It did not know the answers of the two shows.`;
  box.innerHTML = `
    <div class="tier-summary-title"><span>Discover${infoDot(about)}</span></div>
    <div class="tier-summary-row">${statItem(res.answers, "answers")}${statItem(res.interested, "interested")}${statItem(res.not_interested, "not interested")}</div>
    ${groups ? `<div class="tier-summary-row tier-summary-more"><span class="tier-summary-label">Interested, by match:</span>${groups}</div>` : ""}`;
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
  renderRecResults();
  renderInterestResults();
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
      <div class="tier-summary-box rec-results" id="rec-results" hidden></div>
      <div class="tier-summary-box rec-results" id="interest-results" hidden></div>
    </div>

    <div class="vector-map-wrap" id="profile-vector-map-wrap">
      <div class="vector-map-header">
        <div class="vector-map-title">
          <span>Taste Map</span>
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
    // The change also changes the match of the other shows
    scheduleMapMatch(1200);
  }
  return res;
}

// ---- The match gradient of the maps
// With the setting "Match gradient" on, a poster on a map is brighter for a higher match, and a
// dot of the catalog is stronger. The server gives the match of each point of the map, in the
// order of the points. The page gets the values when the setting is on. It gets them again after
// a change of a tier, of the watched state or of the removed shows.

// The brightness of a poster with a match of 0, as a part of the full brightness
const MATCH_DARK = 0.12;
// The dots of the catalog have this number of steps of strength
const GRADIENT_STEPS = 8;
// The page asks the server again this number of times when it does not get the match values
const MATCH_RETRIES = 4;
let mapMatchLoaded = false;
let mapMatchRequest = 0;
let mapMatchTimer = null;

// The brightness of a poster for a match in percent, from MATCH_DARK to 1. The curve is steep at
// the high end. The match is a rank in the catalog, thus one half of the catalog is below 50, and
// the shows of interest are in the last part.
function matchBrightness(match) {
  const part = Math.max(0, Math.min(1, match / 100));
  return MATCH_DARK + (1 - MATCH_DARK) * part * part;
}

function gradientOn() {
  return document.documentElement.dataset.gradient === "on";
}

// The buttons of the maps show if the page has the match values: "loading", "ready" or "error"
function setGradientState(state) {
  document.documentElement.dataset.gradientState = state;
  document.querySelectorAll(".vector-gradient-toggle").forEach((btn) => {
    btn.title = state === "error"
      ? "The server did not give the match values. Click two times to try again."
      : "The brightness of a poster shows its match. A show with a high match is bright.";
  });
}

async function loadMapMatch(attempt = 0) {
  if (!gradientOn()) return;
  const request = ++mapMatchRequest;
  if (!mapMatchLoaded) setGradientState("loading");
  try {
    const data = await getVectorMap();
    const res = await fetch("/api/vector-map/match");
    if (!res.ok) throw new Error(`the server answered ${res.status}`);
    const values = await res.json();
    // An older request that ends late must not replace the values of a newer request
    if (request !== mapMatchRequest) return;
    if (!data || !Array.isArray(values) || values.length !== data.points.length) {
      throw new Error("the list of values does not fit the map");
    }
    data.points.forEach((pt, i) => { pt.match = values[i]; });
    mapMatchLoaded = true;
    setGradientState("ready");
    activeVectorMaps.forEach((ctrl) => ctrl.scheduleDraw());
  } catch (e) {
    console.error("Failed to load the match of the shows of the map", e);
    if (request !== mapMatchRequest) return;
    // The server can be busy, or it can start at this moment: try again some times
    if (attempt < MATCH_RETRIES) {
      clearTimeout(mapMatchTimer);
      mapMatchTimer = setTimeout(() => loadMapMatch(attempt + 1), 2500 * (attempt + 1));
    } else if (!mapMatchLoaded) {
      setGradientState("error");
    }
  }
}

// Get the match values after `delay` milliseconds. A new call before that time replaces the old call.
function scheduleMapMatch(delay = 0) {
  clearTimeout(mapMatchTimer);
  if (gradientOn()) mapMatchTimer = setTimeout(() => loadMapMatch(), delay);
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

// ---- Search on the map
// The text of a title for a comparison: one form for each character, small letters, and no spaces
// or punctuation. Thus "re zero" finds "Re:Zero", and full-width letters find half-width letters.
function searchText(text) {
  return (text || "").normalize("NFKC").toLowerCase().replace(/[\s\p{P}\p{S}]+/gu, "");
}

// The words of the text of a search, each as text for a comparison
function searchWords(value) {
  return (value || "").split(/\s+/).map(searchText).filter(Boolean);
}

// All titles of a show as text for a comparison, with one title in each line. `aka` has the
// titles that the interface does not show: the English title, and for a show of the library the
// titles of its AniList entries. A show of the library has only its title from Jellyfin, which is
// in one language. Without `aka` a search in a different language does not find it.
function showSearchText(show) {
  return [show.title, show.title_native, ...(show.aka || [])].map(searchText).filter(Boolean).join("\n");
}

// The place of a found show in the results: a show with a title that starts with the first word
// is first, then the shows of the user. A lower number is a better place.
function searchRank(text, words, owned) {
  const starts = text.startsWith(words[0]) || text.includes(`\n${words[0]}`);
  return (starts ? 0 : 2) + (owned ? 0 : 1);
}

// The titles of the points of the map as text for a comparison. All maps use the same list.
let mapSearchTexts = null;
let mapSearchPoints = null;

function getMapSearchTexts(points) {
  if (mapSearchPoints !== points) {
    mapSearchTexts = points.map(showSearchText);
    mapSearchPoints = points;
  }
  return mapSearchTexts;
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
  // The search starts this time after the last key, in milliseconds
  const SEARCH_DELAY = 220;
  // The far view shows the found shows as posters up to this number. Above it they are dots.
  const SEARCH_POSTERS = 60;
  // The found shows that are dots are large dots with a halo up to this number
  const SEARCH_LARGE_DOTS = 400;
  // During a search the other shows have this part of their opacity
  const SEARCH_FADE = 0.25;
  // The width of a poster in pixels after a jump to a found show. A poster of this width has its title.
  const FOCUS_CARD = 78;

  // The search: the found shows as indexes of `points` with the best show first, or null without
  // a search. `searchPos` is the place in the list of the show that the user jumped to.
  let searchList = null;
  let searchSet = null;
  let searchPos = -1;
  let searchTimer = null;
  // The animation of a jump to a show
  let flight = null;
  // The match gradient is on in the draw of now, and the page has the match values
  let drawGradient = false;
  // The story of the list draws the dots of two steps and the change between them, or null.
  // See "The story of the list".
  let story = null;

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
    stopFlight();
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
    stopFlight();
    scale = 1.0;
    panX = 0;
    panY = 0;
    dismissHint();
    scheduleDraw();
  };

  // The button for the match gradient. The setting is the same for all maps: see "Settings".
  const legend = box.parentElement.querySelector(".vector-map-legend");
  if (legend && !legend.querySelector(".vector-gradient-toggle")) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "pill vector-gradient-toggle";
    btn.title = "The brightness of a poster shows its match. A show with a high match is bright.";
    btn.innerHTML = '<i class="gradient-swatch" aria-hidden="true"></i>Match gradient';
    btn.classList.toggle("active", gradientOn());
    btn.setAttribute("aria-pressed", String(gradientOn()));
    btn.onclick = () => setSetting("gradient", gradientOn() ? "off" : "on");
    const viewBox = legend.querySelector(".vector-view-pills");
    if (viewBox) viewBox.after(btn);
    else legend.prepend(btn);
  }

  // ---- The search box of the map
  // The user types a part of a title. The map shows the found shows with a frame, and it makes
  // the other shows faint. Enter moves the view to the next found show.
  let searchBox = box.querySelector(".vector-search");
  if (!searchBox) {
    searchBox = document.createElement("div");
    searchBox.className = "vector-search";
    searchBox.innerHTML = `
      <svg class="vector-search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
      <input class="vector-search-input" type="text" placeholder="Find a show on the map" aria-label="Find a show on the map" autocomplete="off" spellcheck="false" enterkeyhint="search">
      <span class="vector-search-count" aria-live="polite" hidden></span>
      <button class="vector-search-btn vector-search-prev" type="button" title="Go to the show before (Shift+Enter)" aria-label="Go to the show before" hidden>‹</button>
      <button class="vector-search-btn vector-search-next" type="button" title="Go to the next show (Enter)" aria-label="Go to the next show" hidden>›</button>
      <button class="vector-search-btn vector-search-clear" type="button" title="Clear the search (Esc)" aria-label="Clear the search" hidden>✕</button>
    `;
    box.appendChild(searchBox);
  }
  const searchInput = searchBox.querySelector(".vector-search-input");
  const searchCount = searchBox.querySelector(".vector-search-count");
  const searchPrev = searchBox.querySelector(".vector-search-prev");
  const searchNext = searchBox.querySelector(".vector-search-next");
  const searchClear = searchBox.querySelector(".vector-search-clear");

  function paintSearch() {
    const count = searchList ? searchList.length : 0;
    searchClear.hidden = !searchInput.value;
    searchCount.hidden = !searchList;
    searchNext.hidden = count < 1;
    searchPrev.hidden = count < 2;
    searchBox.classList.toggle("is-empty", !!searchList && count === 0);
    if (!searchList) return;
    searchCount.textContent = count === 0 ? "No show found" : searchPos >= 0 ? `${searchPos + 1} / ${count}` : `${count} found`;
  }

  function runSearch() {
    clearTimeout(searchTimer);
    searchTimer = null;
    // Each word of the text must be in a title of the show: see showSearchText
    const words = searchWords(searchInput.value);
    searchPos = -1;
    if (!words.length) {
      searchList = null;
      searchSet = null;
    } else {
      const texts = getMapSearchTexts(points);
      const found = [];
      for (let i = 0; i < n; i++) {
        // The order for the jumps: see searchRank. Shows with the same rank are in the order
        // of their AniList score, the highest first.
        if (words.every((word) => texts[i].includes(word))) found.push([i, searchRank(texts[i], words, points[i].owned)]);
      }
      found.sort((a, b) => a[1] - b[1] || (points[b[0]].score ?? -1) - (points[a[0]].score ?? -1));
      searchList = found.map((item) => item[0]);
      searchSet = new Set(searchList);
    }
    paintSearch();
    scheduleDraw();
  }

  function stopFlight() {
    if (flight) cancelAnimationFrame(flight);
    flight = null;
  }

  // Set the pan so that the show `i` is at the screen position (px, py) with the zoom of now
  function panTo(i, px, py, w, h, side) {
    const t = gridBlend(side);
    const x = mapX[i] + (gridX[i] - mapX[i]) * t;
    const y = mapY[i] + (gridY[i] - mapY[i]) * t;
    const k = side * scale;
    panX = px - x * k - ((w - side) / 2 - w / 2) * scale - w / 2;
    panY = py - (1 - y) * k - ((h - side) / 2 - h / 2) * scale - h / 2;
  }

  // Move the view to a show in a short animation. The zoom grows until the poster of the show is
  // easy to see. A view that is nearer than that keeps its zoom.
  function flyTo(i) {
    stopFlight();
    const { w, h, side } = viewSize();
    if (w === 0 || h === 0) return;
    dismissHint();
    hoveredPoint = null;
    tooltip.hidden = true;
    tooltip.style.display = "none";
    const near = cell && viewMode() === "posters" ? FOCUS_CARD / CARD_FILL / cellBase(side) : 5;
    const startScale = scale;
    const endScale = Math.max(scale, Math.min(maxScale(side), near));
    project(w, h, side);
    const startX = sx[i];
    const startY = sy[i];
    // No animation for a user who asked the system for less motion
    const duration = matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 480;
    const begin = performance.now();
    const frame = (now) => {
      const t = duration ? Math.max(0, Math.min(1, (now - begin) / duration)) : 1;
      const e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      scale = startScale * Math.pow(endScale / startScale, e);
      panTo(i, startX + (w / 2 - startX) * e, startY + (h / 2 - startY) * e, w, h, side);
      draw();
      flight = t < 1 && !destroyed ? requestAnimationFrame(frame) : null;
    };
    flight = requestAnimationFrame(frame);
  }

  // Go to the next found show, or to the one before. After the last show the first one is next.
  function stepSearch(step) {
    if (!searchList || !searchList.length) return;
    const count = searchList.length;
    searchPos = searchPos < 0 ? (step > 0 ? 0 : count - 1) : (searchPos + step + count) % count;
    paintSearch();
    flyTo(searchList[searchPos]);
  }

  function clearSearch() {
    searchInput.value = "";
    runSearch();
  }

  searchInput.oninput = () => {
    searchClear.hidden = !searchInput.value;
    // Wait until the user stops typing: a search for each key would draw the map too frequently
    clearTimeout(searchTimer);
    searchTimer = setTimeout(runSearch, SEARCH_DELAY);
  };
  searchInput.onkeydown = (e) => {
    // The other parts of the page must not get the keys of the search
    e.stopPropagation();
    // A key that completes Japanese text in the input method is not a command
    if (e.isComposing || e.keyCode === 229) return;
    if (e.key === "Enter") {
      e.preventDefault();
      // The text changed a moment ago: search now, and do not wait
      if (searchTimer) runSearch();
      stepSearch(e.shiftKey ? -1 : 1);
    } else if (e.key === "Escape") {
      e.preventDefault();
      clearSearch();
    }
  };
  searchPrev.onclick = () => stepSearch(-1);
  searchNext.onclick = () => stepSearch(1);
  searchClear.onclick = () => {
    clearSearch();
    searchInput.focus();
  };
  // A map that is made again keeps the text of its search box
  if (searchInput.value.trim()) runSearch();

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
    // The match gradient: a poster with a low match is dark. The title and the frame keep their
    // brightness. The poster under the pointer also keeps it, so that the user can see the poster.
    if (drawGradient && !isHovered && pt.match != null) {
      ctx.fillStyle = `rgba(0, 0, 0, ${(1 - matchBrightness(pt.match)).toFixed(3)})`;
      ctx.fillRect(x, y, pw, ph);
    }
    if (pw >= TITLE_MIN) drawTitle(ctx, pt, x, y, pw, ph);
    ctx.restore();

    ctx.strokeStyle = isHovered ? colors.ink : look.stroke;
    ctx.lineWidth = isHovered ? Math.max(2.5, frame) : frame;
    roundedRect(ctx, x, y, pw, ph, radius);
    ctx.stroke();

    if (look.badge) drawBadge(ctx, look, x, y, pw, colors);
  }

  // The frame of a found show of the search. The show that the user jumped to has a thicker frame.
  function drawFindRing(ctx, cx, cy, pw, colors, current) {
    const ph = pw * POSTER_ASPECT;
    const gap = Math.max(2, pw * 0.05);
    ctx.save();
    ctx.strokeStyle = colors.find;
    ctx.shadowColor = colors.find;
    ctx.shadowBlur = current ? Math.max(10, pw * 0.3) : Math.max(5, pw * 0.14);
    ctx.lineWidth = (current ? 1.8 : 1) * Math.max(2, pw * 0.055);
    roundedRect(ctx, cx - pw / 2 - gap, cy - ph / 2 - gap, pw + 2 * gap, ph + 2 * gap, Math.max(3, pw * 0.08));
    ctx.stroke();
    ctx.restore();
  }

  // The dots of the story of the list. `story.from` and `story.to` tell for each show if it stays
  // in the step before and in the step of now. A show that stays is a strong dot, and each other
  // show is a faint dot. Fewer shows stay in each step, thus their dots get stronger and larger.
  // `strength` multiplies all opacities.
  function drawStoryDots(ctx, w, h, colors, strength) {
    if (strength <= 0) return;
    const { from, to, ease, lookFrom, lookTo } = story;
    const base = dotRadius(false);
    const mix = (a, b) => a + (b - a) * ease;
    // The groups: 0 = stays out, 1 = goes out, 2 = comes in, 3 = stays in
    const groups = [[], [], [], []];
    // The shows of the user are apart. A show of the user that is out has no dot.
    const mine = [[], [], [], []];
    for (let i = 0; i < n; i++) {
      if (sx[i] < -20 || sx[i] > w + 20 || sy[i] < -20 || sy[i] > h + 20) continue;
      (points[i].owned ? mine : groups)[(from[i] ? 1 : 0) + (to[i] ? 2 : 0)].push(i);
    }
    // All dots of a group are one path: one path for each dot is slow
    const dots = (list, color, alpha, size) => {
      if (!list.length || alpha <= 0.003) return;
      const r = base * size;
      ctx.fillStyle = color;
      ctx.globalAlpha = Math.min(1, alpha) * strength;
      ctx.beginPath();
      for (const i of list) {
        ctx.moveTo(sx[i] + r, sy[i]);
        ctx.arc(sx[i], sy[i], r, 0, Math.PI * 2);
      }
      ctx.fill();
    };
    // The dots have the accent color from the step in which the taste of the user starts to count
    const colorOf = (look) => (look.taste ? colors.accent : colors.dot);
    dots(groups[0], colors.dot, STORY_FAINT, 1);
    dots(groups[1], colorOf(lookFrom), mix(lookFrom.alpha, STORY_FAINT), mix(lookFrom.size, 1));
    dots(groups[2], colorOf(lookTo), mix(STORY_FAINT, lookTo.alpha), mix(1, lookTo.size));
    if (lookFrom.taste === lookTo.taste) {
      dots(groups[3], colorOf(lookTo), mix(lookFrom.alpha, lookTo.alpha), mix(lookFrom.size, lookTo.size));
    } else {
      // The color changes: the dots of the old color go out, and the dots of the new color come in
      const size = mix(lookFrom.size, lookTo.size);
      dots(groups[3], colorOf(lookFrom), lookFrom.alpha * (1 - ease), size);
      dots(groups[3], colorOf(lookTo), lookTo.alpha * ease, size);
    }
    // The shows of the user have the colors of their tiers, as on the usual map. They are in
    // the catalog, and they go out in the second step.
    const mineSize = dotRadius(true) / base;
    const mineAlpha = [0, 1 - ease, ease, 1];
    for (let g = 1; g < 4; g++) {
      for (const tier of [null, "D", "C", "B", "A", "S"]) {
        dots(mine[g].filter((i) => (points[i].tier || null) === tier), (tier && colors.tier[tier]) || colors.library, mineAlpha[g], mineSize);
      }
    }
    ctx.globalAlpha = 1;
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
      find: rootStyle.getPropertyValue("--find").trim() || "#0e8177",
      dot: isDark ? "rgb(222, 216, 206)" : "rgb(74, 68, 63)",
      tier: {},
    };
    for (const t of ["S", "A", "B", "C", "D"]) {
      colors.tier[t] = rootStyle.getPropertyValue(`--tier-${t.toLowerCase()}`).trim();
    }
    const view = viewMode();
    const cards = cardsOn(side);
    drawGradient = gradientOn() && mapMatchLoaded;
    let shown = 0;
    let cardWidth = 0;
    // The search: see "The search box of the map"
    const searching = searchList !== null;
    const isFound = (i) => searching && searchSet.has(i);
    const currentFound = searching && searchPos >= 0 ? searchList[searchPos] : -1;

    if (cards) {
      // The close view. Each show in view is a poster in its cell: catalog first, then the shows
      // of the user, then the highlighted shows, then the found shows of the search, and the show
      // under the pointer last.
      cardWidth = Math.min(CELL_MAX, cellBase(side) * scale) * CARD_FILL;
      const cardHeight = cardWidth * POSTER_ASPECT;
      const layers = [[], [], [], []];
      for (let i = 0; i < n; i++) {
        if (sx[i] < -cardWidth || sx[i] > w + cardWidth || sy[i] < -cardHeight || sy[i] > h + cardHeight) continue;
        const pt = points[i];
        if (hoveredPoint && pt.id === hoveredPoint.id) continue;
        layers[isFound(i) ? 3 : highlightSet.has(pt.id) ? 2 : pt.owned ? 1 : 0].push(i);
      }
      for (let k = 0; k < layers.length; k++) {
        // A search makes the other shows faint, so that the found shows are easy to see
        ctx.globalAlpha = searching && k < 3 ? SEARCH_FADE : 1;
        for (const i of layers[k]) {
          drawCard(ctx, points[i], sx[i], sy[i], cardWidth, colors, false);
          if (k === 3) drawFindRing(ctx, sx[i], sy[i], cardWidth, colors, i === currentFound);
          shown++;
        }
      }
      ctx.globalAlpha = 1;
      const hi = hoveredPoint ? indexOf.get(hoveredPoint.id) : undefined;
      if (hi !== undefined) {
        drawCard(ctx, hoveredPoint, sx[hi], sy[hi], cardWidth * 1.12, colors, true);
        if (isFound(hi)) drawFindRing(ctx, sx[hi], sy[hi], cardWidth * 1.12, colors, hi === currentFound);
        shown++;
      }
    } else {
      // The far view. A highlighted show is a poster (Posters view) or a larger dot (Dots view).
      // A found show of the search is a poster. It is a dot in the Dots view, and also when the
      // search found too many shows for posters.
      const markers = view === "posters";
      const foundCards = searching && markers && searchList.length <= SEARCH_POSTERS;
      const special = (i) => isFound(i) || (highlightSet.has(points[i].id) && (markers || highlightKind === "recommended"));
      // A search makes the other shows faint, so that the found shows are easy to see
      // The story of the list draws its own dots. In its last step the usual picture comes back.
      const usual = story ? (story.last ? story.ease : 0) : 1;
      if (story) drawStoryDots(ctx, w, h, colors, 1 - usual);
      const fade = (searching ? SEARCH_FADE : 1) * usual;
      ctx.globalAlpha = fade;

      // 1. The dots of the catalog. With the match gradient a dot is stronger and larger for a
      // higher match. The dots are in steps, and each step is one path: one path for each dot is slow.
      const catR = dotRadius(false);
      const steps = [];
      for (let k = 0; k < (drawGradient ? GRADIENT_STEPS : 1); k++) steps.push([]);
      for (let i = 0; i < n; i++) {
        const pt = points[i];
        if (pt.owned || special(i)) continue;
        if (sx[i] < -20 || sx[i] > w + 20 || sy[i] < -20 || sy[i] > h + 20) continue;
        const k = drawGradient ? Math.floor(matchBrightness(pt.match ?? 0) * GRADIENT_STEPS) : 0;
        steps[Math.min(steps.length - 1, k)].push(i);
      }
      ctx.fillStyle = drawGradient ? colors.dot : colors.catalog;
      for (let k = 0; k < steps.length; k++) {
        const part = (k + 0.5) / steps.length;
        const r = drawGradient ? catR * (0.8 + 0.6 * part) : catR;
        if (drawGradient) ctx.globalAlpha = fade * (0.05 + 0.9 * part);
        ctx.beginPath();
        for (const i of steps[k]) {
          ctx.moveTo(sx[i] + r, sy[i]);
          ctx.arc(sx[i], sy[i], r, 0, Math.PI * 2);
        }
        ctx.fill();
      }
      ctx.globalAlpha = fade;

      // 2. The dots of the shows of the user. A rated show has the color of its tier. S is last, on top.
      const libR = dotRadius(true);
      for (const tier of [null, "D", "C", "B", "A", "S"]) {
        ctx.fillStyle = (tier && colors.tier[tier]) || colors.library;
        ctx.beginPath();
        for (let i = 0; i < n; i++) {
          const pt = points[i];
          if (!pt.owned || special(i) || (pt.tier || null) !== tier) continue;
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
          if (!highlightSet.has(pt.id) || isFound(i)) continue;
          if (sx[i] < -60 || sx[i] > w + 60 || sy[i] < -90 || sy[i] > h + 90) continue;
          if (hoveredPoint && hoveredPoint.id === pt.id) {
            hovered = i;
            continue;
          }
          drawCard(ctx, pt, sx[i], sy[i], width, colors, false);
          shown++;
        }
        if (hovered >= 0) {
          ctx.globalAlpha = 1;
          drawCard(ctx, points[hovered], sx[hovered], sy[hovered], width * 1.3, colors, true);
          ctx.globalAlpha = fade;
          shown++;
        }
      } else if (highlightKind === "recommended") {
        const hiR = highlightDotRadius();
        for (let i = 0; i < n; i++) {
          if (!highlightSet.has(points[i].id) || isFound(i)) continue;
          if (sx[i] < -20 || sx[i] > w + 20 || sy[i] < -20 || sy[i] > h + 20) continue;
          ctx.fillStyle = colors.accent;
          ctx.globalAlpha = 0.25 * fade;
          ctx.beginPath();
          ctx.arc(sx[i], sy[i], hiR * 2, 0, Math.PI * 2);
          ctx.fill();
          ctx.globalAlpha = fade;
          ctx.beginPath();
          ctx.arc(sx[i], sy[i], hiR, 0, Math.PI * 2);
          ctx.fill();
          ctx.strokeStyle = colors.paper;
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }
      }
      ctx.globalAlpha = 1;

      // 4. The found shows of the search. The best show is drawn last, on top.
      if (searching) {
        const inView = [];
        for (let k = searchList.length - 1; k >= 0; k--) {
          const i = searchList[k];
          if (sx[i] < -60 || sx[i] > w + 60 || sy[i] < -90 || sy[i] > h + 90) continue;
          inView.push(i);
        }
        if (foundCards) {
          const width = markerWidth(side);
          let hovered = -1;
          for (const i of inView) {
            if (hoveredPoint && hoveredPoint.id === points[i].id) {
              hovered = i;
              continue;
            }
            drawCard(ctx, points[i], sx[i], sy[i], width, colors, false);
            drawFindRing(ctx, sx[i], sy[i], width, colors, i === currentFound);
            shown++;
          }
          if (hovered >= 0) {
            drawCard(ctx, points[hovered], sx[hovered], sy[hovered], width * 1.3, colors, true);
            drawFindRing(ctx, sx[hovered], sy[hovered], width * 1.3, colors, hovered === currentFound);
            shown++;
          }
        } else {
          // Dots. All dots are one path: one path for each dot is slow when the search found
          // thousands of shows. Then the dots are also small and have no halo.
          const many = searchList.length > SEARCH_LARGE_DOTS;
          const foundR = many ? dotRadius(true) + 0.5 : highlightDotRadius() + 1;
          const arcs = (r) => {
            ctx.beginPath();
            for (const i of inView) {
              const size = i === currentFound ? Math.max(r * 1.6, 7) : r;
              ctx.moveTo(sx[i] + size, sy[i]);
              ctx.arc(sx[i], sy[i], size, 0, Math.PI * 2);
            }
          };
          ctx.fillStyle = colors.find;
          if (!many) {
            ctx.globalAlpha = 0.28;
            arcs(foundR * 2);
            ctx.fill();
            ctx.globalAlpha = 1;
          }
          arcs(foundR);
          ctx.fill();
          ctx.strokeStyle = colors.paper;
          ctx.lineWidth = many ? 0.75 : 1.5;
          ctx.stroke();
        }
      }

      // 5. A ring around the dot under the pointer. A show that is a poster has no ring.
      const hi = hoveredPoint ? indexOf.get(hoveredPoint.id) : undefined;
      const isCard = hi !== undefined && (foundCards ? isFound(hi) || highlightSet.has(hoveredPoint.id) : !isFound(hi) && markers && highlightSet.has(hoveredPoint.id));
      if (hi !== undefined && !isCard) {
        const ringR = special(hi) ? highlightDotRadius() * 2 + 2 : dotRadius(hoveredPoint.owned) + 6;
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
    canvas.dataset.found = searching ? String(searchList.length) : "";
    canvas.dataset.story = story && !cards ? String(story.step) : "";
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

    // 1. The found shows of the search. They are above the other shows.
    const markers = view === "posters";
    if (searchList) {
      const asCards = markers && searchList.length <= SEARCH_POSTERS;
      const pw = markerWidth(side);
      const ph = pw * POSTER_ASPECT;
      const hitR = (highlightDotRadius() + 5) ** 2;
      for (const i of searchList) {
        if (sx[i] < -60 || sx[i] > w + 60 || sy[i] < -90 || sy[i] > h + 90) continue;
        const hit = asCards
          ? Math.abs(sx[i] - mx) <= pw / 2 + 3 && Math.abs(sy[i] - my) <= ph / 2 + 3
          : (sx[i] - mx) ** 2 + (sy[i] - my) ** 2 <= hitR;
        if (hit) return points[i];
      }
    }

    // 2. The highlighted shows
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

    // 3. The dots of the shows of the user. The target is larger than the dot, and it grows with the dot.
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

    // 4. The dots of the catalog (in the Dots view, or from a zoom of 180%)
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
    stopFlight();
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

    // During the story of the list a dot is not a show under the pointer
    const pt = story ? null : findNearest(mx, my);
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
      if (gradientOn() && mapMatchLoaded && pt.match != null) metaParts.push(`${formatMatch(pt.match)}% match`);

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
    stopFlight();
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
    // The story of the list: see "The story of the list"
    setStory: (state) => {
      story = state;
      if (state) {
        hoveredPoint = null;
        tooltip.hidden = true;
        tooltip.style.display = "none";
      }
    },
    // Show the full map. `dx` and `dy` move it, in pixels.
    resetView: (dx = 0, dy = 0) => {
      stopFlight();
      scale = 1.0;
      panX = dx;
      panY = dy;
      dismissHint();
      scheduleDraw();
    },
    clearSearch: () => {
      if (searchInput.value) clearSearch();
    },
    destroy: () => {
      destroyed = true;
      if (animFrame) cancelAnimationFrame(animFrame);
      clearTimeout(searchTimer);
      stopFlight();
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
      // A show of the library has one title. The second line then has its first other title.
      if (sub) subParts.push(esc(sub));
      else if (t.aka && t.aka.length) subParts.push(esc(t.aka[0]));
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
    const v = q.value.trim();
    qClear.hidden = !v;
    const words = searchWords(v);
    // One Latin letter finds too many shows. One Japanese character can be a full word.
    if (!words.length || (v.length < 2 && /^[\x00-\x7f]*$/.test(v))) {
      closeSearch();
      return;
    }
    // Each word of the text must be in a title of the show: see showSearchText
    const found = [];
    titles.forEach((t, k) => {
      if (t.searchKey === undefined) t.searchKey = showSearchText(t);
      if (words.every((word) => t.searchKey.includes(word))) found.push([t, searchRank(t.searchKey, words, t.owned), k]);
    });
    currentMatches = found.sort((a, b) => a[1] - b[1] || a[2] - b[2]).slice(0, 10).map((item) => item[0]);
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
    text: "The list has the shows that are most similar to the seed show. The formula and the crowd links have no effect on this list.",
  },
};
let recsKinds = "usual";
try {
  if (localStorage.getItem(FORMULA_KEY) === "all") recsKinds = "all";
} catch (e) {}
// The crowd links are the recommendations of AniList users: the shows that the fans of one show
// also like. Without them the formula uses only the ratings of the user and the facts of the
// shows. The browser keeps the selection.
const LINKS_KEY = "rinrikun-links";
const LINKS_TEXT = {
  true: "<b>Crowd links: on.</b> The formula also uses the shows that the fans of your shows recommend on AniList.",
  false: "<b>Crowd links: off.</b> The formula uses only your ratings, and the tags and the text of the shows.",
};
// The match of a show is not a part of the formula of the list. The tooltip "How this works" says
// so, because a list with the crowd links can have a show with a lower match near its top.
const MATCH_TEXT = "<b>Match:</b> how near a show is to your taste. Your predicted tier has a small part in it. The match does not use the formula, thus the list is not always in the order of the match.";
let recsLinks = true;
try {
  if (localStorage.getItem(LINKS_KEY) === "off") recsLinks = false;
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
  const linksGroup = $("#recs-links-group");
  if (linksGroup) linksGroup.style.display = seed ? "none" : "";

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

// The formula that made the list on the page. The tooltip of the button "How this works" tells it.
let recsApplied = { formula: "usual", links: true };

function setRecsApplied(applied, links) {
  if (!FORMULAS[applied]) return;
  recsApplied = { formula: applied, links };
  const btn = $("#recs-how-btn");
  if (!btn) return;
  btn.dataset.formula = applied;
  btn.dataset.links = applied === "seed" ? "" : String(links);
}

TIP_CONTENT.recs = () => {
  const formula = FORMULAS[recsApplied.formula];
  const parts = [`<p><b>${formula.name}.</b> ${formula.text}</p>`];
  if (recsApplied.formula !== "seed") {
    parts.push(`<p>${LINKS_TEXT[recsApplied.links]}</p>`, `<p>${MATCH_TEXT}</p>`,
      "<p>The button <b>How the list is made</b>, above the map, shows each step on the map.</p>");
  }
  return `<div class="tip-text">${parts.join("")}</div>`;
};

function paintRecsFormulaPills() {
  document.querySelectorAll("#recs-formula-pills .pill").forEach((btn) => {
    const on = btn.dataset.kinds === recsKinds;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-pressed", String(on));
  });
  document.querySelectorAll("#recs-links-pills .pill").forEach((btn) => {
    const on = btn.dataset.links === String(recsLinks);
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
  document.querySelectorAll("#recs-links-pills .pill").forEach((btn) => {
    btn.onclick = () => {
      const on = btn.dataset.links === "true";
      if (on === recsLinks) return;
      recsLinks = on;
      try { localStorage.setItem(LINKS_KEY, on ? "on" : "off"); } catch (e) {}
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
  const storyBtn = $("#recs-story-btn");
  if (storyBtn) {
    storyBtn.onclick = () => {
      if (storyState) closeStory();
      else startStory();
    };
  }
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
  scheduleMapMatch(1200);
}

function refreshRecsAfterDismiss() {
  closeStory();
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
  // The story of the list is for the list that the page showed
  closeStory();
  lastDismissed = null;
  renderRecsUndoBar();
  renderRecsSeedBar();
  const applied = seed ? "seed" : recsKinds;
  const appliedLinks = recsLinks;
  const base = withFormula(seed
    ? `/api/recommend?k=40&seed=${encodeURIComponent(seed.id)}`
    : `/api/recommend?k=40&mode=${recsVariety ? "diverse" : "hybrid"}`);
  const request = ++recsRequest;
  const list = await (await fetch(`${base}&new_only=${!recsSequels}`)).json();
  // An older request that ends late must not replace the list of a newer request. Thus the
  // tooltip "How this works" always names the formula of the list that the user sees.
  if (request !== recsRequest) return;
  rawRecs = list;
  setRecsApplied(applied, appliedLinks);
  renderRecsGrid();
  const ids = rawRecs.map((s) => s.id);
  const map = activeVectorMaps.get("recs-vector-canvas");
  // An open map keeps its zoom and its position: only the highlighted shows change
  if (map) map.setHighlight(ids);
  else await initVectorMap("recs-vector-canvas", "recs-vector-tooltip", ids, "Recommended");
  paintStoryButton();
  if (request === recsRequest) autoStory();
}

// ---- The story of the list
// An animation on the Recommendations map shows how the formula goes from the catalog to the list.
// Each step is one part of the formula. The dots of the shows that stay are strong, and the other
// dots are faint. A panel on the map has the number of shows and a short text for each step.
// The server gives the steps: see /api/recommend/steps.
const STORY_SEEN_KEY = "rinrikun-story-seen";
// The time of one step in milliseconds, and the part of it in which the dots change
const STORY_STEP_MS = 3400;
const STORY_MOVE_MS = 1100;
// The opacity of the dot of a show that does not stay
const STORY_FAINT = 0.06;
// The width of the panel on a wide screen, with its distance from the edge of the map box
const STORY_PANEL_SPACE = 288;
const storyNumber = (value) => Number(value).toLocaleString("en-US");
const STORY_STEPS = {
  catalog: {
    name: "The catalog",
    text: (step) => `Each dot is one show. The catalog has ${storyNumber(step.count)} shows.`,
  },
  new: {
    name: "New for you",
    text: (step, info) => `The ${storyNumber(info.shows)} shows that you have go out, with the other shows of their ${storyNumber(info.franchises)} franchises. `
      + `Shows that are not released go out too${info.removed ? `, and the ${storyNumber(info.removed)} shows that you removed` : ""}. One show stays for each franchise.`,
  },
  content: {
    name: "Your taste",
    text: (step, info) => `The formula learns from the tags and the text of your ${storyNumber(info.liked)} liked shows. `
      + "A show stays if it is like some of them, or if it has what they have and the catalog does not have.",
  },
  links: {
    name: "Fans of your shows",
    text: (step, info) => `AniList users who like your shows also recommend other shows. A show moves up if it has many of these links from your ${storyNumber(info.sources)} franchises.`,
  },
  tier: {
    name: "Your tiers",
    text: (step, info) => `A small model learns from the tags of your ${storyNumber(info.rated)} rated shows which tier you will give. A show moves down if the model predicts a low tier for it.`,
  },
  kind: {
    name: "Your usual kinds",
    text: () => "A show moves up if its year, its format and its length are usual for your library.",
  },
  list: {
    name: "Your list",
    text: (step) => `The formula adds all the parts. The ${storyNumber(step.count)} best shows are your list${recsVariety ? ", with more variety" : ""}.`,
  },
};
// The story that plays, or null
let storyState = null;
// The number of the last request for the steps
let storyRequest = 0;

function storyPanel() {
  const box = document.querySelector("#recs-vector-map-wrap .vector-canvas-box");
  if (!box) return null;
  let panel = box.querySelector(".story-panel");
  if (!panel) {
    panel = document.createElement("div");
    panel.className = "story-panel";
    panel.hidden = true;
    box.appendChild(panel);
  }
  return panel;
}

function paintStoryButton() {
  const btn = $("#recs-story-btn");
  if (!btn) return;
  btn.style.display = seed ? "none" : "";
  btn.classList.toggle("active", !!storyState);
  btn.setAttribute("aria-pressed", String(!!storyState));
}

// The look of the dots that stay in a step. Fewer shows stay in each step, thus the dots get
// stronger and larger. `least` is the number of shows of the list.
function storyLook(step, index, total, least) {
  const span = Math.log(Math.max(total, least + 1) / least);
  const part = Math.max(0, Math.min(1, 1 - Math.log(Math.max(step.count, least) / least) / span));
  // The taste of the user counts from the third step
  return { alpha: 0.26 + 0.6 * part, size: 1 + 1.4 * part, taste: index >= 2 };
}

async function startStory() {
  const map = activeVectorMaps.get("recs-vector-canvas");
  const panel = storyPanel();
  if (!map || !panel || seed || !vectorMapData) return;
  closeStory();
  const request = ++storyRequest;
  let data;
  try {
    const res = await fetch(withFormula(`/api/recommend/steps?k=${Math.max(1, rawRecs.length || 40)}&new_only=${!recsSequels}`));
    if (!res.ok) throw new Error(`steps failed: ${res.status}`);
    data = await res.json();
  } catch (e) {
    console.error("Failed to load the steps of the list", e);
    return;
  }
  if (request !== storyRequest || !data.steps || data.steps.length < 3) return;

  const points = vectorMapData.points;
  const lit = data.steps.map((step) => {
    const flags = new Uint8Array(points.length);
    if (!step.points) flags.fill(1);
    else for (const p of step.points) if (p < flags.length) flags[p] = 1;
    return flags;
  });
  // The last step is the list that the page shows
  const last = data.steps[data.steps.length - 1];
  if (last.key === "list" && rawRecs.length) {
    const position = new Map(points.map((pt, i) => [pt.id, i]));
    const flags = new Uint8Array(points.length);
    let count = 0;
    for (const r of rawRecs) {
      const i = position.get(r.id);
      if (i === undefined) continue;
      flags[i] = 1;
      count++;
    }
    lit[lit.length - 1] = flags;
    last.count = count;
  }
  const total = data.steps[0].count;
  const least = Math.max(1, last.count);
  storyState = {
    map, panel, lit, steps: data.steps, info: data.info,
    looks: data.steps.map((step, i) => storyLook(step, i, total, least)),
    index: -1, playing: true, frame: null, timer: null,
  };
  renderStoryPanel();
  paintStoryButton();
  // The zoom buttons move away from the panel
  panel.parentElement.classList.add("story-open");
  // The panel covers a part of the map box. Move the map so that the panel does not cover it.
  const box = panel.parentElement.getBoundingClientRect();
  const rect = panel.getBoundingClientRect();
  const side = Math.max(1, Math.min(box.width, box.height) - 48);
  let dx = 0;
  let dy = 0;
  if (rect.width < box.width * 0.6) {
    const over = (box.width + side) / 2 - (rect.left - box.left) + 12;
    dx = -Math.max(0, Math.min(over, (box.width - side) / 2 - 8));
  } else {
    const over = (box.height + side) / 2 - (rect.top - box.top) + 12;
    dy = -Math.max(0, Math.min(over, (box.height - side) / 2 - 56));
  }
  map.clearSearch();
  map.resetView(dx, dy);
  showStoryStep(0);
}

function renderStoryPanel() {
  const st = storyState;
  const total = st.steps[0].count;
  const rows = st.steps.map((step, i) => {
    // The bar of a step: the number of its shows, on a logarithmic scale
    const width = Math.max(6, Math.round((100 * Math.log(Math.max(step.count, 2))) / Math.log(Math.max(total, 3))));
    return `<button type="button" class="story-row" data-step="${i}" style="--w:${width}%">
      <span class="story-row-name">${STORY_STEPS[step.key].name}</span>
      <span class="story-row-count">${storyNumber(step.count)}</span>
    </button>`;
  }).join("");
  st.panel.innerHTML = `
    <div class="story-head">
      <span class="story-title">How the list is made</span>
      <span class="story-progress"></span>
      <button type="button" class="story-close" aria-label="Close" title="Close">✕</button>
    </div>
    <div class="story-rows">${rows}</div>
    <p class="story-text" aria-live="polite"></p>
    <div class="story-controls"><button type="button" class="pill story-play"></button></div>
    <p class="story-note">Each step keeps the best shows by the score up to that step. A later step can bring a show back.</p>`;
  st.panel.hidden = false;
  st.panel.querySelector(".story-close").onclick = closeStory;
  st.panel.querySelectorAll(".story-row").forEach((row) => {
    row.onclick = () => {
      st.playing = false;
      showStoryStep(Number(row.dataset.step));
    };
  });
  st.panel.querySelector(".story-play").onclick = () => {
    const ended = st.index === st.steps.length - 1;
    st.playing = !st.playing;
    if (!st.playing) {
      clearTimeout(st.timer);
      paintStoryPanel();
    } else {
      showStoryStep(ended ? 0 : st.index + 1);
    }
  };
  st.panel.onkeydown = (e) => {
    if (e.key === "Escape") closeStory();
  };
}

function paintStoryPanel() {
  const st = storyState;
  if (!st) return;
  const step = st.steps[st.index];
  st.panel.querySelectorAll(".story-row").forEach((row, i) => {
    row.classList.toggle("is-done", i <= st.index);
    row.classList.toggle("is-current", i === st.index);
    if (i === st.index) row.setAttribute("aria-current", "step");
    else row.removeAttribute("aria-current");
  });
  st.panel.querySelector(".story-progress").textContent = `${st.index + 1} / ${st.steps.length}`;
  st.panel.querySelector(".story-text").textContent = STORY_STEPS[step.key].text(step, st.info);
  const ended = st.index === st.steps.length - 1;
  st.panel.querySelector(".story-play").textContent = st.playing ? "⏸ Pause" : ended ? "▶ Play again" : "▶ Play";
  // The state of the story, for the tests of the interface
  st.panel.dataset.step = step.key;
  st.panel.dataset.playing = String(st.playing);
}

// Go to a step. The dots change from the step that the map shows to this step.
function showStoryStep(index) {
  const st = storyState;
  if (!st) return;
  cancelAnimationFrame(st.frame);
  clearTimeout(st.timer);
  const before = st.index < 0 ? index : st.index;
  st.index = index;
  const last = index === st.steps.length - 1;
  // No animation for a user who asked the system for less motion
  const duration = before === index || matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : STORY_MOVE_MS;
  const state = { from: st.lit[before], to: st.lit[index], lookFrom: st.looks[before], lookTo: st.looks[index], ease: 0, last, step: index };
  paintStoryPanel();
  const begin = performance.now();
  const frame = (now) => {
    if (storyState !== st) return;
    const t = duration ? Math.max(0, Math.min(1, (now - begin) / duration)) : 1;
    state.ease = t * t * (3 - 2 * t);
    st.map.setStory(state);
    st.map.draw();
    if (t < 1) {
      st.frame = requestAnimationFrame(frame);
      return;
    }
    if (last) {
      // The story ends with the usual picture of the map: the list as posters
      st.map.setStory(null);
      st.map.scheduleDraw();
      st.playing = false;
      paintStoryPanel();
    } else if (st.playing) {
      st.timer = setTimeout(() => showStoryStep(index + 1), STORY_STEP_MS - duration);
    }
  };
  st.frame = requestAnimationFrame(frame);
}

function closeStory() {
  storyRequest++;
  const st = storyState;
  if (!st) return;
  storyState = null;
  cancelAnimationFrame(st.frame);
  clearTimeout(st.timer);
  st.map.setStory(null);
  st.map.scheduleDraw();
  st.panel.hidden = true;
  st.panel.innerHTML = "";
  st.panel.parentElement.classList.remove("story-open");
  paintStoryButton();
}

// The story plays one time without a click: with the first list of recommendations in this browser
function autoStory() {
  if (seed || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  try {
    if (localStorage.getItem(STORY_SEEN_KEY)) return;
    localStorage.setItem(STORY_SEEN_KEY, "1");
  } catch (e) {
    return;
  }
  startStory();
}

let reviewQueue = [];
let reviewIndex = 0;
let reviewFilter = "unrated";
let reviewUndoStack = [];
let totalWatchedCount = 0;
let totalRatedCount = 0;
// The Review tab and the Discover tab use one deck: the card and the buttons below it. The mode
// of the deck is `reviewFilter`: "unrated" or "all" for the Review tab, and "discover" for the
// Discover tab. The deck is in the tab that is open: see setDeckMode.
// The Discover deck shows random shows that the user does not have, and the user says
// "interested", "not interested" or "seen it" for each show. The answers are weak examples for
// the taste model: the library has only shows that the user selected, thus it has few shows
// that the user does not like. See /api/discover.
let discoverCounts = { interested: 0, not_interested: 0 };
// The user pressed "Seen it" for the card of now, and selects a tier
let discoverSeen = false;
let discoverLoading = false;
// The page sends an answer to the server. A second key in this time must not answer the same show again.
let discoverBusy = false;
// The deck gets this number of cards in one request
const DISCOVER_BATCH = 12;

// ---- The pictures of a show: frames of its episodes and of its trailer ----
// A card of the Discover deck shows them, so that the user sees how a show looks without a
// visit to AniList. The server gets the pictures from AniList: see /api/frames.
// The value of a show is null while the request for it is in progress.
const showPictures = new Map();
// The shows for which the server gave no pictures. The page does not ask for them again.
const pictureMisses = new Set();
// The frames that the viewer shows, and the position of the frame of now
let viewerFrames = [];
let viewerIndex = 0;

async function loadPictures(ids) {
  const wanted = ids.filter((id) => !showPictures.has(id) && !pictureMisses.has(id));
  if (!wanted.length) return;
  wanted.forEach((id) => showPictures.set(id, null));
  let res = null;
  try {
    const response = await fetch(`/api/frames?ids=${encodeURIComponent(wanted.join(","))}`);
    if (response.ok) res = await response.json();
  } catch (e) {
    console.error("Failed to load the pictures of the shows", e);
  }
  wanted.forEach((id) => {
    if (res && res[id]) {
      showPictures.set(id, res[id]);
    } else {
      showPictures.delete(id);
      pictureMisses.add(id);
    }
  });
  paintDeckFrames();
  preloadFrames(reviewQueue[reviewIndex + 1]);
}

// YouTube gives a small grey picture, 120 by 90, for a frame that it does not have
function isPlaceholder(img) {
  return img.naturalWidth > 0 && img.naturalWidth <= 120 && img.naturalHeight <= 90;
}

// Get the first frames of a show before its card comes, so that the card shows them immediately
function preloadFrames(show) {
  const pictures = show && showPictures.get(show.id);
  if (!pictures) return;
  pictures.frames.slice(0, 4).forEach((frame) => {
    const img = new Image();
    img.referrerPolicy = "no-referrer";
    img.src = frame.small;
  });
}

// Fill the row of frames of the card of now. The row has the same height in each state, thus
// the buttons below the card do not move when the pictures come.
function paintDeckFrames() {
  const box = $("#deck-frames");
  const show = reviewQueue[reviewIndex];
  if (!box || !show || box.dataset.show !== show.id) return;
  const pictures = showPictures.get(show.id);
  const trailer = $("#deck-trailer-link");
  if (trailer) {
    trailer.hidden = !(pictures && pictures.trailer);
    if (pictures && pictures.trailer) trailer.href = pictures.trailer;
  }
  const note = (text) => { box.innerHTML = `<p class="deck-frames-note">${text}</p>`; };
  if (!pictures) {
    if (pictureMisses.has(show.id)) note("The frames of this show did not load.");
    else box.innerHTML = '<div class="deck-frame empty"></div>'.repeat(3);
    return;
  }
  const frames = pictures.frames.filter((frame) => !frame.broken);
  if (!frames.length) {
    if (pictures.banner) {
      box.innerHTML = `<div class="deck-banner"><img src="${esc(pictures.banner)}" alt="Banner of the show" referrerpolicy="no-referrer"></div>`;
      box.querySelector("img").onerror = () => note("AniList has no frames of this show.");
    } else {
      note("AniList has no frames of this show.");
    }
    return;
  }
  box.innerHTML = frames.map((frame, n) => `
    <button type="button" class="deck-frame" data-frame="${n}" title="${esc(frame.label)}: show this frame larger">
      <img src="${esc(frame.small)}" alt="${esc(frame.label)}: a frame of the show" referrerpolicy="no-referrer" decoding="async">
      <span class="deck-frame-label">${esc(frame.label)}</span>
    </button>`).join("");
  box.scrollLeft = 0;
  box.querySelectorAll(".deck-frame").forEach((button) => {
    const frame = frames[Number(button.dataset.frame)];
    const img = button.querySelector("img");
    // A frame that does not load goes out of the row
    const drop = () => {
      frame.broken = true;
      paintDeckFrames();
    };
    img.onerror = drop;
    img.onload = () => { if (isPlaceholder(img)) drop(); };
    if (img.complete && isPlaceholder(img)) drop();
    button.onclick = () => openViewer(frames, frames.indexOf(frame));
  });
}

// The viewer shows one frame large. The arrow keys and the two buttons go to the other frames.
function openViewer(frames, index) {
  viewerFrames = frames.filter((frame) => !frame.broken);
  if (!viewerFrames.length) return;
  viewerIndex = Math.max(0, viewerFrames.indexOf(frames[index]));
  const dialog = $("#frame-viewer");
  dialog.innerHTML = `
    <button type="button" class="viewer-button viewer-close" aria-label="Close">✕</button>
    <button type="button" class="viewer-button viewer-prev" aria-label="The frame before">‹</button>
    <img class="viewer-picture" alt="" referrerpolicy="no-referrer">
    <button type="button" class="viewer-button viewer-next" aria-label="The next frame">›</button>
    <div class="viewer-caption" aria-live="polite"></div>`;
  dialog.querySelector(".viewer-close").onclick = () => dialog.close();
  dialog.querySelector(".viewer-prev").onclick = () => moveViewer(-1);
  dialog.querySelector(".viewer-next").onclick = () => moveViewer(1);
  paintViewer();
  if (!dialog.open) dialog.showModal();
  // The focus is on the button for the next frame, thus Space and Enter show the next frame.
  // Without this, the focus is on the button that closes the viewer.
  dialog.querySelector(viewerFrames.length > 1 ? ".viewer-next" : ".viewer-close").focus();
}

function paintViewer() {
  const dialog = $("#frame-viewer");
  const frame = viewerFrames[viewerIndex];
  const img = dialog.querySelector(".viewer-picture");
  // The large picture is not there for each frame. The small picture then takes its place.
  const useSmall = () => {
    if (img.dataset.small !== "1") {
      img.dataset.small = "1";
      img.src = frame.small;
    }
  };
  img.dataset.small = frame.large === frame.small ? "1" : "";
  img.onerror = useSmall;
  img.onload = () => { if (isPlaceholder(img)) useSmall(); };
  img.alt = `${frame.label}: a frame of the show`;
  img.src = frame.large;
  dialog.querySelector(".viewer-caption").textContent = `${frame.label} · ${viewerIndex + 1} of ${viewerFrames.length}`;
  dialog.querySelectorAll(".viewer-prev, .viewer-next").forEach((button) => { button.hidden = viewerFrames.length < 2; });
}

function moveViewer(step) {
  if (viewerFrames.length < 2) return;
  viewerIndex = (viewerIndex + step + viewerFrames.length) % viewerFrames.length;
  paintViewer();
}

function initViewer() {
  const dialog = $("#frame-viewer");
  // A click on the dark area around the picture closes the viewer
  dialog.onclick = (e) => { if (e.target === dialog) dialog.close(); };
  dialog.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      moveViewer(e.key === "ArrowLeft" ? -1 : 1);
    }
    // The keys of the deck must not answer the card while the viewer is open
    e.stopPropagation();
  });
  // The wheel of the mouse moves the row of frames to the side, when the row has more frames to show
  document.addEventListener("wheel", (e) => {
    const box = e.target.closest ? e.target.closest("#deck-frames") : null;
    if (!box || e.ctrlKey || Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
    const end = box.scrollWidth - box.clientWidth;
    if (end <= 0 || (e.deltaY < 0 && box.scrollLeft <= 0) || (e.deltaY > 0 && box.scrollLeft >= end - 1)) return;
    e.preventDefault();
    box.scrollLeft += e.deltaY;
  }, { passive: false });
}

async function loadReviewQueue() {
  try {
    if (reviewFilter === "discover") {
      reviewQueue = [];
      reviewIndex = 0;
      reviewUndoStack = [];
      discoverSeen = false;
      await loadDiscoverCards();
      return;
    }
    const filter = reviewFilter;
    const unratedOnly = filter === "unrated";
    const res = await (await fetch(`/api/review-queue?unrated_only=${unratedOnly}`)).json();
    // The user went to a different mode in the time of the request. The shows of this answer
    // are not the shows of the mode of now.
    if (reviewFilter !== filter) return;
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
  const p = $(reviewFilter === "discover" ? "#discover-progress" : "#deck-progress");
  if (!p) return;
  if (reviewFilter === "discover") {
    const answers = discoverCounts.interested + discoverCounts.not_interested;
    p.textContent = `${answers} answers · ${discoverCounts.interested} interested · ${discoverCounts.not_interested} not interested`;
    return;
  }
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
  paintDeckControls();

  if (reviewFilter === "discover" && reviewIndex >= reviewQueue.length) {
    wrap.innerHTML = `
      <div class="deck-card" style="align-items:center;justify-content:center;text-align:center;padding:48px 24px;">
        <p style="color:var(--muted);font-size:14px;margin:0;">${discoverLoading ? "Getting shows…" : "The Discover deck has no more shows."}</p>
      </div>`;
    updateActiveTierButton(null);
    return;
  }

  if (!reviewQueue.length || reviewIndex >= reviewQueue.length) {
    wrap.innerHTML = `
      <div class="deck-card" style="align-items:center;justify-content:center;text-align:center;padding:48px 24px;">
        <div style="max-width:380px;">
          ${vnWindow(reviewFilter === "unrated"
            ? "あら、もう全部に評価をつけたの？ 倫理君にしては仕事が早いじゃない。"
            : "これで最後よ。お疲れさま、倫理君。")}
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
      $("#deck-review-all-btn").onclick = () => setDeckMode("all");
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
    ? `<img src="${esc(largePoster(show.poster))}" data-small="${esc(show.poster)}" alt="${esc(main)}" onerror="${POSTER_ERROR}">
       <div class="poster-fallback" aria-hidden="true">${esc(main[0] || "?")}</div>`
    : `<div class="poster-fallback show" aria-hidden="true">${esc(main[0] || "?")}</div>`;

  const metaItems = [];
  if (show.format) metaItems.push(esc(show.format.toUpperCase()));
  if (show.year) metaItems.push(show.year);
  if (show.studios && show.studios.length) metaItems.push(`Studio: <b>${esc(show.studios.slice(0, 2).join(", "))}</b>`);
  if (scoreVal) metaItems.push(`★ ${scoreVal}`);
  if (matchHtml(show)) metaItems.push(matchHtml(show));
  if (guessHtml(show)) metaItems.push(guessHtml(show));

  const tagsHtml = (show.tags || []).slice(0, 5).map(t => `<span class="chip">${esc(t)}</span>`).join("");
  // A card of the Discover deck has a row of frames, and links to AniList and to the trailer
  const discover = reviewFilter === "discover";
  const linksHtml = discover
    ? `<a class="btn-action" id="deck-trailer-link" target="_blank" rel="noopener noreferrer" hidden>Trailer ↗</a>`
      + (show.anilist_id ? `<a class="btn-action" href="https://anilist.co/anime/${show.anilist_id}" target="_blank" rel="noopener noreferrer">AniList ↗</a>` : "")
    : "";

  wrap.innerHTML = `
    <div class="deck-card${discover ? " with-frames" : ""}">
      <div class="deck-poster-wrap poster-box">
        ${posterHtml}
      </div>
      <div class="deck-info">
        <div class="deck-meta-top">
          <span>${reviewFilter === "discover" ? "You do not have this show" : show.source === "library" ? "Local library" : "Watched"}</span>
          <div style="display:flex;align-items:center;gap:6px;">
            ${tierBadge}
            ${reviewFilter === "discover" ? "" : `<span style="font-size:11.5px;color:var(--muted);">${reviewIndex + 1} / ${reviewQueue.length}</span>`}
          </div>
        </div>
        <h3 class="deck-title">${esc(main)}</h3>
        ${sub ? `<div class="deck-sub">${esc(sub)}</div>` : ""}
        <div class="deck-meta-details">${metaItems.join(" · ")}</div>
        <div class="deck-synopsis">${formatOverview(show.overview)}</div>
        ${tagsHtml ? `<div class="deck-tags">${tagsHtml}</div>` : ""}
        <div class="deck-bottom-actions">
          ${linksHtml}
          <button class="btn-action" id="deck-card-details">Details</button>
        </div>
      </div>
      ${discover ? `<div class="deck-frames" id="deck-frames" data-show="${esc(show.id)}" aria-label="Frames of the show"></div>` : ""}
    </div>`;

  $("#deck-card-details").onclick = () => openModal(show);
  if (discover) {
    paintDeckFrames();
    loadPictures([show.id]);
    preloadFrames(reviewQueue[reviewIndex + 1]);
  }
  updateActiveTierButton(show.tier);
}

async function rateReviewShow(tier) {
  if (!reviewQueue.length || reviewIndex >= reviewQueue.length) return;
  if (reviewFilter === "discover") {
    // In the Discover deck a tier is for a show that the user saw
    if (discoverSeen) await seenDiscover(tier);
    return;
  }
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
  if (reviewFilter === "discover") {
    await undoDiscover();
    return;
  }
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
  if (reviewFilter === "discover") {
    // After "Seen it", Skip saves the show as watched without a tier
    if (discoverSeen) seenDiscover(null);
    else if (reviewIndex < reviewQueue.length) nextDiscoverCard();
    return;
  }
  if (reviewIndex < reviewQueue.length) {
    reviewIndex++;
    updateDeckProgress();
    renderDeckCard();
  }
}

// Get the next cards of the Discover deck and put them at the end of the queue
async function loadDiscoverCards() {
  if (discoverLoading) return;
  discoverLoading = true;
  renderDeckCard();
  try {
    const res = await (await fetch(`/api/discover?count=${DISCOVER_BATCH}`)).json();
    // The user went to a different mode in the time of the request
    if (reviewFilter === "discover") {
      const have = new Set(reviewQueue.map((show) => show.id));
      discoverCounts = res.counts || discoverCounts;
      const cards = (res.cards || []).filter((show) => !have.has(show.id));
      reviewQueue.push(...cards);
      // One request gets the pictures of all new cards. The deck does not wait for it.
      loadPictures(cards.map((show) => show.id));
    }
  } catch (e) {
    console.error("Failed to load the Discover deck", e);
  }
  discoverLoading = false;
  updateDeckProgress();
  renderDeckCard();
}

// The Review deck has the tier buttons. The Discover deck has its three answers, and it shows
// the tier buttons only after "Seen it".
function paintDeckControls() {
  const discover = reviewFilter === "discover";
  const tiers = document.querySelector(".deck-controls .tier-buttons");
  if (tiers) tiers.hidden = discover && !discoverSeen;
  const answers = $("#discover-buttons");
  if (answers) answers.hidden = !discover || discoverSeen;
  const hint = $("#discover-hint");
  if (hint) {
    hint.hidden = !discover;
    hint.textContent = discoverSeen
      ? "You saw this show: give it a tier, or press Skip for no tier. Esc goes back."
      : "Keys: N not interested · I interested · W seen it · Space skip · Backspace undo";
  }
  if ($("#deck-skip")) $("#deck-skip").title = discover ? "Space" : "Space or →";
  if ($("#deck-undo")) $("#deck-undo").title = discover ? "Backspace" : "Backspace or ←";
}

function nextDiscoverCard() {
  discoverSeen = false;
  reviewIndex++;
  // Get more cards before the deck is empty
  if (reviewIndex >= reviewQueue.length - 2) loadDiscoverCards();
  updateDeckProgress();
  renderDeckCard();
}

// Save the answer of the user for a show: true = interested, false = not interested, null = no
// answer. `source` is "deck" for the Discover deck and "page" for a button of a page.
async function setInterest(show, value, source) {
  const res = await fetch("/api/interest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: show.id, value, source }),
  });
  if (!res.ok) throw new Error(`answer failed: ${res.status}`);
  const data = await res.json();
  show.interest = data.interest;
  show.dismissed = data.dismissed;
  discoverCounts = data.counts || discoverCounts;
  noteWatchList(show);
  // An answer changes the taste model, thus the match of the other shows changes
  scheduleMapMatch(1200);
}

async function answerDiscover(value) {
  if (reviewFilter !== "discover" || discoverSeen || discoverBusy || reviewIndex >= reviewQueue.length) return;
  const show = reviewQueue[reviewIndex];
  discoverBusy = true;
  try {
    await setInterest(show, value, "deck");
  } catch (e) {
    console.error("Failed to save the answer", e);
    return;
  } finally {
    discoverBusy = false;
  }
  reviewUndoStack.push({ show, kind: "answer" });
  nextDiscoverCard();
}

// "Seen it": the show goes to the watched shows of the user, with a tier or without one
async function seenDiscover(tier) {
  if (discoverBusy || reviewIndex >= reviewQueue.length) return;
  const show = reviewQueue[reviewIndex];
  const json = { "Content-Type": "application/json" };
  discoverBusy = true;
  try {
    await apiWrite("/api/watched", { method: "POST", headers: json, body: JSON.stringify({ id: show.id, watched: true }) });
    if (tier) await apiWrite("/api/weights", { method: "POST", headers: json, body: JSON.stringify({ id: show.id, tier }) });
  } catch (e) {
    console.error("Failed to save the watched show", e);
    return;
  } finally {
    discoverBusy = false;
  }
  show.owned = 1;
  show.manual_watched = 1;
  show.tier = tier;
  const title = titles.find((x) => x.id === show.id);
  if (title) Object.assign(title, { owned: 1, manual_watched: 1, tier });
  reviewUndoStack.push({ show, kind: "seen", tier });
  nextDiscoverCard();
}

// Undo in the Discover deck: go back from the tier buttons, or take the last answer back
async function undoDiscover() {
  if (discoverSeen) {
    discoverSeen = false;
    renderDeckCard();
    return;
  }
  if (discoverBusy || !reviewUndoStack.length) return;
  const last = reviewUndoStack.pop();
  const show = last.show;
  discoverBusy = true;
  try {
    if (last.kind === "answer") {
      await setInterest(show, null, "deck");
    } else {
      if (last.tier) await apiWrite(`/api/weights?id=${encodeURIComponent(show.id)}`, { method: "DELETE" });
      await apiWrite("/api/watched", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: show.id, watched: false }),
      });
      show.owned = 0;
      show.manual_watched = 0;
      show.tier = null;
      const title = titles.find((x) => x.id === show.id);
      if (title) Object.assign(title, { owned: 0, manual_watched: 0, tier: null });
    }
  } catch (e) {
    console.error("Failed to take the answer back", e);
  } finally {
    discoverBusy = false;
  }
  reviewIndex = Math.max(0, reviewQueue.indexOf(show));
  updateDeckProgress();
  renderDeckCard();
}

// ---- The watch list: the shows with the answer "interested" that the user does not have ----
// A round button floats at the bottom right of the window while the Discover tab is open. It
// opens the list above it.
let watchList = [];
let watchOpen = false;
// The shows that the user took off the list while the list was open. Their rows stay in the
// list with a button that puts the show back, so that a wrong click loses nothing.
const watchGone = new Set();

async function loadWatchList() {
  try {
    const res = await (await fetch("/api/interest")).json();
    if (Array.isArray(res)) {
      watchList = res;
      watchGone.clear();
    }
  } catch (e) {
    console.error("Failed to load the watch list", e);
  }
  renderWatchList();
}

// Keep the list of the page correct after an answer for a show
function noteWatchList(show) {
  const at = watchList.findIndex((s) => s.id === show.id);
  if (show.interest === 1 && !show.owned) {
    watchGone.delete(show.id);
    if (at < 0) {
      watchList.push(show);
      watchList.sort((a, b) => (b.match ?? 0) - (a.match ?? 0));
    }
  } else if (at >= 0 && !watchGone.has(show.id)) {
    watchList.splice(at, 1);
  }
  renderWatchList();
}

// The detail window can change a show of the list: a tier, "watched" or "not interested".
// After the window closes, the list keeps only the shows that are on the watch list.
function syncWatchList() {
  watchList = watchList.filter((s) => watchGone.has(s.id) || (s.interest === 1 && !s.owned && !s.dismissed));
  renderWatchList();
}

function renderWatchList() {
  const count = watchList.filter((s) => !watchGone.has(s.id)).length;
  const button = $("#watch-button");
  if (!button) return;
  $("#watch-count").textContent = count;
  button.setAttribute("aria-label", `Watch list: ${count} ${count === 1 ? "show" : "shows"}`);
  if (!watchOpen) return;
  $("#watch-total").textContent = `${count} ${count === 1 ? "show" : "shows"}`;
  const list = $("#watch-list");
  if (!watchList.length) {
    list.innerHTML = '<li class="watch-empty">Your watch list is empty. Answer "Interested" for a show that you want to watch.</li>';
    return;
  }
  list.innerHTML = watchList.map((show) => {
    const { main, sub } = displayTitles(show);
    const gone = watchGone.has(show.id);
    const meta = [];
    if (show.format) meta.push(esc(show.format.toUpperCase().replace("_", " ")));
    if (show.year) meta.push(show.year);
    if (formatMatch(show.match) != null) meta.push(`${formatMatch(show.match)}% match`);
    const poster = show.poster
      ? `<img src="${esc(show.poster)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.display='none'">`
      : "";
    return `
      <li class="watch-row${gone ? " gone" : ""}" data-id="${esc(show.id)}">
        <button type="button" class="watch-open" title="Show the details">
          <span class="watch-poster">${poster}</span>
          <span class="watch-text">
            <span class="watch-title">${esc(main)}</span>
            ${sub ? `<span class="watch-sub">${esc(sub)}</span>` : ""}
            <span class="watch-meta">${meta.join(" · ")}</span>
          </span>
        </button>
        <button type="button" class="watch-remove" title="${gone ? "Put this show back on the watch list" : "Take this show off the watch list"}"
          aria-label="${gone ? "Put" : "Take"} ${esc(main)} ${gone ? "back on" : "off"} the watch list">${gone ? "Undo" : "✕"}</button>
      </li>`;
  }).join("");
}

// Take a show off the watch list, or put it back
async function toggleWatchRow(show) {
  const back = watchGone.has(show.id);
  if (!back) watchGone.add(show.id);
  try {
    await setInterest(show, back ? true : null, "page");
  } catch (e) {
    console.error("Failed to change the watch list", e);
    if (!back) watchGone.delete(show.id);
    renderWatchList();
  }
  updateDeckProgress();
}

function setWatchOpen(open) {
  if (watchOpen === open) return;
  watchOpen = open;
  $("#watch-panel").hidden = !open;
  $("#watch-button").setAttribute("aria-expanded", open ? "true" : "false");
  if (open) {
    renderWatchList();
    // The server has the correct order and the matches of now
    loadWatchList();
    $("#watch-list").focus({ preventScroll: true });
  } else {
    // A show that the user took off the list does not come back after the list closes
    watchList = watchList.filter((s) => !watchGone.has(s.id));
    watchGone.clear();
  }
}

function initWatchList() {
  $("#watch-button").onclick = () => setWatchOpen(!watchOpen);
  $("#watch-close").onclick = () => {
    setWatchOpen(false);
    $("#watch-button").focus({ preventScroll: true });
  };
  $("#watch-list").onclick = (e) => {
    const row = e.target.closest(".watch-row");
    const show = row && watchList.find((s) => s.id === row.dataset.id);
    if (!show) return;
    if (e.target.closest(".watch-remove")) toggleWatchRow(show);
    else openModal(show);
  };
  // A click outside the list closes it. The detail window and the viewer of the frames are not "outside".
  document.addEventListener("pointerdown", (e) => {
    if (!watchOpen || !e.target.closest) return;
    if (!e.target.closest("#watch-panel, #watch-button, dialog")) setWatchOpen(false);
  });
  $("#detail-modal").addEventListener("close", syncWatchList);
}

// The mode of the Review tab that the user selected last: "unrated" or "all"
let reviewMode = "unrated";
// The cards of the Discover deck, in the time that the deck shows the shows of the user
let discoverStash = null;

// Put the deck in the tab of the mode, and show the cards of the mode. `mode` is "unrated" or
// "all" for the Review tab, and "discover" for the Discover tab.
function setDeckMode(mode) {
  const before = reviewFilter;
  if (before === "discover" && mode !== "discover") {
    discoverStash = { queue: reviewQueue, index: reviewIndex, undo: reviewUndoStack };
  }
  if (mode !== "discover") reviewMode = mode;
  reviewFilter = mode;
  discoverSeen = false;
  $(mode === "discover" ? "#discover-slot" : "#review-slot").appendChild($("#deck-host"));
  $("#deck-filter-unrated").classList.toggle("active", reviewMode === "unrated");
  $("#deck-filter-all").classList.toggle("active", reviewMode === "all");
  if (mode === "discover") {
    // The button of the watch list has the number of its shows
    loadWatchList();
    // The Discover deck keeps its cards when the user opens a different tab. Thus the user
    // comes back to the same card, and the deck does not draw a card that the user did not answer.
    let kept = before === "discover";
    if (!kept && discoverStash) {
      reviewQueue = discoverStash.queue;
      reviewIndex = discoverStash.index;
      reviewUndoStack = discoverStash.undo;
      discoverStash = null;
      kept = true;
    }
    if (kept && reviewIndex < reviewQueue.length) {
      updateDeckProgress();
      renderDeckCard();
      return;
    }
  }
  loadReviewQueue();
}

function initReviewDeck() {
  $("#deck-filter-unrated").onclick = () => setDeckMode("unrated");
  $("#deck-filter-all").onclick = () => setDeckMode("all");
  $("#discover-no").onclick = () => answerDiscover(false);
  $("#discover-yes").onclick = () => answerDiscover(true);
  $("#discover-seen").onclick = () => {
    if (reviewIndex >= reviewQueue.length) return;
    discoverSeen = true;
    renderDeckCard();
  };

  document.querySelectorAll(".btn-tier").forEach((btn) => {
    btn.onclick = () => {
      const tier = btn.dataset.tier;
      rateReviewShow(tier);
    };
  });

  $("#deck-undo").onclick = () => undoReview();
  $("#deck-skip").onclick = () => skipReview();

  initViewer();
  initWatchList();

  document.addEventListener("keydown", (e) => {
    if ($("#tab-review").hidden && $("#tab-discover").hidden) return;
    if ($("#detail-modal").open || $("#frame-viewer").open) return;
    // While the watch list is open, the keys of the deck do nothing, and Escape closes the list
    if (watchOpen) {
      if (e.key === "Escape") {
        e.preventDefault();
        setWatchOpen(false);
        $("#watch-button").focus({ preventScroll: true });
      }
      return;
    }
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA") return;

    const key = e.key.toUpperCase();
    const code = e.code || "";
    if (reviewFilter === "discover" && !discoverSeen) {
      // The keys of the Discover deck. A key with Ctrl, Alt or the command key is a command of the browser.
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (key === "N" || e.key === "ArrowLeft") answerDiscover(false);
      else if (key === "I" || e.key === "ArrowRight") answerDiscover(true);
      else if (key === "W") $("#discover-seen").click();
      else if (e.key === " ") skipReview();
      else if (e.key === "Backspace") undoReview();
      else return;
      e.preventDefault();
      return;
    }
    if (reviewFilter === "discover" && e.key === "Escape") {
      e.preventDefault();
      undoReview();
      return;
    }
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
    renderRatingsSummary();
  } catch (e) {
    console.error("Failed to load ratings", e);
  }
}

// Draw the numbers and the cards of the Ratings tab from the lists that the page has
function renderRatingsSummary() {
  if ($("#count-manual")) $("#count-manual").textContent = manualShows.length;
  if ($("#count-dismissed")) $("#count-dismissed").textContent = dismissedShows.length;

  const counts = { S: 0, A: 0, B: 0, C: 0, D: 0 };
  ratedShows.forEach((s) => {
    if (s.tier && counts[s.tier] !== undefined) counts[s.tier]++;
  });

  const badge = $("#ratings-count-badge");
  if (badge) badge.textContent = `${ratedShows.length} ${ratedShows.length === 1 ? "show" : "shows"}`;

  ["S", "A", "B", "C", "D"].forEach((tier) => {
    const el = $(`#count-tier-${tier.toLowerCase()}`);
    if (el) el.textContent = counts[tier];
  });

  document.querySelectorAll("#ratings-tier-pills .pill").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tier === ratingsTierFilter);
  });

  renderRatingsGrid();
}

// The Ratings tab after a change of a tier. The page changes its own lists and draws them again:
// this needs no request, thus it is immediate. The matches of the other shows change a little
// after each change of a tier, thus the page gets the lists from the server again a short time
// after the last change.
let ratingsReloadTimer = null;

function updateRatingsAfterEdit(r) {
  const tier = r.tier || null;
  const index = ratedShows.findIndex((s) => s.id === r.id);
  if (tier && index >= 0) ratedShows[index].tier = tier;
  else if (tier) ratedShows.push(r);
  else if (index >= 0) ratedShows.splice(index, 1);
  [manualShows, dismissedShows].forEach((list) => {
    const item = list.find((s) => s.id === r.id);
    if (item) item.tier = tier;
  });
  renderRatingsSummary();
  clearTimeout(ratingsReloadTimer);
  ratingsReloadTimer = setTimeout(loadRatings, 2500);
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
      return (b.match ?? 0) - (a.match ?? 0);
    } else if (ratingsSort === "match") {
      return (b.match ?? 0) - (a.match ?? 0);
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
      box.innerHTML = `<div style="grid-column:1/-1;color:var(--muted);text-align:center;padding:40px 20px;">
          ${vnWindow("切り捨てた作品はまだ一つもないのね。優しいのか、優柔不断なのか……。")}
          <p style="margin:0;">No removed recommendations. In the Recommendations tab, click ✕ on a show that you do not want.</p></div>`;
    } else if (ratingsSource === "manual" && ratingsTierFilter === "all") {
      box.innerHTML = `<div style="grid-column:1/-1;color:var(--muted);text-align:center;padding:40px 20px;">
          ${vnWindow("ライブラリの外で観た作品があるなら、正直に白状なさい。")}
          <p style="margin:0;">No manually added shows yet. When you watch a show outside your local library, find it and click "+ Add to Watched".</p></div>`;
    } else if (!ratedShows.length) {
      box.innerHTML = `
        <div style="grid-column:1/-1;text-align:center;padding:48px 20px;color:var(--muted);">
          ${vnWindow("まだ何も評価していないのね。話はそれからよ、倫理君。")}
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
    // The story of the list plays only on the Recommendations tab
    closeStory();
    // The button of the watch list is only on the Discover tab
    setWatchOpen(false);
    $("#watch-button").hidden = b.dataset.tab !== "discover";
    if (b.dataset.tab === "review") setDeckMode(reviewMode);
    if (b.dataset.tab === "discover") setDeckMode("discover");
    if (b.dataset.tab === "ratings") loadRatings();
    if (b.dataset.tab === "recs") recs();
    if (b.dataset.tab === "profile") profile();
  };
});

// ---- The Saekano look
// A message window as in a visual novel: a name plate and one line. The lines are new text in the
// voice of Utaha Kasumigaoka, who calls the user "倫理君" (rinri-kun).
function vnWindow(line) {
  return `<div class="vn-window" lang="ja"><span class="vn-name">霞ヶ丘詩羽</span><p class="vn-line">${esc(line)}</p></div>`;
}

// Cherry blossom petals fall behind the page header. The values are fixed, not random, so that
// the page looks the same each time. The style sheet hides the petals if the setting is off or
// if the system asks for less motion.
function initPetals() {
  const box = $("#petals");
  if (!box) return;
  // position (% of the width), size (px), time of one fall (s), start (s), drift (px), angle (deg), opacity
  const petals = [
    [3, 11, 15, 2, 70, 20, 0.7], [11, 8, 19, 9, 40, 110, 0.55], [18, 12, 13, 5, 90, 200, 0.75],
    [26, 9, 17, 12, 55, 60, 0.6], [34, 7, 21, 1, 35, 300, 0.5], [42, 10, 14, 7, 80, 150, 0.7],
    [50, 8, 18, 14, 45, 250, 0.55], [58, 12, 16, 3, 95, 30, 0.75], [66, 9, 20, 10, 50, 180, 0.6],
    [74, 11, 13, 6, 75, 90, 0.7], [82, 7, 22, 16, 30, 330, 0.5], [89, 10, 15, 11, 65, 130, 0.65],
    [95, 9, 18, 4, 40, 270, 0.6], [46, 6, 24, 18, 25, 10, 0.45],
  ];
  box.innerHTML = petals.map(([x, size, time, start, drift, turn, alpha]) =>
    `<i class="petal" style="--x:${x}%;--size:${size}px;--time:${time}s;--delay:-${start}s;--drift:${drift}px;--turn:${turn}deg;--alpha:${alpha}"></i>`
  ).join("");
}

// ---- Help for the tiers
// The Review tab and the Ratings tab have a card with one question for each tier. The questions
// say what a tier does in the recommender: S, A and B give more shows like the show (with the
// weights 2, 1.5 and 1), and C and D give fewer. D also blocks a show that is almost the same.
const TIER_HELP_KEY = "rinrikun-tier-help";
const TIER_QUESTIONS = [
  ["S", "Would I watch it again, or do I measure other shows by it?"],
  ["A", "Would I be glad if my next show was like this one?"],
  ["B", "Was it worth my time, and is one more show like it fine?"],
  ["C", "Would I be disappointed if the list gave me a show like this?"],
  ["D", "Is a show that is almost the same a certain no?"],
];

function initTierHelp() {
  // The user can close the card. The browser keeps this, and the two cards have the same state.
  let closed = false;
  try { closed = localStorage.getItem(TIER_HELP_KEY) === "closed"; } catch (e) {}
  const rows = TIER_QUESTIONS.map(([tier, question]) =>
    `<div class="tier-help-row"><dt><span class="tier-pill tier-${tier.toLowerCase()}">${tier}</span></dt><dd>${esc(question)}</dd></div>`
  ).join("");
  document.querySelectorAll(".tier-help-slot").forEach((slot) => {
    slot.innerHTML = `
      <details class="tier-help"${closed ? "" : " open"}>
        <summary>Which tier?</summary>
        <dl class="tier-help-list">${rows}</dl>
      </details>`;
    const card = slot.querySelector("details");
    card.addEventListener("toggle", () => {
      try { localStorage.setItem(TIER_HELP_KEY, card.open ? "open" : "closed"); } catch (e) {}
      document.querySelectorAll(".tier-help").forEach((other) => {
        if (other !== card && other.open !== card.open) other.open = card.open;
      });
    });
  });
}

// ---- Settings
// Each setting is a choice between options. The first option is the default. The value of a
// setting is an attribute of the root element (data-<key>), so that the style sheet can use it.
// The browser keeps the values. To add a setting: add an entry to this list, with a picture for
// each option, and add its rules to the style sheet. A setting that needs more than style rules
// has an `apply` function.
//
// A setting has no text below its title. Its tooltip shows one picture for each option. The page
// draws the pictures, thus they have the colors of the theme and the typefaces of the page.
const SETTINGS_KEY = "rinrikun-settings";

// The picture of a typeface option: a heading, the title of a show and a line of other text
function fontPicture(kind, about) {
  return `<div class="tip-picture tip-picture-font ${kind}" role="img" aria-label="${about}">
      <span class="tpf-heading">Taste profile</span>
      <span class="tpf-title" lang="ja">冴えない彼女の育てかた</span>
      <span class="tpf-meta">2015 · Comedy, Romance</span>
    </div>`;
}

// The picture of a petals option: the page header, with petals or without them
function petalsPicture(on, about) {
  // The position, the size and the angle of each petal
  const petals = [[14, 14, 1, 20], [38, 42, 0.8, 110], [57, 9, 0.7, 200], [100, 44, 1, 60], [121, 16, 0.8, 300],
    [141, 54, 0.9, 150], [129, 74, 0.6, 250], [22, 68, 0.7, 330]];
  const shapes = on ? petals.map(([x, y, size, turn]) =>
    `<path d="M0 0C5-1 9 2 10 7C4 8 0 5 0 0Z" transform="translate(${x} ${y}) rotate(${turn}) scale(${size})" fill="#f0a6ba" opacity="0.9"/>`).join("") : "";
  const lobes = [0, 72, 144, 216, 288].map((turn) => `<circle cx="80" cy="18" r="7.5" transform="rotate(${turn} 80 26)"/>`).join("");
  return `<svg class="tip-picture tip-picture-sky" viewBox="0 0 160 90" role="img" aria-label="${about}">
      ${shapes}
      <g fill="currentColor">${lobes}</g>
      <text x="80" y="59" text-anchor="middle" font-size="13" font-weight="200" fill="currentColor" lang="ja">りんりくん</text>
      <rect x="36" y="69" width="88" height="12" rx="6" fill="none" stroke="currentColor" stroke-opacity="0.28"/>
    </svg>`;
}

// The picture of a match gradient option: posters on a map
function gradientPicture(on, about) {
  const colors = ["#d98a8a", "#8aa9d9", "#93c58d", "#d9b98a", "#b392c5", "#8ac5bf", "#c592ad", "#a9a9a9"];
  let tiles = "";
  for (let row = 0; row < 3; row++) {
    for (let col = 0; col < 7; col++) {
      const place = `x="${8 + col * 21}" y="${7 + row * 26}" width="18" height="23" rx="2.5"`;
      tiles += `<rect ${place} fill="${colors[(col * 3 + row * 5) % 8]}"/>`;
      // With the gradient, a poster is darker if it is farther from the best match. The map
      // makes a poster darker in the same way: with black above it.
      const far = Math.hypot(col - 2, (row - 1) * 1.3);
      if (on) tiles += `<rect ${place} fill="#000" opacity="${Math.min(1 - MATCH_DARK, far / 3.4).toFixed(2)}"/>`;
    }
  }
  return `<svg class="tip-picture" viewBox="0 0 160 90" role="img" aria-label="${about}">${tiles}</svg>`;
}

const SETTINGS = [
  {
    key: "font",
    title: "Typeface",
    options: [
      { value: "mixed", label: "Serif titles", picture: () => fontPicture("serif", "Titles and headings in a serif typeface") },
      { value: "sans", label: "Noto Sans JP everywhere", picture: () => fontPicture("sans", "All text in Noto Sans JP") },
    ],
    apply: applyFontSetting,
  },
  {
    key: "petals",
    title: "Cherry blossom petals",
    options: [
      { value: "on", label: "On", picture: () => petalsPicture(true, "Petals fall behind the page header") },
      { value: "off", label: "Off", picture: () => petalsPicture(false, "A page header without petals") },
    ],
  },
  {
    key: "gradient",
    title: "Match gradient on the maps",
    options: [
      { value: "off", label: "Off", picture: () => gradientPicture(false, "All posters have their full brightness") },
      { value: "on", label: "On", picture: () => gradientPicture(true, "A poster is brighter for a higher match") },
    ],
    apply: applyGradientSetting,
  },
];
const settings = {};

// The tooltip of a setting: one picture for each option, with a frame around the selected option
TIP_CONTENT.setting = (el) => {
  const setting = SETTINGS.find((x) => x.key === el.dataset.setting);
  if (!setting) return "";
  return `<div class="tip-previews">${setting.options.map((o) => `
      <figure class="tip-preview${o.value === settings[setting.key] ? " current" : ""}">
        ${o.picture()}
        <figcaption>${esc(o.label)}</figcaption>
      </figure>`).join("")}
    </div>`;
};

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

// Each map has a button for the match gradient. Paint the buttons, get the match values and draw
// the maps again.
function applyGradientSetting(value) {
  const on = value === "on";
  document.querySelectorAll(".vector-gradient-toggle").forEach((btn) => {
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-pressed", String(on));
  });
  if (on) scheduleMapMatch();
  activeVectorMaps.forEach((ctrl) => ctrl.scheduleDraw());
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
  // The tooltip of a setting that is open now. The new elements replace its element.
  const open = tipTarget && tipTarget.dataset.tipRich === "setting" && list.contains(tipTarget)
    ? { key: tipTarget.dataset.setting, part: tipTarget.classList.contains("info-dot") ? ".info-dot" : ".setting-options" }
    : null;
  // The option that has the keyboard focus now
  const focused = list.contains(document.activeElement) ? document.activeElement.dataset : null;
  list.innerHTML = SETTINGS.map((setting) => {
    const current = setting.options.find((o) => o.value === settings[setting.key]);
    const pills = setting.options.map((o) => `
          <button class="pill ${o === current ? "active" : ""}" data-key="${setting.key}" data-value="${o.value}" aria-pressed="${o === current}">${esc(o.label)}</button>`).join("");
    // The "i" and the options show the pictures of the options. A click on an option selects it.
    return `
      <div class="setting-row" data-setting="${setting.key}">
        <div class="setting-info">
          <span class="setting-title">${esc(setting.title)}</span><button type="button" class="info-dot" data-tip-rich="setting" data-setting="${setting.key}" aria-label="Show a picture of each option">i</button>
        </div>
        <div class="filter-pills setting-options" role="group" aria-label="${esc(setting.title)}" data-tip-rich="setting" data-setting="${setting.key}" data-tip-pass>${pills}
        </div>
      </div>`;
  }).join("");
  list.querySelectorAll(".pill").forEach((btn) => {
    btn.onclick = () => setSetting(btn.dataset.key, btn.dataset.value);
  });
  if (focused && focused.key) {
    const btn = list.querySelector(`.pill[data-key="${focused.key}"][data-value="${focused.value}"]`);
    if (btn) btn.focus();
  }
  if (open) {
    // Show the tooltip again, with the frame around the new selection
    const el = list.querySelector(`.setting-row[data-setting="${open.key}"] ${open.part}`);
    if (el) showTip(el);
    else hideTip();
  }
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

initPetals();
initTierHelp();
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
