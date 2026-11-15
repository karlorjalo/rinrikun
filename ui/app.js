const $ = (s) => document.querySelector(s);
const esc = (s) => (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function card(r, why) {
  const d = document.createElement("div");
  d.className = "card";
  d.innerHTML = `
    <img src="${esc(r.poster || "")}" loading="lazy" onerror="this.style.visibility='hidden'">
    <div>
      <div class="t">${esc(r.title)} ${r.owned ? '<span class="badge">owned</span>' : ""}</div>
      <div class="m">${esc(r.title_native)} ${r.year || ""} · ${esc((r.genres || []).slice(0, 3).join(", "))}</div>
      <div class="m">sim ${r.similarity}% · score ${r.score ?? "?"}</div>
      <div class="m">${why || (r.shared_tags || []).map((t) => `<span class="badge">${esc(t)}</span>`).join("")}</div>
    </div>`;
  d.onclick = () => useSeed(r);
  return d;
}

async function profile() {
  const p = await (await fetch("/api/profile")).json();
  const el = $("#tab-profile");
  el.innerHTML = `<h2>Taste profile — ${p.owned_count} owned of ${p.total_count} indexed</h2>
    <h2>Dominant tags</h2><div class="tagbar">${p.tag_summary.map(([t, c]) => `<span>${esc(t)} <b>${c}</b></span>`).join("")}</div>
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
