"""Phase 2: mark roads near fire detections, compute drive times to exits, export JSON for the web page."""
import json

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd
from shapely.geometry import Point

import config

CUT_DISTANCE_M = 100          # roads this close to any detection so far are "likely affected" (treated as impassable)
STEP_HOURS = 3
SUMMERLAND = (-119.677, 49.601)   # lon, lat of town centre (approximate)
ORIGIN_RADIUS_M = 2500        # sample origins within this distance of the centre
ORIGIN_GRID_M = 500           # at most one origin per 500 m cell
UTM = "EPSG:32611"            # metres, so buffers and distances are real metres
OUT = config.ROOT / "web" / "data"
OUT.mkdir(parents=True, exist_ok=True)

# Fallback speeds (km/h) used when OSM has no maxspeed tag. These are my assumptions.
DEFAULT_SPEEDS = {"motorway": 100, "trunk": 80, "primary": 60, "secondary": 50, "tertiary": 40,
                  "unclassified": 40, "residential": 30, "living_street": 20}


def step_index(t, steps):
    """Index of the first step whose end time is >= t."""
    return next((k for k, s in enumerate(steps) if t <= s), len(steps) - 1)


# ---------- 1. Roads ----------
G = ox.load_graphml(config.RAW / "roads.graphml")
# Keep only the main connected piece so every node can reach every other node
biggest = max(nx.strongly_connected_components(G), key=len)
print(f"Roads: {len(G.nodes)} nodes; keeping {len(biggest)} in the main connected network")
G = G.subgraph(biggest).copy()

edges_raw = ox.graph_to_gdfs(G, nodes=False)
print(f"Edges with a real maxspeed tag in OSM: {edges_raw['maxspeed'].notna().mean():.0%} "
      "(the rest use default speeds by road type)")
G = ox.add_edge_speeds(G, hwy_speeds=DEFAULT_SPEEDS, fallback=40)
G = ox.add_edge_travel_times(G)          # adds travel_time in seconds
G = ox.project_graph(G, to_crs=UTM)
nodes, edges = ox.graph_to_gdfs(G)
edges = edges.reset_index()              # columns u, v, key, ...

# ---------- 2. Fires and when roads are likely affected ----------
fires = pd.read_csv(config.RAW / "fires_merged.csv")
fires["time_pacific"] = pd.to_datetime(fires["time_utc"], utc=True).dt.tz_convert(config.TIMEZONE)
fires = fires.sort_values("time_pacific").reset_index(drop=True)
fire_pts = gpd.GeoDataFrame(fires, geometry=gpd.points_from_xy(fires.longitude, fires.latitude), crs=4326).to_crs(UTM)

# For each road: the time of the EARLIEST detection within CUT_DISTANCE_M = when it is likely affected
buffers = fire_pts[["time_pacific", "geometry"]].copy()
buffers["geometry"] = buffers.buffer(CUT_DISTANCE_M)
hits = gpd.sjoin(edges[["geometry"]], buffers, predicate="intersects")
edges["affected_time"] = hits.groupby(level=0)["time_pacific"].min()
print(f"Roads likely affected by the end: {edges['affected_time'].notna().sum()} of {len(edges)} edges")

# ---------- 3. Time steps (every 3 h, Pacific) ----------
first = fires["time_pacific"].min().floor(f"{STEP_HOURS}h")
last = fires["time_pacific"].max()
# each step = "everything detected up to this time"
steps = list(pd.date_range(first + pd.Timedelta(hours=STEP_HOURS), last + pd.Timedelta(hours=STEP_HOURS),
                           freq=f"{STEP_HOURS}h"))
print(f"{len(steps)} steps from {steps[0]} to {steps[-1]}")

# ---------- 4. Exits (confirmed: Hwy 97 north end and south end of the map) ----------
is97 = edges["ref"].astype(str).str.contains(r"\b97\b", na=False)   # BC 97, not 97C
hwy_nodes = nodes.loc[sorted(set(edges[is97].u) | set(edges[is97].v))]
# Third exit: the Hwy 97 node closest to central Penticton (assumed "nearest safe town")
penticton = gpd.GeoSeries([Point(-119.59, 49.50)], crs=4326).to_crs(UTM).iloc[0]
exit_penticton = hwy_nodes.geometry.distance(penticton).idxmin()
# North exit: Hwy 97 node just north of Peachland (replaces the far-away Kelowna end of the map)
peachland_n = gpd.GeoSeries([Point(-119.74, 49.80)], crs=4326).to_crs(UTM).iloc[0]
exit_north = hwy_nodes.geometry.distance(peachland_n).idxmin()
exits = [exit_north, hwy_nodes["y"].idxmin(), exit_penticton]       # north of Peachland, far south, Penticton
exit_ll = gpd.GeoSeries(nodes.loc[exits].geometry, crs=UTM).to_crs(4326)
for name, n in zip(["north (Peachland)", "south", "Penticton"], exits):
    print(f"Exit {name}: node {n} at lon {exit_ll[n].x:.4f}, lat {exit_ll[n].y:.4f}")

