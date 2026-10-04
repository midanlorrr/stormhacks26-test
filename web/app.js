// Loads the exported files in data/ and draws them with MapLibre. No build step.

const slider = document.getElementById("slider");
const playBtn = document.getElementById("play");
let steps = [];          // contents of steps.json
let briefings = [];      // list from briefings/index.json (made by data_prep/07_briefings.py)
let areas = [];          // features of areas.geojson (1 km squares with estimated residents)
let timer = null;        // setInterval id while playing

const map = new maplibregl.Map({
  container: "map",
  center: [-119.78, 49.63],
  zoom: 10.5,
  // Basemap: dimmed Sentinel-2 cloudless satellite imagery (EOX). If its tiles fail, we switch to a plain OpenStreetMap fallback.
  style: {
    version: 8,
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
        attribution: "FALLBACK basemap: &copy; OpenStreetMap contributors",
      },
    },
    layers: [
      // FALLBACK basemap, hidden unless the satellite tiles fail
      { id: "basemap-fallback-osm", type: "raster", source: "osm", layout: { visibility: "none" } },
      // Main basemap, dimmed so the overlays stand out (tweak these three numbers to taste)
      { id: "basemap-satellite", type: "raster", source: "satellite",
        paint: { "raster-brightness-max": 0.55, "raster-saturation": -0.45, "raster-contrast": 0.1 } },
    ],
  },
});
map.addControl(new maplibregl.NavigationControl(), "top-right");

// If the satellite tiles keep failing (for example, no internet), show the OpenStreetMap fallback instead
let satelliteErrors = 0;
map.on("error", (e) => {
  if (e.sourceId !== "satellite" || ++satelliteErrors !== 3) return;
  map.setLayoutProperty("basemap-satellite", "visibility", "none");
  map.setLayoutProperty("basemap-fallback-osm", "visibility", "visible");
  document.getElementById("basemap-note").hidden = false;
});

// Read a JSON file and stop with a visible message if it fails
async function load(name) {
  const res = await fetch("data/" + name);
  if (!res.ok) throw new Error(name + " failed to load (" + res.status + ")");
  return res.json();
}

map.on("load", async () => {
  let fires, roads, points, routes, areaData;
  try {
    [steps, fires, roads, points, routes, areaData] = await Promise.all([
      load("steps.json"), load("fires.geojson"), load("roads.geojson"),
      load("points.geojson"), load("routes.geojson"), load("areas.geojson"),
    ]);
  } catch (err) {
    document.getElementById("clock").textContent = "Error: " + err.message +
      " (run the page through a local server, see README)";
    return;
  }

  areas = areaData.features.map((f) => f.properties).filter((p) => p.cut_step != null);

  map.addSource("roads", { type: "geojson", data: roads });
  map.addSource("fires", { type: "geojson", data: fires });
  map.addSource("routes", { type: "geojson", data: routes });
  map.addSource("points", { type: "geojson", data: points });

  // Roads: grey base, red once likely affected. affected_step is null for roads never affected.
  map.addLayer({ id: "roads", type: "line", source: "roads",
    paint: { "line-color": "#777", "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.5, 14, 2] } });
  map.addLayer({ id: "roads-affected", type: "line", source: "roads",
    filter: ["<=", ["coalesce", ["get", "affected_step"], 999], 0],
    paint: { "line-color": "#d11", "line-width": ["interpolate", ["linear"], ["zoom"], 9, 1.5, 14, 4] } });

  map.addLayer({ id: "route", type: "line", source: "routes",
    filter: ["==", ["get", "step"], 0],
    paint: { "line-color": "#1565c0", "line-width": 4 } });

  map.addLayer({ id: "fires", type: "circle", source: "fires",
    filter: ["<=", ["get", "step"], 0],
    paint: { "circle-color": "#ff7a00", "circle-opacity": 0.7,
             "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 2, 14, 9] } });

  map.addLayer({ id: "points", type: "circle", source: "points",
    paint: { "circle-radius": ["match", ["get", "kind"], "exit", 7, 3],
             "circle-color": ["match", ["get", "kind"], "exit", "#1b7f3b", "#5b6b8a"],
             "circle-stroke-color": "#fff", "circle-stroke-width": 1 } });

  await loadBriefings();
  slider.max = steps.length - 1;
  slider.addEventListener("input", () => show(Number(slider.value)));
  playBtn.addEventListener("click", togglePlay);
  show(0);
});

// Update the map and side panel for one time step
function show(i) {
  const s = steps[i];
  slider.value = i;
  map.setFilter("fires", ["<=", ["get", "step"], i]);
  map.setFilter("roads-affected", ["<=", ["coalesce", ["get", "affected_step"], 999], i]);
  map.setFilter("route", ["==", ["get", "step"], i]);

  document.getElementById("clock").textContent = new Date(s.time).toLocaleString("en-CA", {
    timeZone: "America/Vancouver", weekday: "short", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit",
  }) + " PDT (data up to this time)";
  document.getElementById("s-fires").textContent = s.fires_so_far;
  document.getElementById("s-roads").textContent = s.roads_affected;
  document.getElementById("s-res").textContent = "~" + s.residents_cut_off.toLocaleString("en-CA");
  showAreas(i);
  showBriefing(i);
  document.getElementById("s-longest").textContent = s.longest_drive_min == null ? "n/a" : "~" + Math.round(s.longest_drive_min) + " min";
  document.getElementById("s-mean").textContent = s.mean_drive_min == null ? "n/a" : "~" + Math.round(s.mean_drive_min) + " min";
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
  list.innerHTML = "";
  const cut = areas.filter((a) => a.cut_step <= i).sort((a, b) => b.residents - a.residents).slice(0, 6);
  if (cut.length === 0) {
    list.innerHTML = "<li>None yet</li>";
    return;
  }
  const firstDetection = new Date(steps[0].first_detection);
  for (const a of cut) {
    const hours = ((new Date(a.cut_time) - firstDetection) / 3600000).toFixed(1);
    const li = document.createElement("li");
    li.innerHTML = a.name + ": ~" + a.residents + " residents, cut off " + hours + " h after first detection; est. drive " +
      Math.round(a.baseline_drive_min) + " min" + (a.tight ? ' <span class="tight">(tight)</span>' : "");
    list.appendChild(li);
  }
}

function togglePlay() {
  if (timer) { stop(); return; }
  if (Number(slider.value) >= steps.length - 1) show(0);   // restart from the beginning
  playBtn.textContent = "Pause";
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
}
