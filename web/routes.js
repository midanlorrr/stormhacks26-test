// Route replay: pick a starting point and watch the fastest route to an exit, and its estimated drive time, change over the replay.
// Two separate "what if" scenarios (never combined). Data: data/route_replay.json, made by data_prep/10_route_replay.py.
// Loaded after app.js: it uses app.js's map, steps, slider and burn.

const rr = { data: null, loading: null, active: false, origin: 0, scenario: "fire", layersAdded: false };
const rrList = document.getElementById("rr-list");
const rrStatus = document.getElementById("rr-status");
const rrChart = document.getElementById("rr-chart");
const SVG_NS = "http://www.w3.org/2000/svg";
const EXIT_BLUE = "#9cc9f0";                          // the exit-route colour used everywhere else on the map

const rrTime = (iso) => new Date(iso).toLocaleString("en-CA", { timeZone: "America/Vancouver", weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) + " PDT";

function rrLoad() {
  if (!rr.loading) {
    rr.loading = fetch("data/route_replay.json").then((r) => r.json()).then((d) => { rr.data = d; buildList(); }).catch(() => { rr.loading = null; });
  }
  return rr.loading;
}

// ---------- the list of starting points ----------
function buildList() {
  rrList.replaceChildren();
  rr.data.origins.forEach((o, k) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "rr-origin";
    b.textContent = o.label;
    b.setAttribute("aria-pressed", String(k === rr.origin));
    b.addEventListener("click", () => selectOrigin(k, true));
    rrList.appendChild(b);
  });
}

function selectOrigin(k, fit) {
  rr.origin = k;
  [...rrList.children].forEach((b, j) => b.setAttribute("aria-pressed", String(j === k)));
  if (fit && rr.active) fitToOrigin();
  render();
}

// Zoom the map to everything this starting point's routes touch (both scenarios, so switching scenario does not move the map)
function fitToOrigin() {
  const o = rr.data.origins[rr.origin];
  const bounds = new maplibregl.LngLatBounds([o.lon, o.lat], [o.lon, o.lat]);
  for (const sc of ["fire", "closure"]) for (const r of o[sc].routes) for (const c of r.coords) bounds.extend(c);
  map.fitBounds(bounds, { padding: 50, maxZoom: 12.5, duration: 900 });
}

// ---------- the route on the map ----------
function addRouteLayers() {
  if (rr.layersAdded) return;
  const empty = { type: "FeatureCollection", features: [] };
  map.addSource("rr-line", { type: "geojson", data: empty });
  map.addSource("rr-origin", { type: "geojson", data: empty });
  const round = { "line-cap": "round", "line-join": "round" };
  map.addLayer({ id: "rr-casing", type: "line", source: "rr-line", layout: round,
                 paint: { "line-color": "#05080c", "line-width": ["interpolate", ["linear"], ["zoom"], 9, 5, 13, 8, 16, 11],
                          "line-opacity": ["case", ["get", "dim"], 0.2, 0.8] } });
  map.addLayer({ id: "rr-line", type: "line", source: "rr-line", layout: round,
                 paint: { "line-color": EXIT_BLUE, "line-width": ["interpolate", ["linear"], ["zoom"], 9, 2.5, 13, 4, 16, 6],
                          "line-opacity": ["case", ["get", "dim"], 0.4, 1] } });
  map.addLayer({ id: "rr-origin", type: "circle", source: "rr-origin",
                 paint: { "circle-radius": 7, "circle-color": "#12161c", "circle-stroke-color": "#ecebe8", "circle-stroke-width": 2.5 } });
  rr.layersAdded = true;
}

function setRouteLayers(visible) {
  for (const id of ["rr-casing", "rr-line", "rr-origin"]) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
  // the "longest drive" route of the other views is hidden while this one is shown, so there are not two blue lines
  if (!burn.active) for (const id of ["route-casing", "route"]) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visible ? "none" : "visible");
}

window.setRoutesActive = async function (on) {
  if (on === rr.active) return;
  rr.active = on;
  if (!on) {
    if (rr.layersAdded) setRouteLayers(false);
    return;
  }
  await rrLoad();
  if (!rr.active || !rr.data) return;                      // left the tab while loading
  addRouteLayers();
  setRouteLayers(true);
  fitToOrigin();
  render();
};

