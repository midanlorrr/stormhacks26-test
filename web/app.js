// Loads the exported files in data/ and draws them with MapLibre. No build step.

const slider = document.getElementById("slider");
const playBtn = document.getElementById("play");
let steps = [];          // contents of steps.json
let timer = null;        // setInterval id while playing

const map = new maplibregl.Map({
  container: "map",
  center: [-119.78, 49.63],
  zoom: 10.5,
  style: {
    version: 8,
    sources: {
      osm: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: "&copy; OpenStreetMap contributors",
      },
    },
    layers: [{ id: "osm", type: "raster", source: "osm" }],
  },
});
map.addControl(new maplibregl.NavigationControl(), "top-right");

// Read a JSON file and stop with a visible message if it fails
async function load(name) {
  const res = await fetch("data/" + name);
  if (!res.ok) throw new Error(name + " failed to load (" + res.status + ")");
  return res.json();
}

map.on("load", async () => {
  let fires, roads, points, routes;
  try {
    [steps, fires, roads, points, routes] = await Promise.all([
      load("steps.json"), load("fires.geojson"), load("roads.geojson"),
      load("points.geojson"), load("routes.geojson"),
    ]);
  } catch (err) {
    document.getElementById("clock").textContent = "Error: " + err.message +
      " (run the page through a local server, see README)";
    return;
  }

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
  document.getElementById("s-cut").textContent = s.origins_cut_off + " of " + s.origins_total;
  document.getElementById("s-longest").textContent = s.longest_drive_min == null ? "n/a" : "~" + Math.round(s.longest_drive_min) + " min";
  document.getElementById("s-mean").textContent = s.mean_drive_min == null ? "n/a" : "~" + Math.round(s.mean_drive_min) + " min";
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
