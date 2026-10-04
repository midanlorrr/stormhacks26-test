// Loads the exported files in data/ and draws them with MapLibre. No build step.

const slider = document.getElementById("slider");
const playBtn = document.getElementById("play");
let steps = [];          // contents of steps.json
let briefings = [];      // list from briefings/index.json (made by data_prep/07_briefings.py)
let areas = [];          // features of areas.geojson (1 km squares with estimated residents)
let timer = null;        // setInterval id while playing

const SUMMERLAND = [-119.67, 49.6];     // lng, lat
const REPLAY_PADDING = { left: 440, top: 0, right: 0, bottom: 0 };   // keeps Summerland clear of the side panel (24 + 380 px + space)

const map = new maplibregl.Map({
  container: "map",
  center: [-125, 40],                     // landing: zoomed-out globe, roughly over North America
  zoom: 1.8,
  // Basemap: dimmed Sentinel-2 cloudless satellite imagery (EOX). If its tiles fail, we switch to a plain OpenStreetMap fallback.
  style: {
    version: 8,
    // Label fonts are read from web/fonts (Noto Sans, downloaded once), so labels work offline
    glyphs: location.href.replace(/[^/]*$/, "") + "fonts/{fontstack}/{range}.pbf",
    sources: {
      satellite: {
        type: "raster",
        tiles: ["https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2025_3857/default/g/{z}/{y}/{x}.jpg"],
        tileSize: 256,
        maxzoom: 14,
        attribution: "EOxCloudless <a href='https://cloudless.eox.at' target='_blank'>cloudless.eox.at</a> by EOX IT Services GmbH " +
          "(Contains modified Copernicus Sentinel data 2025). Non-commercial use (CC BY-NC-SA 4.0).",
      },
      osm: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: "&copy; OpenStreetMap contributors",
      },
    },
    layers: [
      // Under the imagery: graphite, which shows through the oceans and any missing tiles
      { id: "globe-base", type: "background", paint: { "background-color": "#0e1116" } },
      // "Streets" basemap (standard OpenStreetMap). Hidden until you pick it, or until the satellite tiles fail.
      { id: "basemap-streets", type: "raster", source: "osm", layout: { visibility: "none" } },
      // Main basemap: Sentinel-2 imagery, dimmed so the overlays stand out (tweak these numbers to taste)
      { id: "basemap-satellite", type: "raster", source: "satellite",
        paint: { "raster-brightness-max": 0.85, "raster-saturation": -0.45, "raster-contrast": 0.1 } },
      // Design: a flat near-black layer over the imagery (35%) keeps the orange and red readable
      { id: "basemap-shade", type: "background",
        paint: { "background-color": "#0a0b0d", "background-opacity": 0.35 } },
    ],
  },
});
map.addControl(new maplibregl.NavigationControl(), "top-right");

