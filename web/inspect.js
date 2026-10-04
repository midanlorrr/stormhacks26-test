// Click-to-inspect: click an empty spot on the map to see, for that point, how close the fire came, whether the nearest
// road was likely affected, and the estimates for the 1 km area around it. Proximity and estimates only.
// Loaded after app.js: it uses app.js's map, steps, slider, burn, ROAD_TYPES and fmtTime.

const INSPECT_KM = 1;                    // "fire detection within 1 km"
const ROAD_MAX_M = 500;                  // no road is named if the nearest one is further than this
const STUDY_BOX = { west: -120.3, south: 49.3, east: -119.4, north: 49.9 };   // same box as data_prep/config.py

const inspect = { cells: null, loading: null, marker: null, point: null, facts: null };
const inspectCard = document.getElementById("inspect");
const inspectBody = document.getElementById("inspect-body");
const inspectFoot = document.getElementById("inspect-foot");

// ---------- small helpers ----------
// Local flat-earth distance in metres (fine for a few kilometres)
function metresBetween(lng1, lat1, lng2, lat2) {
  const dx = (lng2 - lng1) * Math.cos(((lat1 + lat2) / 2) * Math.PI / 180) * 111320;
  const dy = (lat2 - lat1) * 110574;
  return Math.hypot(dx, dy);
}

// Distance from a point to a line segment, in metres
function metresToSegment(lng, lat, a, b) {
  const k = Math.cos(lat * Math.PI / 180) * 111320, m = 110574;
  const px = 0, py = 0, ax = (a[0] - lng) * k, ay = (a[1] - lat) * m, bx = (b[0] - lng) * k, by = (b[1] - lat) * m;
  const dx = bx - ax, dy = by - ay;
  const t = dx === 0 && dy === 0 ? 0 : Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)));
  return Math.hypot(ax + t * dx - px, ay + t * dy - py);
}

// Longitude/latitude to UTM zone 11N metres (the grid the 1 km areas were cut on in data_prep/03_analysis.py)
function toUtm11(lng, lat) {
  const a = 6378137, f = 1 / 298.257223563, k0 = 0.9996, e2 = f * (2 - f), ep2 = e2 / (1 - e2);
  const phi = lat * Math.PI / 180, lam = (lng + 117) * Math.PI / 180;
  const N = a / Math.sqrt(1 - e2 * Math.sin(phi) ** 2), T = Math.tan(phi) ** 2, C = ep2 * Math.cos(phi) ** 2, A = Math.cos(phi) * lam;
  const M = a * ((1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * phi - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * Math.sin(2 * phi) +
                 (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * Math.sin(4 * phi) - (35 * e2 ** 3 / 3072) * Math.sin(6 * phi));
  const x = k0 * N * (A + (1 - T + C) * A ** 3 / 6 + (5 - 18 * T + T * T + 72 * C - 58 * ep2) * A ** 5 / 120) + 500000;
  const y = k0 * (M + N * Math.tan(phi) * (A * A / 2 + (5 - T + 9 * C + 4 * C * C) * A ** 4 / 24 + (61 - 58 * T + T * T + 600 * C - 330 * ep2) * A ** 6 / 720));
  return [x, y];
}

// The reverse: UTM zone 11N metres back to longitude/latitude (used to draw the corners of the 1 km square)
function fromUtm11(x, y) {
  const a = 6378137, f = 1 / 298.257223563, k0 = 0.9996, e2 = f * (2 - f), ep2 = e2 / (1 - e2);
  const e1 = (1 - Math.sqrt(1 - e2)) / (1 + Math.sqrt(1 - e2));
  const mu = (y / k0) / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256));
  const phi1 = mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * Math.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * Math.sin(4 * mu) +
               (151 * e1 ** 3 / 96) * Math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * Math.sin(8 * mu);
  const N1 = a / Math.sqrt(1 - e2 * Math.sin(phi1) ** 2), T1 = Math.tan(phi1) ** 2, C1 = ep2 * Math.cos(phi1) ** 2;
  const R1 = a * (1 - e2) / Math.pow(1 - e2 * Math.sin(phi1) ** 2, 1.5), D = (x - 500000) / (N1 * k0);
  const lat = phi1 - (N1 * Math.tan(phi1) / R1) * (D * D / 2 - (5 + 3 * T1 + 10 * C1 - 4 * C1 * C1 - 9 * ep2) * D ** 4 / 24 +
              (61 + 90 * T1 + 298 * C1 + 45 * T1 * T1 - 252 * ep2 - 3 * C1 * C1) * D ** 6 / 720);
  const lon = -117 * Math.PI / 180 + (D - (1 + 2 * T1 + C1) * D ** 3 / 6 + (5 - 2 * C1 + 28 * T1 - 3 * C1 * C1 + 8 * ep2 + 24 * T1 * T1) * D ** 5 / 120) / Math.cos(phi1);
  return [lon * 180 / Math.PI, lat * 180 / Math.PI];
}

