"""Phase 2: mark roads near fire detections, compute drive times to exits, export JSON for the web page."""
import json
from collections import Counter

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd
from shapely.geometry import Point
from shapely.ops import linemerge

import config

CUT_DISTANCE_M = 100          # roads this close to any detection so far are "likely affected" (treated as impassable)
LOW_CUT_DISTANCE_M = 50       # a tighter rule, used only for the LOW end of the "residents cut off" range
STEP_HOURS = 3
SUMMERLAND = (-119.677, 49.601)   # lon, lat of town centre (approximate)
ORIGIN_RADIUS_M = 2500        # sample origins within this distance of the centre
ORIGIN_GRID_M = 500           # at most one origin per 500 m cell
AREA_M = 1000                # population areas are 1 km squares
TIGHT_SHARE = 0.25            # flag an area if its drive time is >= 25% of the time before it was cut off
NEVER = pd.Timestamp("2100-01-01", tz=config.TIMEZONE)   # stands in for "never cut off"
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

# Same thing with the tighter distance: gives the low estimate of residents cut off
low_buffers = fire_pts[["time_pacific", "geometry"]].copy()
low_buffers["geometry"] = low_buffers.buffer(LOW_CUT_DISTANCE_M)
low_hits = gpd.sjoin(edges[["geometry"]], low_buffers, predicate="intersects")
edges["affected_time_low"] = low_hits.groupby(level=0)["time_pacific"].min()

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

# ---------- 5b. Residents: when does each road node lose every route to an exit? ----------
# node_population.csv comes from 05_population.py: WorldPop people assigned to their nearest road node
pop = pd.read_csv(config.RAW / "node_population.csv").set_index("node")["pop"]
pop = pop[pop.index.isin(G.nodes)]
t0 = fires["time_pacific"].min()                       # first detection

# Remove affected roads one detection time at a time (they only ever get removed, never restored)
# and note the first time each populated node can no longer reach any exit.
def cut_off_times(time_column):
    found = {}
    H = G.copy()
    for t, grp in edges.dropna(subset=[time_column]).groupby(time_column):
        H.remove_edges_from(zip(grp.u, grp.v, grp.key))
        reachable = nx.multi_source_dijkstra_path_length(H.reverse(copy=False), exits)
        for n in pop.index:
            if n not in reachable and n not in found:
                found[n] = t
    return found

node_cut_time = cut_off_times("affected_time")            # 100 m rule: the main (high) estimate
node_cut_time_low = cut_off_times("affected_time_low")    # 50 m rule: the low estimate
print(f"{len(node_cut_time)} of {len(pop)} populated road nodes lose every route to an exit "
      f"(~{pop[list(node_cut_time)].sum():,.0f} of {pop.sum():,.0f} people in the study box); "
      f"with the {LOW_CUT_DISTANCE_M} m rule: ~{pop[list(node_cut_time_low)].sum():,.0f}")

# Baseline drive time (no fire at all) from every node to its nearest exit, in minutes
base = nx.multi_source_dijkstra_path_length(G.reverse(copy=False), exits, weight="travel_time")

# Group populated nodes into 1 km squares ("areas") and work out the race for each one
street = {}                                            # a street name for each node, to label areas
for u, name in zip(edges.u, edges["name"]):
    street.setdefault(u, str(name) if isinstance(name, str) else "")
