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
  d.onclick = () => useSeed(r);
  return d;
}

async function profile() {
  const p = await (await fetch("/api/profile")).json();
  const el = $("#tab-profile");
  el.innerHTML = `<h2>Taste profile — ${p.owned_count} owned of ${p.total_count} indexed</h2>
    <h2>Dominant tags</h2><div class="tagbar">${p.tag_summary.map(([t, c]) => `<span class="chip">${esc(t)} <b>${c}</b></span>`).join("")}</div>
    <h2>Defining shows (nearest to taste center)</h2>`;
  const cards = document.createElement("div");
  cards.className = "cards";
  p.defining_shows.forEach((r) => cards.appendChild(card(r, `${r.similarity}% to center`)));
  el.appendChild(cards);
}

let titles = [];
async function initSearch() {
  titles = await (await fetch("/api/shows")).json();
  const q = $("#q");
  q.oninput = () => {
    const v = q.value.toLowerCase();
    if (v.length < 2) return ($("#qlist").innerHTML = "");
    $("#qlist").innerHTML = "";
    titles.filter((t) => (t.title + " " + t.title_native).toLowerCase().includes(v)).slice(0, 8)
      .forEach((t) => {
        const d = document.createElement("div");
        d.textContent = `${t.title} ${t.owned ? "✓" : ""}`;
        d.onclick = () => runSimilar(t);
        $("#qlist").appendChild(d);
      });
  };
}

async function runSimilar(t) {
  $("#qlist").innerHTML = "";
  $("#q").value = t.title;
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
