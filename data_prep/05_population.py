"""Get open gridded population (WorldPop) for the study area and assign it to road nodes.

Source: WorldPop Global2 R2025A, Canada, 100 m, constrained population counts for 2025
(CC BY 4.0, WorldPop / University of Southampton, DOI 10.5258/SOTON/WP00839; WorldPop labels it alpha).
The full Canada file is ~200 MB; we download it once, keep only our bounding box, and cache that small clip.
"""
import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import requests
import rasterio
from rasterio.windows import from_bounds

import config

URL = ("https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2025/CAN/v1/100m/constrained/"
       "can_pop_2025_CN_100m_R2025A_v1.tif")
CLIP = config.RAW / "worldpop_can_2025_clip.tif"
OUT = config.RAW / "node_population.csv"
UTM = "EPSG:32611"
MAX_SNAP_M = 1500     # a populated cell further than this from any road node is dropped (and reported)

# ---------- 1. Download once, keep only our window (cached) ----------
# The server ignores partial-download requests, so we fetch the whole Canada file (~200 MB),
# cut out our bounding box, and delete the big file again.
if CLIP.exists():
    print("Using cached clip:", CLIP.name)
else:
    full = config.RAW / "worldpop_can_2025_full.tif"
    print("Downloading the Canada file (~200 MB), one time only...")
    with requests.get(URL, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(full, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    with rasterio.open(full) as src:
        win = from_bounds(config.WEST, config.SOUTH, config.EAST, config.NORTH, src.transform).round_offsets().round_lengths()
        data = src.read(1, window=win)
        profile = src.profile | {"height": data.shape[0], "width": data.shape[1],
                                 "transform": src.window_transform(win), "tiled": False, "compress": "deflate"}
        profile.pop("blockxsize", None)
        profile.pop("blockysize", None)
    with rasterio.open(CLIP, "w", **profile) as dst:
        dst.write(data, 1)
    full.unlink()                       # the big file is no longer needed
    print(f"Cached clip: {CLIP.name} ({CLIP.stat().st_size / 1e3:.0f} KB); big file deleted")

# ---------- 2. Read the cells that hold people ----------
with rasterio.open(CLIP) as src:
    arr = src.read(1).astype(float)
    nodata = src.nodata
    if nodata is not None:
        arr[arr == nodata] = 0
    arr[~np.isfinite(arr)] = 0
    arr[arr < 0] = 0
    rows, cols = np.nonzero(arr > 0)
    xs, ys = rasterio.transform.xy(src.transform, rows, cols)          # cell centres (lon, lat)
cells = gpd.GeoDataFrame({"pop": arr[rows, cols]}, geometry=gpd.points_from_xy(xs, ys), crs=4326).to_crs(UTM)
print(f"Population in the study box: {cells['pop'].sum():,.0f} people in {len(cells)} populated 100 m cells")

# Sanity: compare with the figures in the project brief (Summerland ~12,000, Peachland ~8,000)
for name, (lon, lat) in {"Summerland": (-119.677, 49.601), "Peachland": (-119.737, 49.773)}.items():
    c = gpd.GeoSeries(gpd.points_from_xy([lon], [lat]), crs=4326).to_crs(UTM).iloc[0]
    for r in (3000, 5000):
        print(f"  WorldPop within {r // 1000} km of {name} centre: {cells[cells.distance(c) < r]['pop'].sum():,.0f}")

# ---------- 3. Assign each populated cell to its nearest road node ----------
G = ox.load_graphml(config.RAW / "roads.graphml")
G = G.subgraph(max(nx.strongly_connected_components(G), key=len)).copy()   # same network as 03_analysis
nodes = ox.graph_to_gdfs(ox.project_graph(G, to_crs=UTM), edges=False)
snapped = gpd.sjoin_nearest(cells, nodes[["geometry"]].reset_index(), how="left", distance_col="snap_m")   # adds an "osmid" column
snapped = snapped[~snapped.index.duplicated()]                       # ties: keep one node per cell
too_far = snapped["snap_m"] > MAX_SNAP_M
print(f"Dropped {snapped.loc[too_far, 'pop'].sum():,.0f} people living > {MAX_SNAP_M} m from any road node "
      f"({too_far.sum()} cells)")
node_pop = snapped[~too_far].groupby("osmid")["pop"].sum()
node_pop.index.name = "node"
node_pop.to_csv(OUT)
print(f"Saved population for {len(node_pop)} road nodes ({node_pop.sum():,.0f} people) to {OUT.name}")