xy = nodes.loc[pop.index]
area_id = pd.Series(list(zip((xy.x // AREA_M).astype(int), (xy.y // AREA_M).astype(int))), index=pop.index)
areas = []
cell_shares = []                                       # extra output for the click-to-inspect card (see below)
for cell_key, members in area_id.groupby(area_id):
    ids = list(members.index)
    p = pop[ids]
    if p.sum() < 20:                                   # skip nearly empty squares
        continue
    # "Cut off" = the time by which at least half of the area's residents have lost every route
    cum = 0
    cut_time = None
    for n in sorted(ids, key=lambda n: node_cut_time.get(n, NEVER)):
        if n not in node_cut_time:
            break
        cum += p[n]
        if cum >= p.sum() / 2:
            cut_time = node_cut_time[n]
            break
    drive = float((p * pd.Series({n: base[n] / 60 for n in ids})).sum() / p.sum())   # people-weighted minutes
    window = (cut_time - t0).total_seconds() / 60 if cut_time is not None else None
    centre = gpd.GeoSeries([Point((xy.loc[ids, "x"] * p).sum() / p.sum(), (xy.loc[ids, "y"] * p).sum() / p.sum())], crs=UTM).to_crs(4326).iloc[0]
    names = Counter(street[n] for n in ids if street.get(n))
    areas.append({"name": "near " + names.most_common(1)[0][0] if names else "unnamed roads",
                  "residents": int(round(p.sum(), -1)), "baseline_drive_min": round(drive, 1),
                  "cut_time": cut_time, "window_min": round(window) if window is not None else None,
                  "drive_share": round(drive / window, 2) if window else None,
                  "geometry": centre})
    cell_shares.append({"key": cell_key, "ids": ids, "p": p, "drive": round(drive, 1), "name": areas[-1]["name"]})
cut_areas = [a for a in areas if a["cut_time"] is not None]
print(f"\n{len(areas)} populated 1 km areas; {len(cut_areas)} get cut off. Time from first detection ({t0:%a %H:%M}) to cut-off:")
for a in sorted(cut_areas, key=lambda a: -a["residents"])[:8]:
    print(f"  {a['name']:<32} ~{a['residents']:>5} residents  cut off {a['cut_time']:%a %H:%M}  window {a['window_min']:>4} min  "
          f"est. drive {a['baseline_drive_min']:>4} min  share {a['drive_share']:.0%}")
tight = [a for a in cut_areas if a["drive_share"] >= TIGHT_SHARE]
print(f"Areas where the drive is >= {TIGHT_SHARE:.0%} of the time before cut-off: {len(tight)}")

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
    residents = sum(v for n, v in pop.items() if node_cut_time.get(n, NEVER) <= t)
    residents_low = sum(v for n, v in pop.items() if node_cut_time_low.get(n, NEVER) <= t)
    worst = max(times, key=times.get) if times else None
    res = {"step": i, "time": t.isoformat(), "first_detection": t0.isoformat(),
           "fires_so_far": int((fires["time_pacific"] <= t).sum()),
           "roads_affected": int(len(cut)),
           "origins_total": len(origins), "residents_cut_off": int(round(residents, -1)),
           "residents_cut_off_low": int(round(residents_low, -1)),
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
          f"residents cut off~{res['residents_cut_off']:>6,}  longest={res['longest_drive_min']} min  "
          f"mean={res['mean_drive_min']} min")

# ---------- 6b. Cross-check against the official fire perimeter (needs the BCWS shapefile in data_raw/) ----------
official_boundary_residents = None
perimeter_file = config.RAW / "bcws_perimeters" / "prot_current_fire_polys.shp"
if perimeter_file.exists():
    perimeter = gpd.read_file(perimeter_file)
    perimeter = perimeter[perimeter["FIRE_NUM"] == "K51490"].to_crs(UTM).geometry.union_all()
    inside = edges[edges.geometry.intersects(perimeter)]
    H = G.copy()
    H.remove_edges_from(zip(inside.u, inside.v, inside.key))
    reachable = nx.multi_source_dijkstra_path_length(H.reverse(copy=False), exits)
    official_boundary_residents = int(round(sum(v for n, v in pop.items() if n not in reachable), -1))
    print(f"Cross-check: closing every road that touches the official perimeter leaves ~{official_boundary_residents:,} residents cut off")
else:
    print("Cross-check skipped: download the BCWS perimeter first (see README)")

# ---------- 7. Export (WGS84 GeoJSON, 5 decimals ~ 1 m) ----------
f_out = fire_pts[["time_pacific", "source", "geometry"]].to_crs(4326)
f_out["step"] = f_out["time_pacific"].apply(lambda x: step_index(x, steps))
f_out["time"] = f_out["time_pacific"].apply(lambda x: x.isoformat())
f_out.drop(columns="time_pacific").to_file(OUT / "fires.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)

# Roads: OSM stores each two-way road as two edges; keep one per pair (the earliest time)
edges["pair"] = [str(sorted([u, v])) for u, v in zip(edges.u, edges.v)]
r = edges.sort_values("affected_time", na_position="last").drop_duplicates("pair").copy()
# OSM tags can be a list (a road with two values) or missing; keep one plain text value for the map
def plain(v):
    if isinstance(v, list):
        v = v[0] if v else ""
    return "" if v is None or str(v) == "nan" else str(v)
for col in ("name", "highway", "ref"):
    r[col] = r[col].apply(plain)
r["affected_step"] = r["affected_time"].apply(lambda x: step_index(x, steps) if pd.notna(x) else None)
r["affected_time"] = r["affected_time"].apply(lambda x: x.isoformat() if pd.notna(x) else None)
gpd.GeoDataFrame(r[["name", "highway", "ref", "affected_time", "affected_step", "geometry"]], crs=UTM).to_crs(4326).to_file(
    OUT / "roads.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)

# Labels for the roads the map always names (Highway 97 and two others). OSM chops a road into many short pieces,
# which are too short for a text label to fit, so merge each road's pieces into longer lines.
ALWAYS_LABELLED = ["Princeton-Summerland Road", "Prairie Valley Road"]      # keep in sync with web/app.js
named = r[r["ref"].isin(["BC 97", "97"]) | r["name"].isin(ALWAYS_LABELLED)].copy()
named["label"] = named.apply(lambda row: "Highway 97" if row["ref"] in ("BC 97", "97") else row["name"], axis=1)
label_rows = []
for label, grp in named.groupby("label"):
    merged = linemerge(list(grp.geometry))
    # simplify(30 m): smooth out tiny zigzags, since text can only follow fairly straight lines (labels only; the road lines are untouched)
    label_rows += [{"label": label, "geometry": g.simplify(30)} for g in (merged.geoms if hasattr(merged, "geoms") else [merged])]
gpd.GeoDataFrame(label_rows, crs=UTM).to_crs(4326).to_file(OUT / "road_labels.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)

pts = gpd.GeoDataFrame({"kind": ["exit"] * len(exits) + ["origin"] * len(origins)},
                       geometry=list(nodes.loc[exits + origins].geometry), crs=UTM)
pts.to_crs(4326).to_file(OUT / "points.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)
area_gdf = gpd.GeoDataFrame([{**a, "cut_step": step_index(a["cut_time"], steps) if a["cut_time"] is not None else None,
                              "cut_time": a["cut_time"].isoformat() if a["cut_time"] is not None else None,
                              "tight": bool(a["drive_share"] is not None and a["drive_share"] >= TIGHT_SHARE)}
                             for a in areas], crs=4326)
area_gdf.to_file(OUT / "areas.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)

# ---------- 7b. Per 1 km area: % of estimated residents with no route to any exit, at every step ----------
# "hi" uses the 100 m rule (the main estimate), "lo" the 50 m rule. Used by the click-to-inspect card on the page.
def shares_for(cut_times, ids, p):
    """Whole percent of the area's residents cut off at each step, and the same as residents (for the cross-check below)."""
    people = [sum(p[n] for n in ids if cut_times.get(n, NEVER) <= t) for t in steps]
    return [int(round(100 * v / p.sum())) for v in people], people

def first_cut(cut_times, ids, p):
    """Time the first road node holding at least about one estimated resident loses every route (None if never)."""
    times = [cut_times[n] for n in ids if n in cut_times and p[n] >= 1]
    return min(times).isoformat() if times else None

cells_out, check_hi, check_lo, display_hi, display_lo = [], [0.0] * len(steps), [0.0] * len(steps), [0] * len(steps), [0] * len(steps)
for c in cell_shares:
    hi, people_hi = shares_for(node_cut_time, c["ids"], c["p"])
    lo, people_lo = shares_for(node_cut_time_low, c["ids"], c["p"])
    residents = int(round(c["p"].sum(), -1))
    cells_out.append({"x": int(c["key"][0]), "y": int(c["key"][1]), "name": c["name"], "residents": residents, "drive": c["drive"],
                      "hi": hi, "lo": lo, "first_hi": first_cut(node_cut_time, c["ids"], c["p"]), "first_lo": first_cut(node_cut_time_low, c["ids"], c["p"])})
    for i in range(len(steps)):
        check_hi[i] += people_hi[i]
        check_lo[i] += people_lo[i]
        display_hi[i] += residents * (round(hi[i] / 10) * 10) / 100          # what a reader gets by multiplying the card's numbers
        display_lo[i] += residents * (round(lo[i] / 10) * 10) / 100
(OUT / "area_cut_shares.json").write_text(json.dumps({"cell_m": AREA_M, "crs": UTM, "cells": cells_out}, separators=(",", ":")))

# Cross-check: do the per-area numbers add up to the headline "residents cut off"?
print("\nReconciliation of area_cut_shares.json with steps.json (residents cut off; 100 m rule = high, 50 m rule = low)")
print("step  time          headline_hi  sum_areas_hi  sum_displayed_hi | headline_lo  sum_areas_lo  sum_displayed_lo")
for i, t in enumerate(steps):
    h = results[i]
    print(f"{i:>4}  {t:%a %d %H:%M}  {h['residents_cut_off']:>10,}  {check_hi[i]:>12,.0f}  {display_hi[i]:>16,.0f} | "
          f"{h['residents_cut_off_low']:>10,}  {check_lo[i]:>12,.0f}  {display_lo[i]:>16,.0f}")
tiny = {n for n in pop.index} - {n for c in cell_shares for n in c["ids"]}
print(f"Last step, exact: all nodes {sum(pop[n] for n in pop.index if node_cut_time.get(n, NEVER) <= steps[-1]):,.1f}; "
      f"in the 280 squares {check_hi[-1]:,.1f}; in squares under 20 residents {sum(pop[n] for n in tiny if node_cut_time.get(n, NEVER) <= steps[-1]):,.1f}")
print(f"Residents in squares of fewer than 20 people (no entry on the card): {pop.sum() - sum(c['p'].sum() for c in cell_shares):,.0f} of {pop.sum():,.0f}")
(OUT / "routes.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": routes}))
(OUT / "steps.json").write_text(json.dumps(results, indent=1))
(OUT / "crosschecks.json").write_text(json.dumps({"official_boundary_residents": official_boundary_residents}, indent=1))
print("\nExported to", OUT)
for p in sorted(OUT.iterdir()):
    print(f"  {p.name}: {p.stat().st_size / 1e6:.2f} MB")
