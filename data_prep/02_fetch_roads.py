"""Download the drivable OSM road network and save it as GraphML."""
import osmnx as ox

import config

out = config.RAW / "roads.graphml"
if out.exists():
    print(f"Cache exists: {out} (delete it to redownload)")
else:
    # osmnx 2.x takes bbox as (left, bottom, right, top)
    G = ox.graph_from_bbox((config.WEST, config.SOUTH, config.EAST, config.NORTH), network_type="drive")
    ox.save_graphml(G, out)
    print("Downloaded and saved", out)

G = ox.load_graphml(out)
print(f"Road graph: {len(G.nodes)} nodes, {len(G.edges)} edges")
