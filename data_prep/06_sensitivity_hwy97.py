"""Sensitivity test: what if the whole official Highway 97 closure (Antlers Beach to Kickininee) is impassable?

This does NOT change the main results. It reruns the end-of-replay numbers under four road scenarios.
Official closure per the Aug 8 BC Emergency Alert and CBC: Hwy 97 from Antlers Beach (lat ~49.739)
to the Pyramid Picnic Area in Kickininee Provincial Park (lat ~49.546). Start time is unknown, so we
test the closure as if it were in place for the whole period, and treat it as closed to everyone (worst case).
"""
import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd
from shapely.geometry import Point

import config

UTM = "EPSG:32611"
CLOSURE_LAT = (49.546, 49.739)
SPEEDS = {"motorway": 100, "trunk": 80, "primary": 60, "secondary": 50, "tertiary": 40,
          "unclassified": 40, "residential": 30, "living_street": 20}      # same defaults as 03_analysis.py

# ---------- Same network, exits, origins and fire-affected roads as 03_analysis.py ----------
G = ox.load_graphml(config.RAW / "roads.graphml")
G = G.subgraph(max(nx.strongly_connected_components(G), key=len)).copy()
G = ox.add_edge_travel_times(ox.add_edge_speeds(G, hwy_speeds=SPEEDS, fallback=40))
G = ox.project_graph(G, to_crs=UTM)
nodes, edges = ox.graph_to_gdfs(G)
edges = edges.reset_index()

f = pd.read_csv(config.RAW / "fires_merged.csv")
pts = gpd.GeoDataFrame(f, geometry=gpd.points_from_xy(f.longitude, f.latitude), crs=4326).to_crs(UTM)
hits = gpd.sjoin(edges[["geometry"]], gpd.GeoDataFrame(geometry=pts.buffer(100)), predicate="intersects")
fire_edges = edges.loc[hits.index.unique()]                          # roads the tool marks as likely affected

is97 = edges["ref"].astype(str).str.contains(r"\b97\b", na=False)
hwy_nodes = nodes.loc[sorted(set(edges[is97].u) | set(edges[is97].v))]
def nearest(lon, lat):
    p = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(UTM).iloc[0]
    return hwy_nodes.geometry.distance(p).idxmin()
exits = [nearest(-119.74, 49.80), hwy_nodes["y"].idxmin(), nearest(-119.59, 49.50)]   # north, south, Penticton

centre = gpd.GeoSeries([Point(-119.677, 49.601)], crs=4326).to_crs(UTM).iloc[0]
near = nodes[nodes.geometry.distance(centre) < 2500].copy()
near["cell"] = list(zip((near.x // 500).astype(int), (near.y // 500).astype(int)))
origins = list(near.groupby("cell").head(1).index)
pop = pd.read_csv(config.RAW / "node_population.csv").set_index("node")["pop"]
pop = pop[pop.index.isin(G.nodes)]

# Official closure: major highway edges (trunk/motorway, including ramps) whose midpoint lies in the closed latitude band
mid = gpd.GeoSeries(edges.geometry.centroid, crs=UTM).to_crs(4326)
band = mid.y.between(*CLOSURE_LAT)
closure = edges[band & edges["highway"].astype(str).str.contains("trunk|motorway")]
print(f"{len(origins)} origins; official-closure edges removed in scenarios C and D: {len(closure)} "
      f"(tool marks {len(fire_edges)} edges from fire, {len(set(fire_edges.index) & set(closure.index))} overlap)")


def run(name, removed):
    H = G.copy()
    H.remove_edges_from(zip(removed.u, removed.v, removed.key))
    dist = nx.multi_source_dijkstra_path_length(H.reverse(copy=False), exits, weight="travel_time")
    times = [dist[o] / 60 for o in origins if o in dist]
    stuck_pop = sum(v for n, v in pop.items() if n not in dist)
    ok = ", ".join(f"{lbl} {nx.shortest_path_length(H, 419468233, e, weight='travel_time') / 60:.0f} min"
                   if nx.has_path(H, 419468233, e) else f"{lbl} none"
                   for lbl, e in zip(["north", "south", "Penticton"], exits))
    print(f"{name:<34} residents cut off ~{round(stuck_pop, -1):>6,.0f} | origins cut off {len(origins) - len(times):>2}/{len(origins)} | "
          f"{'longest %.1f min, mean %.1f min' % (max(times), sum(times) / len(times)) if times else 'no origin can reach any exit'} | "
          f"Summerland centre to: {ok}")


run("A. no fire, no closure", edges.iloc[0:0])
run("B. tool as is (fire marks only)", fire_edges)
run("C. official Hwy 97 closure only", closure)
run("D. fire marks + official closure", pd.concat([fire_edges, closure]).drop_duplicates(["u", "v", "key"]))