// ---------- draw everything for the slider's current step ----------
function render() {
  if (!rr.data) return;
  const o = rr.data.origins[rr.origin], block = o[rr.scenario], i = Number(slider.value);
  const at = block.at[i];
  // the line: today's route, or (dimmed) the last route that existed when there is none now
  let shown = at;
  for (let j = i; shown < 0 && j >= 0; j--) shown = block.at[j];
  if (rr.layersAdded) {
    const features = shown >= 0 ? [{ type: "Feature", properties: { dim: at < 0 }, geometry: { type: "LineString", coordinates: block.routes[shown].coords } }] : [];
    map.getSource("rr-line").setData({ type: "FeatureCollection", features });
    map.getSource("rr-origin").setData({ type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [o.lon, o.lat] } }] });
  }
  // the status line
  rrStatus.replaceChildren();
  rrStatus.classList.toggle("rr-none", at < 0);
  const when = document.createElement("div");
  when.className = "rr-when";
  when.textContent = rrTime(steps[i].time);
  const what = document.createElement("div");
  what.className = "rr-what";
  if (at < 0) {
    what.textContent = "No route available at this time";
  } else {
    const minutes = block.minutes[i];
    what.textContent = "About " + Math.round(minutes) + " min to an exit";
    const tag = document.createElement("span");
    tag.className = "es-est-tag";
    tag.textContent = "est.";
    what.append(" ", tag);
    if (at !== block.at[0]) {
      const diff = document.createElement("div");
      diff.className = "rr-diff";
      diff.textContent = "A different route from the first step";
      rrStatus.append(when, what, diff);
      drawChart();
      return;
    }
  }
  rrStatus.append(when, what);
  drawChart();
}
window.updateRoutes = function () { if (rr.active) render(); };

// ---------- the chart of drive time over the 25 steps ----------
function svg(tag, attrs, text) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (text !== undefined) el.textContent = text;
  return el;
}

function drawChart() {
  const o = rr.data.origins[rr.origin], block = o[rr.scenario], n = steps.length, i = Number(slider.value);
  const W = 240, H = 96, L = 26, R = 8, T = 10, B = 22;
  const all = [...o.fire.minutes, ...o.closure.minutes].filter((m) => m !== null);
  const top = Math.max(20, Math.ceil(Math.max(...all) / 10) * 10);                 // same scale for both scenarios, so switching is easy to compare
  const x = (k) => L + (k * (W - L - R)) / (n - 1);
  const y = (m) => T + (H - T - B) * (1 - m / top);
  rrChart.replaceChildren();
  rrChart.setAttribute("viewBox", "0 0 " + W + " " + H);
  rrChart.setAttribute("aria-label", "Estimated minimum drive time over the replay, " + rr.data.origins[rr.origin].label);
  // grid and axis labels
  for (const m of [0, top / 2, top]) {
    rrChart.append(svg("line", { x1: L, x2: W - R, y1: y(m), y2: y(m), class: "rr-grid" }), svg("text", { x: L - 4, y: y(m) + 3, class: "rr-axis", "text-anchor": "end" }, String(m)));
  }
  steps.forEach((s, k) => {                                                         // a label at each midnight
    if (new Date(s.time).toLocaleTimeString("en-GB", { timeZone: "America/Vancouver", hour: "2-digit", hour12: false }) === "00") {
      rrChart.append(svg("text", { x: x(k), y: H - 7, class: "rr-axis", "text-anchor": "middle" }, new Date(s.time).toLocaleDateString("en-CA", { timeZone: "America/Vancouver", month: "short", day: "numeric" })));
    }
  });
  // steps with no route: a hatched band
  let k = 0;
  while (k < n) {
    if (block.minutes[k] === null) {
      let end = k;
      while (end + 1 < n && block.minutes[end + 1] === null) end++;
      rrChart.append(svg("rect", { x: x(k) - 3, y: T, width: x(end) - x(k) + 6, height: H - T - B, class: "rr-noroute" }));
      if (end - k >= 3) rrChart.append(svg("text", { x: (x(k) + x(end)) / 2, y: T + 14, class: "rr-axis", "text-anchor": "middle" }, "no route"));
      k = end + 1;
    } else {
      k++;
    }
  }
  // where the closure starts (closure scenario only)
  if (rr.scenario === "closure") {
    const cx = x(rr.data.closure_first_step);
    rrChart.append(svg("line", { x1: cx, x2: cx, y1: T, y2: H - B, class: "rr-closure" }), svg("text", { x: cx - 3, y: T + 9, class: "rr-axis", "text-anchor": "end" }, "closure"));
  }
  // the drive time, as steps (the value holds until the next step)
  let d = "";
  block.minutes.forEach((m, j) => {
    if (m === null) return;
    const prevNull = j === 0 || block.minutes[j - 1] === null;
    d += (prevNull ? "M" : "L") + x(j) + " " + y(m) + " L" + x(Math.min(j + 1, n - 1)) + " " + y(m) + " ";
  });
  rrChart.append(svg("path", { d, class: "rr-linepath" }));
  // the current step
  rrChart.append(svg("line", { x1: x(i), x2: x(i), y1: T, y2: H - B, class: "rr-now" }));
  const m = block.minutes[i];
  rrChart.append(svg("circle", { cx: x(i), cy: m === null ? y(0) : y(m), r: 4, class: m === null ? "rr-dot rr-dot-none" : "rr-dot" }));
}

// ---------- scenario selector ----------
document.querySelectorAll('input[name="rr-scenario"]').forEach((input) => {
  input.addEventListener("change", () => { rr.scenario = input.value; render(); });
});