# ---------- 5. Origins: one node per 500 m cell within 2.5 km of Summerland ----------
centre = gpd.GeoSeries([Point(SUMMERLAND)], crs=4326).to_crs(UTM).iloc[0]
near = nodes[nodes.geometry.distance(centre) < ORIGIN_RADIUS_M].copy()
near["cell"] = list(zip((near.x // ORIGIN_GRID_M).astype(int), (near.y // ORIGIN_GRID_M).astype(int)))
origins = list(near.groupby("cell").head(1).index)
print(f"{len(origins)} origin points sampled in Summerland")

# ---------- 6. Drive times per step ----------
results = []
routes = []
for i, t in enumerate(steps):
    cut = edges[edges["affected_time"].notna() & (edges["affected_time"] <= t)]
    H = G.copy()
    H.remove_edges_from(zip(cut.u, cut.v, cut.key))
    # Search backwards from the exits: gives each node's drive time to the NEAREST exit
    dist = nx.multi_source_dijkstra_path_length(H.reverse(copy=False), exits, weight="travel_time")
    times = {o: dist[o] / 60 for o in origins if o in dist}       # minutes
    cut_off = [o for o in origins if o not in dist]
    worst = max(times, key=times.get) if times else None
    res = {"step": i, "time": t.isoformat(),
           "fires_so_far": int((fires["time_pacific"] <= t).sum()),
           "roads_affected": int(len(cut)),
           "origins_total": len(origins), "origins_cut_off": len(cut_off),
           "longest_drive_min": round(times[worst], 1) if worst else None,
           "mean_drive_min": round(sum(times.values()) / len(times), 1) if times else None}
    results.append(res)
    if worst:   # route of the origin with the longest drive, to draw on the map
        reachable = [e for e in exits if nx.has_path(H, worst, e)]
        best_exit = min(reachable, key=lambda e: nx.shortest_path_length(H, worst, e, weight="travel_time"))
        path = nx.shortest_path(H, worst, best_exit, weight="travel_time")
        pts = gpd.GeoSeries(nodes.loc[path].geometry.values, crs=UTM).to_crs(4326)
        routes.append({"type": "Feature", "properties": {"step": i, "minutes": round(times[worst], 1)},
                       "geometry": {"type": "LineString", "coordinates": [[round(p.x, 5), round(p.y, 5)] for p in pts]}})
    print(f"{t:%a %d %H:%M}  fires={res['fires_so_far']:5d}  roads affected={res['roads_affected']:4d}  "
          f"cut off={res['origins_cut_off']:2d}/{len(origins)}  longest={res['longest_drive_min']} min  "
          f"mean={res['mean_drive_min']} min")

# ---------- 7. Export (WGS84 GeoJSON, 5 decimals ~ 1 m) ----------
f_out = fire_pts[["time_pacific", "source", "geometry"]].to_crs(4326)
f_out["step"] = f_out["time_pacific"].apply(lambda x: step_index(x, steps))
f_out["time"] = f_out["time_pacific"].apply(lambda x: x.isoformat())
f_out.drop(columns="time_pacific").to_file(OUT / "fires.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)

# Roads: OSM stores each two-way road as two edges; keep one per pair (the earliest time)
edges["pair"] = [str(sorted([u, v])) for u, v in zip(edges.u, edges.v)]
r = edges.sort_values("affected_time", na_position="last").drop_duplicates("pair").copy()
r["name"] = r["name"].astype(str).replace("nan", "")
r["highway"] = r["highway"].astype(str)
r["affected_step"] = r["affected_time"].apply(lambda x: step_index(x, steps) if pd.notna(x) else None)
r["affected_time"] = r["affected_time"].apply(lambda x: x.isoformat() if pd.notna(x) else None)
gpd.GeoDataFrame(r[["name", "highway", "affected_time", "affected_step", "geometry"]], crs=UTM).to_crs(4326).to_file(
    OUT / "roads.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)

pts = gpd.GeoDataFrame({"kind": ["exit"] * len(exits) + ["origin"] * len(origins)},
                       geometry=list(nodes.loc[exits + origins].geometry), crs=UTM)
pts.to_crs(4326).to_file(OUT / "points.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)
(OUT / "routes.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": routes}))
(OUT / "steps.json").write_text(json.dumps(results, indent=1))
print("\nExported to", OUT)
for p in sorted(OUT.iterdir()):
    print(f"  {p.name}: {p.stat().st_size / 1e6:.2f} MB")
