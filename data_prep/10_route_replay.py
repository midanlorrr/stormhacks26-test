"""Step 10: route replay. For a few preset starting points, find the fastest route to an exit at every time step,
in two separate "what if" scenarios:
  fire   = roads within 100 m of a satellite detection are impassable (what the rest of the tool does)
  closure = the official Highway 97 closure (Antlers Beach to Pyramid Picnic Area) is impassable from its first documented
            time, 12:45 pm PDT on Aug 8 (BC Emergency Alert). Fire marks are NOT used in this scenario.
The two are never combined: together they seal in every starting point, which cannot be what happened.

Run with no presets chosen (PRESETS empty) to print the exploration table used to choose them.
With presets, it also writes web/data/route_replay.json. Does not change any other output.
"""
import json
from collections import Counter

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd
from shapely.geometry import LineString, Point

import config

UTM = "EPSG:32611"
SPEEDS = {"motorway": 100, "trunk": 80, "primary": 60, "secondary": 50, "tertiary": 40,
          "unclassified": 40, "residential": 30, "living_street": 20}      # same defaults as 03_analysis.py
CUT_DISTANCE_M = 100                  # same rule as 03_analysis.py
CLOSURE_LAT = (49.546, 49.739)        # official Highway 97 closure, as in 06_sensitivity_hwy97.py
CLOSURE_START = pd.Timestamp("2026-08-08 12:45", tz=config.TIMEZONE)      # BC Emergency Alert: the first documented time
STEP_HOURS = 3
AREA_M = 1000
CHECK_STEPS = [1, 10, 15, 25]         # 1-based step numbers to print in the exploration table
OUT = config.ROOT / "web" / "data"

# Starting points chosen after the exploration: area grid cell "x_y" (km, as in area_cut_shares.json) and a short label.
PRESETS = [
    ("303_5497", "Prairie Valley Road (west)"),
    ("304_5497", "Morrow Avenue (west of town)"),
    ("304_5496", "Dale Meadows Road"),
    ("305_5497", "Sinclair Road (town)"),
    ("306_5498", "Turner Street (north of centre)"),
    ("309_5494", "Okanagan Highway (Trout Creek)"),
    ("306_5500", "Sumac Ridge Drive (north end)"),
    ("309_5493", "Okanagan Highway (south, Trout Creek)"),
    ("301_5515", "Princeton Avenue (Peachland)"),
    ("313_5483", "Government Street (Penticton)"),
]
PREVIEW = False           # True: print the table for the presets and stop; False: write web/data/route_replay.json

# ---------- network, exits, fire-affected roads: the same set-up as 03_analysis.py ----------
G = ox.load_graphml(config.RAW / "roads.graphml")
G = G.subgraph(max(nx.strongly_connected_components(G), key=len)).copy()
G = ox.add_edge_travel_times(ox.add_edge_speeds(G, hwy_speeds=SPEEDS, fallback=40))
G = ox.project_graph(G, to_crs=UTM)
nodes, edges = ox.graph_to_gdfs(G)
edges = edges.reset_index()

fires = pd.read_csv(config.RAW / "fires_merged.csv")
fires["time_pacific"] = pd.to_datetime(fires["time_utc"], utc=True).dt.tz_convert(config.TIMEZONE)
fire_pts = gpd.GeoDataFrame(fires, geometry=gpd.points_from_xy(fires.longitude, fires.latitude), crs=4326).to_crs(UTM)
buffers = fire_pts[["time_pacific", "geometry"]].copy()
buffers["geometry"] = buffers.buffer(CUT_DISTANCE_M)
hits = gpd.sjoin(edges[["geometry"]], buffers, predicate="intersects")
edges["affected_time"] = hits.groupby(level=0)["time_pacific"].min()

first = fires["time_pacific"].min().floor(f"{STEP_HOURS}h")
steps = list(pd.date_range(first + pd.Timedelta(hours=STEP_HOURS), fires["time_pacific"].max() + pd.Timedelta(hours=STEP_HOURS),
                           freq=f"{STEP_HOURS}h"))

is97 = edges["ref"].astype(str).str.contains(r"\b97\b", na=False)
hwy_nodes = nodes.loc[sorted(set(edges[is97].u) | set(edges[is97].v))]
def nearest_hwy(lon, lat):
    p = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(UTM).iloc[0]
    return hwy_nodes.geometry.distance(p).idxmin()
exits = [nearest_hwy(-119.74, 49.80), hwy_nodes["y"].idxmin(), nearest_hwy(-119.59, 49.50)]   # north, far south, Penticton

# official closure edges (Highway 97 trunk/motorway between the two latitudes), as in 06_sensitivity_hwy97.py
mid = gpd.GeoSeries(edges.geometry.centroid, crs=UTM).to_crs(4326)
closure = edges[mid.y.between(*CLOSURE_LAT) & edges["highway"].astype(str).str.contains("trunk|motorway")]