const pdt = (iso) => new Date(iso).toLocaleString("en-CA", { timeZone: "America/Vancouver", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) + " PDT";
const distText = (m) => (m < 1000 ? Math.round(m / 10) * 10 + " m" : (m / 1000).toFixed(1) + " km");
// One end of a share, as text: "0%", "under 5%" or the nearest 10% ("30%")
const shareEnd = (n) => (n <= 0 ? "0%" : n < 5 ? "under 5%" : Math.round(n / 10) * 10 + "%");

// "about 20% to 40%" from the low (50 m rule) and high (100 m rule) estimates
function shareText(lo, hi) {
  const a = shareEnd(lo), b = shareEnd(hi);
  const exact = (t) => t === "0%" || t.startsWith("under");          // no "about" in front of these
  if (a === b) return exact(b) ? b : "about " + b;
  return (exact(a) || exact(b) ? "" : "about ") + a + " to " + b;
}

// The same share as a word: none / some / most / all (a range of words if the two estimates differ)
function bandWord(s) {
  if (s <= 0) return "none";
  if (s >= 95) return "all";
  return s > 50 ? "most" : "some";
}
const bandText = (lo, hi) => (bandWord(lo) === bandWord(hi) ? bandWord(hi) : bandWord(lo) + " to " + bandWord(hi));

// ---------- the 1 km area file, fetched the first time it is needed ----------
function loadCells() {
  if (!inspect.loading) {
    inspect.loading = fetch("data/area_cut_shares.json").then((r) => r.json()).then((d) => {
      inspect.cells = new Map(d.cells.map((c) => [c.x + "_" + c.y, c]));
    }).catch(() => { inspect.loading = null; });
  }
  return inspect.loading;
}

// ---------- gather what is true at a clicked point (does not depend on the slider) ----------
function gatherFacts(lng, lat) {
  const data = window.inspectData;
  const facts = { lng, lat, inside: lng >= STUDY_BOX.west && lng <= STUDY_BOX.east && lat >= STUDY_BOX.south && lat <= STUDY_BOX.north };
  if (!facts.inside || !data) return facts;
  // fire detections within INSPECT_KM, earliest first
  facts.fires = [];
  for (const f of data.fires) {
    const [x, y] = f.geometry.coordinates;
    if (Math.abs(y - lat) > 0.012 || Math.abs(x - lng) > 0.018) continue;            // quick skip (about 1.3 km box)
    const d = metresBetween(lng, lat, x, y);
    if (d <= INSPECT_KM * 1000) facts.fires.push({ d, step: f.properties.step, time: f.properties.time });
  }
  facts.fires.sort((a, b) => new Date(a.time) - new Date(b.time));
  // nearest mapped road
  let best = null;
  for (const f of data.roads) {
    const c = f.geometry.coordinates;
    for (let k = 0; k < c.length - 1; k++) {
      if (Math.abs(c[k][1] - lat) > 0.01 && Math.abs(c[k + 1][1] - lat) > 0.01) continue;
      const d = metresToSegment(lng, lat, c[k], c[k + 1]);
      if (!best || d < best.d) best = { d, p: f.properties };
    }
  }
  facts.road = best && best.d <= ROAD_MAX_M ? best : null;
  // the 1 km area (a square on the UTM grid) the point falls in
  const [ux, uy] = toUtm11(lng, lat);
  facts.cell = inspect.cells ? inspect.cells.get(Math.floor(ux / 1000) + "_" + Math.floor(uy / 1000)) || null : null;
  return facts;
}

// ---------- draw the card for the slider's current step ----------
function line(parent, label, value, extra) {
  const row = document.createElement("div");
  row.className = "inspect-row";
  const l = document.createElement("span");
  l.className = "inspect-label";
  l.textContent = label;
  const v = document.createElement("span");
  v.className = "inspect-value";
  v.textContent = value;
  if (extra) {
    const tag = document.createElement("span");
    tag.className = "es-est-tag";
    tag.textContent = extra;
    v.append(" ", tag);
  }
  row.append(l, v);
  parent.appendChild(row);
}

function heading(parent, text) {
  const h = document.createElement("div");
  h.className = "inspect-section";
  h.textContent = text;
  parent.appendChild(h);
}

function note(parent, text, cls) {
  const p = document.createElement("p");
  p.className = "es-note" + (cls ? " " + cls : "");
  p.textContent = text;
  parent.appendChild(p);
}

function renderInspect() {
  const f = inspect.facts;
  if (!f || inspectCard.hidden) return;
  const i = Number(slider.value);
  const nowText = new Date(steps[i].time).toLocaleString("en-CA", { timeZone: "America/Vancouver", weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  inspectBody.replaceChildren();
  inspectFoot.replaceChildren();
  document.getElementById("inspect-title").textContent = Math.abs(f.lat).toFixed(4) + "°N  " + Math.abs(f.lng).toFixed(4) + "°W";
  note(inspectFoot, "Illustrative estimate from public data, not official guidance.", "inspect-disclaimer");

  if (!f.inside) {
    note(inspectBody, "No data here. This point is outside the study area (Summerland, Faulder and Peachland).");
    return;
  }
  const c = f.cell;
  const firstCut = c ? c.first_hi : null;

  // the time of the replay, and a small timeline to read at a glance
  const when = document.createElement("div");
  when.className = "inspect-when";
  when.textContent = "Replay time: " + nowText + " PDT";
  inspectBody.appendChild(when);
  inspectBody.appendChild(buildInspectTimeline(f, i, firstCut));

  // 1. fire detections
  heading(inspectBody, "Fire detections within " + INSPECT_KM + " km (dashed circle)");
  const soFar = f.fires.filter((d) => d.step <= i);
  line(inspectBody, "Now", soFar.length ? soFar.length + " so far, nearest " + distText(Math.min(...soFar.map((d) => d.d))) : "none yet");
  line(inspectBody, "First in replay", f.fires.length ? pdt(f.fires[0].time) + ", " + distText(f.fires[0].d) + " away" : "none during the replay");

  // 2. nearest road
  heading(inspectBody, "Nearest road");
  if (!f.road) {
    line(inspectBody, "Road", "no mapped road within " + ROAD_MAX_M + " m");
  } else {
    const p = f.road.p, isHwy = p.ref === "BC 97" || p.ref === "97";
    const type = (ROAD_TYPES[p.highway.replace("_link", "")] || p.highway) + (p.highway.endsWith("_link") ? " ramp" : "");
    line(inspectBody, "Road", (isHwy ? "Highway 97" : p.name || "Unnamed " + type.toLowerCase()) + ", " + distText(f.road.d) + " away");
    const status = p.affected_step == null ? "not marked as affected during the replay"
      : p.affected_step <= i ? "likely affected since " + pdt(p.affected_time) : "not yet affected; likely affected from " + pdt(p.affected_time);
    line(inspectBody, "Now", status);
  }

  // 3. residents and routes out
  heading(inspectBody, "Residents in this 1 km square");
  if (!c) {
    line(inspectBody, "Estimate", "fewer than about 20 estimated residents");
  } else {
    line(inspectBody, "Estimate", "about " + c.residents.toLocaleString("en-CA"), "est.");
    const hi = c.hi[i], lo = c.lo[i], end = c.hi.length - 1;
    line(inspectBody, "Cut off now", shareText(lo, hi) + " (" + bandText(lo, hi) + ")", "est.");
    line(inspectBody, "Cut off by end", shareText(c.lo[end], c.hi[end]) + " (" + bandText(c.lo[end], c.hi[end]) + ")", "est.");
    if (firstCut) line(inspectBody, "First route lost", pdt(firstCut), "est.");
    line(inspectBody, "Drive to an exit", "about " + Math.round(c.drive) + " min before the fire", "est.");
  }

  // footnotes, kept short (the disclaimer line above stays pinned at the bottom of the card)
  note(inspectFoot, "Cut off = no drivable route to any exit. Drive time: free-flow, before the fire. Roads: marked from detections within 100 m. " +
    "Residents: WorldPop 2025 (100 m) summed over 1 km, rounded to 10.", "inspect-source");
  inspectFoot.insertBefore(inspectFoot.lastChild, inspectFoot.firstChild);        // sources first, disclaimer last
}

// A small timeline for the whole replay: a dot where fire first came within 1 km, a diamond where routes were first cut, a tick for "now"
function buildInspectTimeline(f, i, firstCut) {
  const t0 = new Date(steps[0].time).getTime(), span = new Date(steps[steps.length - 1].time).getTime() - t0;
  const place = (iso) => Math.max(0, Math.min(100, ((new Date(iso).getTime() - t0) / span) * 100));
  const wrap = document.createElement("div");
  const bar = document.createElement("div");
  bar.className = "inspect-timeline";
  bar.setAttribute("aria-hidden", "true");
  const now = document.createElement("span");
  now.className = "tl-now";
  now.style.left = (i / (steps.length - 1)) * 100 + "%";
  bar.appendChild(now);
  const legend = [];
  if (f.fires.length) {
    const d = document.createElement("span");
    d.className = "tl-dot tl-fire";
    d.style.left = place(f.fires[0].time) + "%";
    bar.appendChild(d);
    legend.push("● fire within " + INSPECT_KM + " km");
  }
  if (firstCut) {
    const d = document.createElement("span");
    d.className = "tl-dot tl-cut";
    d.style.left = place(firstCut) + "%";
    bar.appendChild(d);
    legend.push("◆ first route cut (est.)");
  }
  const ends = document.createElement("div");
  ends.className = "inspect-timeline-ends";
  const dayLabel = (iso) => new Date(iso).toLocaleDateString("en-CA", { timeZone: "America/Vancouver", month: "short", day: "numeric" });
  ends.textContent = dayLabel(steps[0].time) + " to " + dayLabel(steps[steps.length - 1].time) + (legend.length ? "   " + legend.join("   ") : "   no fire or route cut here");
  wrap.append(bar, ends);
  return wrap;
}

// ---------- show what is being analysed: the 1 km square (residents) and the 1 km circle (fire detections) ----------
function areaShapes(lng, lat) {
  const [ux, uy] = toUtm11(lng, lat);
  const x0 = Math.floor(ux / 1000) * 1000, y0 = Math.floor(uy / 1000) * 1000;
  const square = [[x0, y0], [x0 + 1000, y0], [x0 + 1000, y0 + 1000], [x0, y0 + 1000], [x0, y0]].map(([x, y]) => fromUtm11(x, y));
  const circle = [];
  for (let k = 0; k <= 64; k++) {
    const angle = (k / 64) * 2 * Math.PI;
    circle.push([lng + (INSPECT_KM * 1000 * Math.cos(angle)) / (111320 * Math.cos(lat * Math.PI / 180)), lat + (INSPECT_KM * 1000 * Math.sin(angle)) / 110574]);
  }
  return {
    type: "FeatureCollection",
    features: [{ type: "Feature", properties: { kind: "square" }, geometry: { type: "Polygon", coordinates: [square] } },
               { type: "Feature", properties: { kind: "circle" }, geometry: { type: "LineString", coordinates: circle } }],
  };
}

function drawArea(lng, lat, inside) {
  const data = inside ? areaShapes(lng, lat) : { type: "FeatureCollection", features: [] };
  if (map.getSource("inspect-area")) {
    map.getSource("inspect-area").setData(data);
    return;
  }
  map.addSource("inspect-area", { type: "geojson", data });
  map.addLayer({ id: "inspect-square-fill", type: "fill", source: "inspect-area", filter: ["==", ["get", "kind"], "square"],
                 paint: { "fill-color": "#ecebe8", "fill-opacity": 0.07 } });
  map.addLayer({ id: "inspect-square", type: "line", source: "inspect-area", filter: ["==", ["get", "kind"], "square"],
                 paint: { "line-color": "#ecebe8", "line-width": 1.6 } });
  map.addLayer({ id: "inspect-circle", type: "line", source: "inspect-area", filter: ["==", ["get", "kind"], "circle"],
                 paint: { "line-color": "#ecebe8", "line-width": 1.2, "line-dasharray": [3, 3], "line-opacity": 0.85 } });
}

// ---------- open, move and close ----------
function closeInspect() {
  document.body.classList.remove("inspecting");
  if (map.getSource("inspect-area")) map.getSource("inspect-area").setData({ type: "FeatureCollection", features: [] });
  if (inspect.marker) { inspect.marker.remove(); inspect.marker = null; }
  inspectCard.hidden = true;
  inspect.facts = null;
}

async function openInspect(lng, lat) {
  await loadCells();
  inspect.facts = gatherFacts(lng, lat);
  if (!inspect.marker) {
    const el = document.createElement("div");
    el.className = "es-inspect-marker";
    el.title = "Click to close";
    el.addEventListener("click", (e) => { e.stopPropagation(); closeInspect(); });
    inspect.marker = new maplibregl.Marker({ element: el }).setLngLat([lng, lat]).addTo(map);     // only one marker at a time
  } else {
    inspect.marker.setLngLat([lng, lat]);
  }
  drawArea(lng, lat, inspect.facts.inside);
  inspectCard.hidden = false;
  document.body.classList.add("inspecting");                                    // the map key makes room for the card
  renderInspect();
}

map.on("click", (e) => {
  if (!document.body.classList.contains("replay") || burn.active) return;      // not on the intro globe, and not in the Burn scar view
  const hitRoad = map.getLayer("roads-hit") && map.queryRenderedFeatures(e.point, { layers: ["roads-hit"] }).length > 0;
  if (hitRoad) { closeInspect(); return; }                                      // a road popup takes this click
  openInspect(e.lngLat.lng, e.lngLat.lat);
});
document.getElementById("inspect-close").addEventListener("click", closeInspect);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeInspect(); });
slider.addEventListener("input", renderInspect);                                // keep "now" lines in step with the slider
window.updateInspect = renderInspect;                                           // app.js calls this when the replay plays on
window.closeInspect = closeInspect;
window.openInspect = openInspect;                                               // the road popup's "Inspect this spot" button uses this