// ----- Landing: a globe in the right half of the screen, with a fire marker on Summerland -----
// Globe docs: https://maplibre.org/maplibre-gl-js/docs/examples/display-a-globe-with-a-vector-map/
function landingPadding() {
  return innerWidth > 900 ? { left: Math.round(innerWidth * 0.5), top: 0, right: 0, bottom: 0 }
                          : { top: Math.round(innerHeight * 0.5), left: 0, right: 0, bottom: 0 };   // narrow screens: text on top
}
map.setPadding(landingPadding());
map.on("style.load", () => {
  map.setProjection({ type: "globe" });
  // A thin atmosphere around the globe that fades out as you zoom in
  map.setSky({ "sky-color": "#0b0f14", "horizon-color": "#3a2616",
               "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 5, 1, 7, 0] });
});
const markerElement = document.createElement("div");           // fire dot with soft halos, and its label (styled in style.css)
markerElement.className = "es-marker";
markerElement.innerHTML = '<span class="es-marker-core"></span><span class="es-marker-label">SUMMERLAND, BC</span>';
const summerlandMarker = new maplibregl.Marker({ element: markerElement }).setLngLat(SUMMERLAND).addTo(map);

// ----- Basemap toggle: Satellite / Streets (top-right, under the zoom buttons) -----
let satelliteErrors = 0;

function setBasemap(mode) {                   // mode is "satellite" or "streets"
  map.setLayoutProperty("basemap-satellite", "visibility", mode === "satellite" ? "visible" : "none");
  map.setLayoutProperty("basemap-streets", "visibility", mode === "streets" ? "visible" : "none");
  for (const button of document.querySelectorAll(".basemap-toggle button")) {
    button.classList.toggle("active", button.dataset.mode === mode);
  }
  if (mode === "satellite") {                 // trying satellite again: forget earlier errors and hide the warning
    satelliteErrors = 0;
    document.getElementById("basemap-note").hidden = true;
  }
}

// A small MapLibre control with two buttons
class BasemapToggle {
  onAdd() {
    this.box = document.createElement("div");
    this.box.className = "maplibregl-ctrl maplibregl-ctrl-group basemap-toggle";
    for (const [mode, text] of [["satellite", "Satellite"], ["streets", "Streets"]]) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.mode = mode;
      button.textContent = text;
      button.addEventListener("click", () => setBasemap(mode));
      this.box.appendChild(button);
    }
    this.box.firstChild.classList.add("active");
    return this.box;
  }
  onRemove() {
    this.box.remove();
  }
}
map.addControl(new BasemapToggle(), "top-right");

// If the satellite tiles keep failing (for example, no internet), switch to Streets and say so
map.on("error", (e) => {
  if (e.sourceId !== "satellite") {           // not a satellite-tile problem: show it instead of hiding it
    console.error(e.error);
    return;
  }
  if (++satelliteErrors !== 3) return;
  setBasemap("streets");
  document.getElementById("basemap-note").hidden = false;
});

// ----- Roads -----
// "design" = the Evacusense design (thin light roads, red affected roads, pale blue exit route);
// "typed" = styled by road type with dark casing and a glow; "original" = the earlier plain grey + red look
const ROAD_STYLE = "design";

// A road's tier, from its OSM tags: Highway 97 (ref), main roads, or local streets
const isHwy97 = ["match", ["get", "ref"], ["BC 97", "97"], true, false];
const isMain = ["match", ["get", "highway"],
  ["motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link", "tertiary", "tertiary_link"],
  true, false];
// Pick a value by tier; widths grow with zoom
const byTier = (hwy, main, local) => ["case", isHwy97, hwy, isMain, main, local];
const widthAtZoom = (z9, z15) => ["interpolate", ["linear"], ["zoom"], 9, z9, 15, z15];

function addRoadLayers() {
  if (ROAD_STYLE === "original") {            // earlier look: easy to switch back to
    map.addLayer({ id: "roads", type: "line", source: "roads",
      paint: { "line-color": "#777", "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.5, 14, 2] } });
    map.addLayer({ id: "roads-affected", type: "line", source: "roads",
      filter: ["<=", ["coalesce", ["get", "affected_step"], 999], 0],
      paint: { "line-color": "#d11", "line-width": ["interpolate", ["linear"], ["zoom"], 9, 1.5, 14, 4] } });
    map.addLayer({ id: "route", type: "line", source: "routes", filter: ["==", ["get", "step"], 0],
      paint: { "line-color": "#1565c0", "line-width": 4 } });
    return;
  }
  if (ROAD_STYLE === "design") {              // values from the design handoff (section 6); Highway 97 is a little brighter
    const rounded = { "line-cap": "round", "line-join": "round" };
    map.addLayer({ id: "roads", type: "line", source: "roads", layout: rounded,
      paint: { "line-color": ["case", isHwy97, "rgba(236,235,232,0.6)", "rgba(236,235,232,0.28)"],
               "line-width": ["interpolate", ["linear"], ["zoom"], 9, ["case", isHwy97, 1.2, 0.7], 11, ["case", isHwy97, 1.8, 1],
                              13, ["case", isHwy97, 2.4, 1.5], 16, ["case", isHwy97, 4, 2.4]] } });
    map.addLayer({ id: "roads-affected", type: "line", source: "roads", layout: rounded,
      filter: ["<=", ["coalesce", ["get", "affected_step"], 999], 0],
      paint: { "line-color": "#e5484d", "line-width": ["interpolate", ["linear"], ["zoom"], 9, 1.8, 13, 3.5, 16, 5] } });
    map.addLayer({ id: "route", type: "line", source: "routes", layout: rounded, filter: ["==", ["get", "step"], 0],
      paint: { "line-color": "#9cc9f0", "line-width": ["interpolate", ["linear"], ["zoom"], 9, 2.5, 13, 4, 16, 6] } });
    return;
  }
  const round = { "line-cap": "round", "line-join": "round" };
  // 1. dark casing under every road, so lines stay readable on satellite
  map.addLayer({ id: "roads-casing", type: "line", source: "roads", layout: round,
    paint: { "line-color": "#05080c", "line-opacity": 0.85,
             "line-width": ["interpolate", ["linear"], ["zoom"], 9, byTier(3.5, 2.2, 1.4), 15, byTier(10, 6.5, 4.5)] } });
  // 2. the roads: Highway 97 brightest and thickest, main roads medium, local streets thin and dim
  map.addLayer({ id: "roads", type: "line", source: "roads", layout: round,
    paint: { "line-color": byTier("#f4f1e8", "#c3c9d2", "#7f8794"),
             "line-width": ["interpolate", ["linear"], ["zoom"], 9, byTier(2, 1, 0.4), 15, byTier(6, 3.5, 1.8)] } });
  // 3. red glow, then the red line, for roads likely affected by the current step
  map.addLayer({ id: "roads-affected-glow", type: "line", source: "roads", layout: round,
    filter: ["<=", ["coalesce", ["get", "affected_step"], 999], 0],
    paint: { "line-color": "#ff2a2a", "line-opacity": 0.45, "line-blur": 5,
             "line-width": ["interpolate", ["linear"], ["zoom"], 9, byTier(7, 5, 4), 15, byTier(18, 14, 11)] } });
  map.addLayer({ id: "roads-affected", type: "line", source: "roads", layout: round,
    filter: ["<=", ["coalesce", ["get", "affected_step"], 999], 0],
    paint: { "line-color": "#ff3b3b",
             "line-width": ["interpolate", ["linear"], ["zoom"], 9, byTier(2.5, 1.8, 1.4), 15, byTier(6.5, 4.5, 3.5)] } });
  // 4. exit route in pale cyan, with a dark casing
  map.addLayer({ id: "route-casing", type: "line", source: "routes", layout: round, filter: ["==", ["get", "step"], 0],
    paint: { "line-color": "#05080c", "line-width": 8, "line-opacity": 0.8 } });
  map.addLayer({ id: "route", type: "line", source: "routes", layout: round, filter: ["==", ["get", "step"], 0],
    paint: { "line-color": "#8ff0ff", "line-width": 4 } });
}

// ----- Places: hospitals, fire stations, police, schools, community centres, big parks, beaches -----
// Neutral on purpose: in the design, colour is reserved for fire (orange), affected roads (red) and the exit route (pale blue)
const POI_COLORS = { hospital: "#ecebe8", fire_station: "#ecebe8", police: "#ecebe8", school: "#8a8d93",
                     community_centre: "#c9c8c4", park: "#c9c8c4", beach: "#c9c8c4" };
const POI_ORDER = ["hospital", "fire_station", "police", "community_centre", "park", "beach", "school"];   // label priority

function addPoiLayers() {
  const kind = ["get", "kind"];
  const colour = ["match", kind, ...Object.entries(POI_COLORS).flat(), "#ffffff"];
  const important = ["match", kind, ["hospital", "fire_station", "police"], true, false];
  map.addLayer({ id: "pois", type: "circle", source: "pois", minzoom: 11,
    paint: { "circle-color": colour, "circle-radius": ["case", important, 5, 3.5],
             "circle-stroke-color": "#0a0b0d", "circle-stroke-width": 1.2 } });
  const label = (id, filter, minzoom) => map.addLayer({
    id, type: "symbol", source: "pois", filter, minzoom,
    layout: { "text-field": ["get", "name"], "text-font": ["Noto Sans Regular"], "text-size": 11, "text-anchor": "top",
              "text-offset": [0, 0.7], "text-max-width": 9, "text-optional": true,
              "symbol-sort-key": ["index-of", kind, ["literal", POI_ORDER]] },    // lower number = placed first
    paint: { "text-color": colour, "text-halo-color": "#0a0b0d", "text-halo-width": 1.6 },
  });
  label("pois-labels", ["!=", kind, "school"], 12);          // schools are many, so they get a label only when zoomed in
  label("pois-labels-schools", ["==", kind, "school"], 13.5);
}

// ----- Road popups: hover to peek, click to pin -----
const ROAD_TYPES = {
  motorway: "Motorway", trunk: "Major highway", primary: "Primary road", secondary: "Secondary road",
  tertiary: "Tertiary road", residential: "Residential street", unclassified: "Minor road",
  living_street: "Living street", road: "Road", escape: "Escape lane",
};

const fmtTime = (iso) => new Date(iso).toLocaleString("en-CA", {
  timeZone: "America/Vancouver", weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
}) + " PDT";

// Build the popup content from a road's properties (DOM text, never HTML, so odd characters in names are safe)
function roadPopupContent(p) {
  const box = document.createElement("div");
  box.className = "road-popup";
  const add = (tag, text, cls) => {
    const el = document.createElement(tag);
    el.textContent = text;
    if (cls) el.className = cls;
    box.appendChild(el);
  };
  const isHwy = p.ref === "BC 97" || p.ref === "97";
  add("strong", isHwy ? "Highway 97" + (p.name ? " (" + p.name + ")" : "") : p.name || "Unnamed road");
  const type = (ROAD_TYPES[p.highway.replace("_link", "")] || p.highway) + (p.highway.endsWith("_link") ? " ramp" : "");
  add("div", type + (p.ref && !isHwy ? " · " + p.ref : ""));
  const now = Number(slider.value);
  if (p.affected_step == null) {
    add("div", "Not marked as affected (no satellite detection within 100 m).");
  } else if (p.affected_step <= now) {
    add("div", "Likely affected since " + fmtTime(p.affected_time) + ".", "affected");
  } else {
    add("div", "Not yet affected at this time; likely affected from " + fmtTime(p.affected_time) + ".");
  }
  add("div", "Estimate from satellite detections, not an official closure.", "small");
  return box;
}

// Where roads overlap (a highway and its ramps), show the most important one: Highway 97, then main roads, then local streets
function pickRoad(features) {
  const rank = (p) => (p.ref === "BC 97" || p.ref === "97" ? 0 : p.highway.endsWith("_link") ? 3 :
    ["motorway", "trunk", "primary", "secondary", "tertiary"].includes(p.highway) ? 1 : 2);
  return features.map((f) => f.properties).sort((a, b) => rank(a) - rank(b))[0];
}

function addRoadPopups() {
  // An invisible, wider copy of the roads, so thin lines are easy to hover and click
  map.addLayer({ id: "roads-hit", type: "line", source: "roads",
    paint: { "line-width": 14, "line-opacity": 0 } });
  const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12, maxWidth: "260px" });
  let pinned = false;                         // a clicked popup stays until you click empty map

  map.on("mousemove", "roads-hit", (e) => {
    map.getCanvas().style.cursor = "pointer";
    if (!pinned) popup.setLngLat(e.lngLat).setDOMContent(roadPopupContent(pickRoad(e.features))).addTo(map);
  });
  map.on("mouseleave", "roads-hit", () => {
    map.getCanvas().style.cursor = "";
    if (!pinned) popup.remove();
  });
  map.on("click", (e) => {
    const hit = map.queryRenderedFeatures(e.point, { layers: ["roads-hit"] });
    pinned = hit.length > 0;
    if (pinned) popup.setLngLat(e.lngLat).setDOMContent(roadPopupContent(pickRoad(hit))).addTo(map);
    else popup.remove();
  });
}

// ----- Road name labels (follow the line; off-white with a dark halo) -----
const hasName = ["!=", ["get", "name"], ""];
const isMajor = ["match", ["get", "highway"],
  ["motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link"], true, false];
// Highway 97, Princeton-Summerland Road and Prairie Valley Road are labelled at every zoom, from road_labels.geojson.
// Here we only stop the normal layers from repeating those names.
const isAlways = ["any", isHwy97, ["match", ["get", "name"], ["Princeton-Summerland Road", "Prairie Valley Road"], true, false]];

function addRoadLabels() {
  const label = (id, filter, minzoom, font, size, field, source = "roads") => map.addLayer({
    id, type: "symbol", source, minzoom, ...(filter ? { filter } : {}),
    layout: { "symbol-placement": "line", "symbol-spacing": 300, "text-field": field, "text-font": [font],
              "text-size": ["interpolate", ["linear"], ["zoom"], 9, size - 2, 15, size + 2], "text-letter-spacing": 0.03 },
    paint: { "text-color": "#ecebe8", "text-halo-color": "#0a0b0d", "text-halo-width": 1.8, "text-halo-blur": 0.5 },
  });
  // Added from least to most important: layers added later are placed first, so they win label collisions
  label("labels-local", ["all", hasName, ["!", isMajor], ["!", isAlways]], 13, "Noto Sans Regular", 11, ["get", "name"]);
  label("labels-major", ["all", hasName, isMajor, ["!", isAlways]], 10.5, "Noto Sans Regular", 12, ["get", "name"]);
  label("labels-always", null, 8, "Noto Sans Bold", 12, ["get", "label"], "road-labels");   // merged lines, no filter needed
}

// Read a JSON file and stop with a visible message if it fails
async function load(name) {
  const res = await fetch("data/" + name);
  if (!res.ok) throw new Error(name + " failed to load (" + res.status + ")");
  return res.json();
}

map.on("load", async () => {
  let fires, roads, points, routes, areaData, roadLabels, pois;
  try {
    [steps, fires, roads, points, routes, areaData, roadLabels, pois] = await Promise.all([
      load("steps.json"), load("fires.geojson"), load("roads.geojson"),
      load("points.geojson"), load("routes.geojson"), load("areas.geojson"), load("road_labels.geojson"), load("pois.geojson"),
    ]);
  } catch (err) {
    document.getElementById("loading-text").textContent = "Error: " + err.message +
      " (run the page through a local server, see README)";
    return;
  }

  areas = areaData.features.map((f) => f.properties).filter((p) => p.cut_step != null);

  map.addSource("roads", { type: "geojson", data: roads });
  map.addSource("road-labels", { type: "geojson", data: roadLabels });
  map.addSource("pois", { type: "geojson", data: pois });
  map.addSource("fires", { type: "geojson", data: fires });
  map.addSource("routes", { type: "geojson", data: routes });
  map.addSource("points", { type: "geojson", data: points });

  addRoadLayers();
  addRoadPopups();

  // Fire detections: a soft halo layer under a solid orange core
  map.addLayer({ id: "fires-glow", type: "circle", source: "fires",
    filter: ["<=", ["get", "step"], 0],
    paint: { "circle-color": "#ff6a2b", "circle-opacity": 0.25, "circle-blur": 0.6,
             "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 2.5, 10, 5, 12, 12, 15, 18] } });
  map.addLayer({ id: "fires", type: "circle", source: "fires",
    filter: ["<=", ["get", "step"], 0],
    paint: { "circle-color": "#ff6a2b",
             "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 0.8, 10, 1.6, 12, 3.5, 15, 5] } });

  map.addLayer({ id: "points", type: "circle", source: "points",
    paint: { "circle-radius": ["match", ["get", "kind"], "exit", 6, 3],
             "circle-color": ["match", ["get", "kind"], "exit", "#ecebe8", "#8a8d93"],
             "circle-stroke-color": "#0a0b0d", "circle-stroke-width": 1.5 } });

  addPoiLayers();
  addRoadLabels();           // added last, so road names win label collisions

  await loadBriefings();
  slider.max = steps.length - 1;
  slider.addEventListener("input", () => show(Number(slider.value)));
  playBtn.addEventListener("click", togglePlay);
  show(0);

  setReplayVisible(false);               // fires, roads and labels stay hidden until the replay starts
  map.once("idle", setReady);            // everything loaded and drawn
  setTimeout(setReady, 20000);           // ...or give up waiting after 20 s, so one slow tile never blocks Start
});

// ----- Landing page states: "loading" -> "landing" -> "replay" (a class on <body> drives the CSS) -----
const REPLAY_LAYERS = ["roads-casing", "roads", "roads-affected-glow", "roads-affected", "route-casing", "route", "fires-glow", "fires", "points",
                       "pois", "pois-labels", "pois-labels-schools", "labels-local", "labels-major", "labels-always", "roads-hit"];

function setReplayVisible(visible) {
  for (const id of REPLAY_LAYERS) {
    if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
  }
}

function setReady() {
  if (!document.body.classList.contains("loading")) return;       // already ready
  document.body.classList.remove("loading");
  document.getElementById("start").disabled = false;
  startSpin();
}

// ----- Spinning globe: turn it slowly with requestAnimationFrame until the user touches it or presses Start -----
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");   // people who ask their system for less motion
const SPIN_DEGREES_PER_SECOND = 4;
let spinning = false;
let lastFrame = 0;

function spinFrame(now) {
  if (!spinning) return;
  const seconds = Math.min((now - lastFrame) / 1000, 0.1);     // cap the step, so a slow frame never causes a jump
  lastFrame = now;
  const centre = map.getCenter();
  const lng = ((centre.lng - SPIN_DEGREES_PER_SECOND * seconds + 540) % 360) - 180;   // minus = surface moves left to right
  map.jumpTo({ center: [lng, centre.lat] });
  requestAnimationFrame(spinFrame);
}

function startSpin() {
  if (spinning || reducedMotion.matches || !document.body.classList.contains("landing")) return;
  spinning = true;
  lastFrame = performance.now();
  requestAnimationFrame(spinFrame);
}

function stopSpin() {
  spinning = false;
}
for (const type of ["mousedown", "touchstart", "wheel"]) map.on(type, stopSpin);   // the user took control

// ----- Start / Skip -----
// Start: fade out the landing overlay and fly to Summerland. Skip (or reduced motion): jump there.
function startReplay(animate) {
  stopSpin();
  document.getElementById("start").disabled = true;               // no double clicks
  document.body.classList.replace("landing", "flying");           // fades the landing overlay out; the map ignores the mouse while flying
  setReplayVisible(true);                                         // switch the data layers on now: MapLibre only prepares visible layers,
                                                                  // so they are ready when the camera arrives (they are tiny while far away)
  const view = { center: SUMMERLAND, zoom: 10, pitch: 45, bearing: -20, padding: REPLAY_PADDING };
  if (animate && !reducedMotion.matches) {
    map.once("moveend", arriveAtSummerland);
    map.flyTo({ ...view, duration: 7000 });
  } else {
    map.jumpTo(view);
    arriveAtSummerland();
  }
}

// The camera has arrived: show the panel and the fire and road layers, and start playing the replay
function arriveAtSummerland() {
  document.body.classList.replace("flying", "replay");
  summerlandMarker.remove();
  show(0);
  if (!timer && !reducedMotion.matches) togglePlay();             // auto-play (people who prefer less motion press Play themselves)
}

document.getElementById("start").addEventListener("click", () => startReplay(true));
document.getElementById("skip").addEventListener("click", (e) => { e.preventDefault(); startReplay(false); });

// "How it works" panel
const how = document.getElementById("how");
document.getElementById("how-btn").addEventListener("click", () => { how.hidden = false; document.getElementById("how-close").focus(); });
document.getElementById("how-close").addEventListener("click", () => { how.hidden = true; });
how.addEventListener("click", (e) => { if (e.target === how) how.hidden = true; });          // click outside the card
document.addEventListener("keydown", (e) => { if (e.key === "Escape") how.hidden = true; });

// Update the map and side panel for one time step
function show(i) {
  const s = steps[i];
  slider.value = i;
  map.setFilter("fires", ["<=", ["get", "step"], i]);
  map.setFilter("fires-glow", ["<=", ["get", "step"], i]);
  const affected = ["<=", ["coalesce", ["get", "affected_step"], 999], i];   // roads likely affected by step i
  map.setFilter("roads-affected", affected);
  if (map.getLayer("roads-affected-glow")) map.setFilter("roads-affected-glow", affected);
  map.setFilter("route", ["==", ["get", "step"], i]);
  if (map.getLayer("route-casing")) map.setFilter("route-casing", ["==", ["get", "step"], i]);

  const when = new Date(s.time);                                        // the data covers everything detected up to this time
  document.getElementById("clock").textContent = when.toLocaleTimeString("en-GB", { timeZone: "America/Vancouver", hour: "2-digit", minute: "2-digit", hour12: false });
  document.getElementById("clock-date").textContent = when.toLocaleDateString("en-CA", { timeZone: "America/Vancouver", month: "short", day: "numeric", year: "numeric" });
  const fraction = Number(slider.max) > 0 ? i / Number(slider.max) : 0;   // orange slider fill ends at the middle of the thumb
  document.getElementById("slider-fill").style.width = "calc(7px + (100% - 14px) * " + fraction + ")";
  document.getElementById("s-fires").textContent = s.fires_so_far.toLocaleString("en-CA");
  document.getElementById("s-roads").textContent = s.roads_affected.toLocaleString("en-CA");
  document.getElementById("s-res").textContent = s.residents_cut_off.toLocaleString("en-CA");
  showAreas(i);
  showBriefing(i);
  document.getElementById("s-longest").textContent = s.longest_drive_min == null ? "n/a" : Math.round(s.longest_drive_min) + " min";
  document.getElementById("s-mean").textContent = s.mean_drive_min == null ? "n/a" : Math.round(s.mean_drive_min) + " min";
}

// ----- Briefings: pre-generated files, so the demo needs no API key or internet -----
async function loadBriefings() {
  const select = document.getElementById("lang");
  select.addEventListener("change", () => showBriefing(Number(slider.value)));
  try {
    const res = await fetch("briefings/index.json");
    if (!res.ok) return;
    briefings = await res.json();
  } catch (err) {
    return;
  }
  const languages = [...new Set(briefings.map((b) => b.language))];
  for (const lang of languages) select.add(new Option(lang, lang));
  select.disabled = languages.length === 0;
}

// Show the latest pre-generated briefing at or before the current step, in the chosen language
async function showBriefing(i) {
  const box = document.getElementById("briefing");
  const lang = document.getElementById("lang").value;
  const options = briefings.filter((b) => b.language === lang && b.step <= i && !b.file.includes("_near-"));
  if (options.length === 0) {
    if (briefings.length > 0) box.innerHTML = '<p class="small">No briefing yet for this time. Briefings exist for later steps.</p>';
    return;
  }
  const pick = options[options.length - 1];
  let data;
  try {
    data = await (await fetch("briefings/" + pick.file)).json();
  } catch (err) {
    box.textContent = "Could not load the briefing.";
    return;
  }
  if (Number(slider.value) !== i) return;      // the slider moved while we were loading
  box.innerHTML = "";
  const note = document.createElement("p");
  note.className = "small";
  note.textContent = "Written by " + data.model + " from the estimates above, for " +
    new Date(data.time).toLocaleString("en-CA", { timeZone: "America/Vancouver", weekday: "short", hour: "numeric", minute: "2-digit" }) +
    " PDT. Not official guidance.";
  box.appendChild(note);
  const summary = document.createElement("p");
  summary.textContent = data.briefing.summary;           // textContent: AI text is never treated as HTML
  box.appendChild(summary);
  for (const [title, key] of [["Steps", "steps"], ["What to bring", "what_to_bring"], ["Pets", "pets"], ["Caveats", "caveats"]]) {
    const h = document.createElement("h3");
    h.textContent = title;
    const ul = document.createElement("ul");
    for (const item of data.briefing[key]) {
      const li = document.createElement("li");
      li.textContent = item;
      ul.appendChild(li);
    }
    box.append(h, ul);
  }
}

// List the areas cut off so far, largest first. Time is measured from the first detection.
function showAreas(i) {
  const list = document.getElementById("areas-list");
  list.replaceChildren();
  const cutNow = areas.filter((a) => a.cut_step <= i);
  document.getElementById("areas-count").textContent = cutNow.length;
  const top = cutNow.sort((a, b) => b.residents - a.residents).slice(0, 3);     // the three largest; the rest are counted in the heading
  if (top.length === 0) {
    const none = document.createElement("p");
    none.className = "es-note";
    none.textContent = "None yet";
    list.appendChild(none);
    return;
  }
  const firstDetection = new Date(steps[0].first_detection);
  for (const a of top) {
    const hours = ((new Date(a.cut_time) - firstDetection) / 3600000).toFixed(1);
    const wrap = document.createElement("div");
    wrap.className = "es-row-wrap";
    const row = document.createElement("div");
    row.className = "es-row";
    const name = document.createElement("span");
    name.textContent = a.name;
    const count = document.createElement("span");
    const number = document.createElement("span");
    number.className = "es-est";
    number.textContent = a.residents.toLocaleString("en-CA");
    const tag = document.createElement("span");
    tag.className = "es-est-tag";
    tag.textContent = "est.";
    count.append(number, tag);
    row.append(name, count);
    const detail = document.createElement("div");
    detail.className = "es-row-sub";
    detail.textContent = "cut off +" + hours + " h \u00b7 est. drive " + Math.round(a.baseline_drive_min) + " min";
    if (a.tight) {
      const flag = document.createElement("span");
      flag.className = "tight";
      flag.textContent = " \u00b7 tight";
      detail.appendChild(flag);
    }
    wrap.append(row, detail);
    list.appendChild(wrap);
  }
  if (cutNow.length > top.length) {
    const more = document.createElement("p");
    more.className = "es-note";
    more.textContent = "+" + (cutNow.length - top.length) + " more";
    list.appendChild(more);
  }
}

// Collapsible panel sections (Areas cut off, Briefing, About). The disclaimer is never collapsible.
function initSections() {
  for (const head of document.querySelectorAll(".es-section-head[data-toggle]")) {
    const section = head.closest(".es-section");
    const chevron = head.querySelector(".es-chev");
    const setOpen = (open) => {
      section.classList.toggle("is-closed", !open);
      head.setAttribute("aria-expanded", String(open));
      chevron.textContent = open ? "\u25b4" : "\u25be";
    };
    head.addEventListener("click", (e) => {
      if (e.target.closest("select")) return;                          // choosing a language must not collapse the section
      setOpen(section.classList.contains("is-closed"));
    });
    head.addEventListener("keydown", (e) => {
      if ((e.key === "Enter" || e.key === " ") && e.target === head) { e.preventDefault(); head.click(); }
    });
  }
}
initSections();

function togglePlay() {
  if (timer) { stop(); return; }
  if (Number(slider.value) >= steps.length - 1) show(0);   // restart from the beginning
  playBtn.textContent = "Pause";
  playBtn.dataset.state = "playing";
  timer = setInterval(() => {
    const next = Number(slider.value) + 1;
    if (next >= steps.length) { stop(); return; }
    show(next);
  }, 600);
}

function stop() {
  clearInterval(timer);
  timer = null;
  playBtn.textContent = "Play";
  playBtn.dataset.state = "paused";
}
