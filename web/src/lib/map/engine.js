// @ts-nocheck
// The map of the shows: a canvas that the user can zoom and move.
//
// This file came from the map code of the first page of the app, as one module. The draw code and
// the pointer code are the same. The types are in engine.d.ts. The Svelte component
// components/map/VectorMap.svelte makes the canvas and calls createVectorMap.
//
// The map makes three controls in the box of the canvas: the zoom buttons, a hint, and the
// search box. Their style is in map.css.
import { displayTitles, formatMatch } from "#lib/format.js";
import { searchRank, searchWords, showSearchText } from "#lib/search.js";
import { MATCH_DARK } from "#lib/settings-list.js";

const esc = (s) => (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ---- The match gradient
// With the setting "Match gradient" on, a poster on a map is brighter for a higher match, and a
// dot of the catalog is stronger.

// The dots of the catalog have this number of steps of strength
const GRADIENT_STEPS = 8;

// The brightness of a poster for a match in percent, from MATCH_DARK to 1. The curve is steep at
// the high end. The match is a rank in the catalog, thus one half of the catalog is below 50, and
// the shows of interest are in the last part.
function matchBrightness(match) {
  const part = Math.max(0, Math.min(1, match / 100));
  return MATCH_DARK + (1 - MATCH_DARK) * part * part;
}

// The opacity of the dot of a show that does not stay in a step of the story of the list:
// see components/map/ListStory.svelte
const STORY_FAINT = 0.06;

// ---- The posters
const posterImgCache = new Map();
const posterListeners = new Map();
// The cache keeps this number of posters. The close view of the map asks for the posters of all
// shows in view (about 700 when the posters appear), and the catalog has thousands of shows.
const POSTER_CACHE_MAX = 1600;
// The posters that load in this time (in milliseconds) after the first one use one draw of the map
const POSTER_DRAW_DELAY = 150;

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

// ---- The map
export function createVectorMap(canvas, tooltip, data, options = {}) {
  const {
    highlightIds = [],
    highlightLabel = "Highlighted",
    highlightKind = "recommended",
    onOpen = () => {},
    gradient = () => false,
  } = options;

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
  // The timer of the draw for the posters that load (schedulePosterDraw)
  let posterTimer = null;
  // The size of the box at the last draw (see the ResizeObserver below)
  let drawnW = -1;
  let drawnH = -1;
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
  // The titles of the points as text for a comparison: see showSearchText
  let searchTexts = null;
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

  // A poster that loads asks for one draw POSTER_DRAW_DELAY later, and the posters that load in
  // that time use the same draw. A draw of the full map takes some ten milliseconds (more on a
  // phone), and the posters of a map load one after the other. Zoom, pan and resize draw in the
  // next frame (scheduleDraw).
  function schedulePosterDraw() {
    if (destroyed || posterTimer) return;
    posterTimer = setTimeout(() => {
      posterTimer = null;
      scheduleDraw();
    }, POSTER_DRAW_DELAY);
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
    hintPill.textContent = "Scroll to zoom · Drag to pan";
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

  // ---- The search box of the map
  // The user types a part of a title. The map shows the found shows with a frame, and it makes
  // the other shows faint. Enter moves the view to the next found show.
  let searchBox = box.querySelector(".vector-search");
  if (!searchBox) {
    searchBox = document.createElement("div");
    searchBox.className = "vector-search";
    searchBox.innerHTML = `
      <svg class="vector-search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
      <input class="vector-search-input" type="text" placeholder="Find a show" aria-label="Find a show on the map" autocomplete="off" spellcheck="false" enterkeyhint="search">
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
      const texts = (searchTexts ??= points.map(showSearchText));
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
      return { stroke: colors.accent, strong: true, glow: true, badge: "petal", badgeColor: colors.accent };
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
      const large = getPosterImage(pt.poster.replace("/cover/small/", "/cover/medium/"), schedulePosterDraw);
      if (large) return large;
    }
    return getPosterImage(pt.poster, schedulePosterDraw);
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
    if (look.badge === "petal") {
      // The mark of a recommendation: a petal, as in the legend of the map
      ctx.save();
      ctx.translate(bx + size / 2, by + size / 2);
      ctx.rotate(-0.6);
      ctx.beginPath();
      ctx.moveTo(-size * 0.3, 0);
      ctx.quadraticCurveTo(0, -size * 0.36, size * 0.3, 0);
      ctx.quadraticCurveTo(0, size * 0.36, -size * 0.3, 0);
      ctx.fill();
      ctx.restore();
      return;
    }
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
    drawnW = w;
    drawnH = h;

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
      catalog: isDark ? "rgba(169, 158, 163, 0.28)" : "rgba(114, 101, 106, 0.24)",
      library: isDark ? "rgba(238, 229, 232, 0.75)" : "rgba(35, 28, 31, 0.62)",
      neutral: isDark ? "rgba(169, 158, 163, 0.55)" : "rgba(114, 101, 106, 0.5)",
      muted: isDark ? "#a99ea3" : "#72656a",
      empty: isDark ? "#3a3337" : "#f1eaeb",
      paper: isDark ? "#242022" : "#ffffff",
      ink: isDark ? "#f5f0f1" : "#231c1f",
      shadow: isDark ? "rgba(0, 0, 0, 0.7)" : "rgba(35, 28, 31, 0.45)",
      find: rootStyle.getPropertyValue("--find").trim() || "#0e8177",
      dot: isDark ? "rgb(224, 214, 218)" : "rgb(74, 65, 69)",
      tier: {},
    };
    for (const t of ["S", "A", "B", "C", "D"]) {
      colors.tier[t] = rootStyle.getPropertyValue(`--tier-${t.toLowerCase()}`).trim();
    }
    const view = viewMode();
    const cards = cardsOn(side);
    drawGradient = gradient();
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
      if (gradient() && pt.match != null) metaParts.push(`${formatMatch(pt.match)}% match`);

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
      onOpen(hoveredPoint);
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

  // A ResizeObserver calls one time at its start, also when the size did not change: the map then
  // drew two times at its start. A new size draws the map again.
  const ro = new ResizeObserver((entries) => {
    const size = entries[0]?.borderBoxSize?.[0];
    if (size && Math.abs(size.inlineSize - drawnW) < 0.5 && Math.abs(size.blockSize - drawnH) < 0.5) return;
    scheduleDraw();
  });
  ro.observe(box);

  scheduleDraw();

  return {
    draw,
    scheduleDraw,
    // "posters" or "dots"
    setView: (view) => {
      canvas.dataset.view = view;
      scheduleDraw();
    },
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
      clearTimeout(posterTimer);
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
  };
}