# ---------- candidate starting points: one road node for each populated 1 km area ----------
pop = pd.read_csv(config.RAW / "node_population.csv").set_index("node")["pop"]
pop = pop[pop.index.isin(G.nodes)]
xy = nodes.loc[pop.index]
cell = pd.Series(list(zip((xy.x // AREA_M).astype(int), (xy.y // AREA_M).astype(int))), index=pop.index)
street = {}
for u, name in zip(edges.u, edges["name"]):
    street.setdefault(u, str(name) if isinstance(name, str) else "")
candidates = []
for key, members in cell.groupby(cell):
    p = pop[list(members.index)]
    if p.sum() < 20:
        continue
    node = p.idxmax()                                          # the node holding the most residents in the square
    names = Counter(street[n] for n in members.index if street.get(n))
    candidates.append({"cell": f"{key[0]}_{key[1]}", "node": node, "residents": int(round(p.sum(), -1)),
                       "road": names.most_common(1)[0][0] if names else "unnamed roads"})
lonlat = gpd.GeoSeries(nodes.loc[[c["node"] for c in candidates]].geometry, crs=UTM).to_crs(4326)
for c, pt in zip(candidates, lonlat):
    c["lon"], c["lat"] = round(pt.x, 5), round(pt.y, 5)
print(f"{len(candidates)} populated 1 km areas; {len(steps)} steps ({steps[0]:%b %d %H:%M} to {steps[-1]:%b %d %H:%M}); "
      f"closure edges: {len(closure)}; closure starts with step {next(i for i, t in enumerate(steps) if t >= CLOSURE_START) + 1}")


# ---------- fastest routes at every step, in each scenario ----------
def removed_edges(scenario, t):
    if scenario == "fire":
        return edges[edges["affected_time"].notna() & (edges["affected_time"] <= t)]
    return closure if t >= CLOSURE_START else edges.iloc[0:0]


def graph_at(scenario, t):
    """The road network with this scenario's closed roads taken out, at time t."""
    H = G.copy()
    r = removed_edges(scenario, t)
    H.remove_edges_from(zip(r.u, r.v, r.key))
    return H


def routes_at(scenario, t):
    """For every node: (minutes, path to the nearest exit), or nothing if it cannot reach an exit."""
    H = graph_at(scenario, t)
    dist, paths = nx.multi_source_dijkstra(H.reverse(copy=False), exits, weight="travel_time")
    return {n: (dist[n] / 60, tuple(reversed(paths[n]))) for n in dist}         # paths run exit -> node on the reversed graph


results = {}                       # (scenario, step index) -> {node: (minutes, path)}
for scenario in ("fire", "closure"):
    for i, t in enumerate(steps):
        results[(scenario, i)] = routes_at(scenario, t)


def summary(c, scenario):
    """One line of facts about how a candidate's route behaves in one scenario."""
    series = [results[(scenario, i)].get(c["node"]) for i in range(len(steps))]
    minutes = [s[0] if s else None for s in series]
    paths = [s[1] if s else None for s in series]
    return {"minutes": minutes, "changes": len({p for p in paths if p}) > 1, "no_route": any(m is None for m in minutes),
            "slower": any(m is not None and minutes[0] is not None and m > minutes[0] + 0.5 for m in minutes)}


for c in candidates:
    c["fire"], c["closure"] = summary(c, "fire"), summary(c, "closure")

if PREVIEW or not PRESETS:
    fmt = lambda m: "none" if m is None else f"{m:4.0f}"
    pick = lambda s: " ".join(fmt(s["minutes"][k - 1]) for k in CHECK_STEPS)
    print("\nBehaviour counts over the 280 areas:")
    for sc in ("fire", "closure"):
        n = sum(c[sc]["changes"] for c in candidates)
        nr = sum(c[sc]["no_route"] for c in candidates)
        print(f"  {sc:<8} route changes for {n} areas; no route at some step for {nr} areas")
    print(f"\n{'cell':<9} {'residents':>9}  {'lon':>10} {'lat':>8}  {'road':<28} | fire min @steps {CHECK_STEPS} | closure min @steps {CHECK_STEPS} | flags")
    chosen = {k for k, _ in PRESETS}
    show = [c for c in candidates if c['cell'] in chosen] if PRESETS else [c for c in candidates if c["fire"]["changes"] or c["closure"]["changes"] or c["fire"]["no_route"] or c["closure"]["no_route"]
            or (-119.76 < c["lon"] < -119.60 and 49.53 < c["lat"] < 49.66)]
    for c in sorted(show, key=lambda c: (-c["fire"]["changes"], -c["closure"]["changes"], -c["residents"])):
        flags = ",".join(k for k, v in [("fire-changes", c["fire"]["changes"]), ("fire-noroute", c["fire"]["no_route"]),
                                         ("closure-changes", c["closure"]["changes"]), ("closure-noroute", c["closure"]["no_route"])] if v)
        print(f"{c['cell']:<9} {c['residents']:>9,}  {c['lon']:>10.4f} {c['lat']:>8.4f}  {c['road'][:28]:<28} | {pick(c['fire'])} | {pick(c['closure'])} | {flags}")
    print("\nFire-only areas that change, minutes at every step (None = no route):")
    for c in candidates:
        if c["fire"]["changes"] or c["fire"]["no_route"]:
            print(f"  {c['cell']} {c['road'][:24]:<24}", [None if m is None else round(m) for m in c["fire"]["minutes"]])
    print("\nAreas whose route never changes in either scenario (lon -119.9 to -119.55), largest first:")
    quiet = [c for c in candidates if not (c["fire"]["changes"] or c["closure"]["changes"] or c["fire"]["no_route"] or c["closure"]["no_route"])
             and -119.9 < c["lon"] < -119.55]
    for c in sorted(quiet, key=lambda c: -c["residents"])[:14]:
        print(f"  {c['cell']:<9} {c['residents']:>6,} {c['lon']:.4f} {c['lat']:.4f} {c['road'][:28]:<28} {c['fire']['minutes'][0]:.0f} min")
    print("\nPopulated areas west of -119.72 (Faulder, Prairie Valley and beyond):")
    for c in sorted([c for c in candidates if c["lon"] < -119.72], key=lambda c: -c["residents"])[:10]:
        print(f"  {c['cell']:<9} {c['residents']:>6,} {c['lon']:.4f} {c['lat']:.4f} {c['road'][:28]:<28} fire {c['fire']['minutes'][0]:.0f} -> {c['fire']['minutes'][-1] and round(c['fire']['minutes'][-1])}")
    raise SystemExit


# ---------- export: for each preset, scenario and step, the route (geometry) and its estimated minimum drive time ----------
by_cell = {c["cell"]: c for c in candidates}
to_lonlat = lambda xs, ys: gpd.GeoSeries(gpd.points_from_xy(xs, ys), crs=UTM).to_crs(4326)


def route_line(H, path):
    """The route as one line in map metres: use each road piece's real shape when OSM has one."""
    coords = []
    for a, b in zip(path[:-1], path[1:]):
        pieces = H.get_edge_data(a, b)
        best = min(pieces.values(), key=lambda d: d["travel_time"])         # the quicker of any parallel roads
        line = list(best["geometry"].coords) if "geometry" in best else [(nodes.loc[a].x, nodes.loc[a].y), (nodes.loc[b].x, nodes.loc[b].y)]
        if coords and coords[-1] == line[0]:
            line = line[1:]
        coords += line
    return LineString(coords).simplify(5)                                  # 5 m is plenty for a line on this map


out = {"closure_start": CLOSURE_START.isoformat(),
       "closure_first_step": next(i for i, t in enumerate(steps) if t >= CLOSURE_START),         # 0-based index of the first step with the closure
       "steps": [t.isoformat() for t in steps],
       "origins": []}
for cell_id, label in PRESETS:
    c = by_cell[cell_id]
    out["origins"].append({"id": cell_id, "label": label, "road": c["road"], "residents": c["residents"], "lon": c["lon"], "lat": c["lat"],
                           "fire": {"routes": [], "at": []}, "closure": {"routes": [], "at": []}})

for scenario in ("fire", "closure"):
    for i, t in enumerate(steps):
        H = graph_at(scenario, t)
        for (cell_id, _), entry in zip(PRESETS, out["origins"]):
            node = by_cell[cell_id]["node"]
            found = results[(scenario, i)].get(node)
            block = entry[scenario]
            if found is None:
                block["at"].append(-1)                                     # no route to any exit at this step
                continue
            minutes, path = found
            known = next((k for k, r in enumerate(block["routes"]) if r["path"] == path), None)
            if known is None:
                line = route_line(H, path)
                xs, ys = zip(*line.coords)
                pts = to_lonlat(xs, ys)
                block["routes"].append({"path": path, "minutes": round(minutes, 1), "coords": [[round(p.x, 5), round(p.y, 5)] for p in pts]})
                known = len(block["routes"]) - 1
            else:                                                          # same road path, but keep the time of the first step it appeared
                pass
            block["at"].append(known)
            block.setdefault("minutes_at", {})[i] = round(minutes, 1)

# every step gets its own minutes (the same road path can take slightly different times only if speeds changed; they do not)
for entry in out["origins"]:
    for scenario in ("fire", "closure"):
        block = entry[scenario]
        block["minutes"] = [None if k < 0 else block["minutes_at"][i] for i, k in enumerate(block["at"])]
        del block["minutes_at"]
        for r in block["routes"]:
            del r["path"]
            del r["minutes"]
(OUT / "route_replay.json").write_text(json.dumps(out, separators=(",", ":")))
size = (OUT / "route_replay.json").stat().st_size
print(f"Wrote route_replay.json: {size / 1024:.0f} KB for {len(PRESETS)} starting points")
for entry in out["origins"]:
    print(f"  {entry['id']:<9} {entry['label']:<38} fire: {len(entry['fire']['routes'])} route(s), no route at {entry['fire']['at'].count(-1):>2} steps | "
          f"closure: {len(entry['closure']['routes'])} route(s), no route at {entry['closure']['at'].count(-1):>2} steps")
