"""Get points of interest (hospitals, fire stations, police, schools, community centres, big parks, beaches)
from OpenStreetMap for the study area, and export them as web/data/pois.geojson for the map.

The raw download is cached in data_raw/, so reruns do not hit the OSM servers again.
"""
import geopandas as gpd
import osmnx as ox

import config

RAW = config.RAW / "osm_pois_raw.geojson"
OUT = config.ROOT / "web" / "data" / "pois.geojson"
UTM = "EPSG:32611"
MIN_PARK_HA = 20          # only parks at least this big count as "major"
DUPLICATE_M = 300         # same kind + same name within this distance = one place (OSM often has a point and an outline)

TAGS = {
    "amenity": ["hospital", "fire_station", "police", "school", "community_centre"],
    "leisure": ["park"],
    "natural": ["beach"],
}

# ---------- 1. Download (cached) ----------
if RAW.exists():
    print("Using cached download:", RAW.name)
    feats = gpd.read_file(RAW)
else:
    print("Asking OpenStreetMap (Overpass) for places in the study area...")
    feats = ox.features_from_bbox((config.WEST, config.SOUTH, config.EAST, config.NORTH), TAGS).reset_index()
    keep = [c for c in ("name", "amenity", "leisure", "natural", "geometry") if c in feats.columns]
    feats = feats[keep]
    feats.to_file(RAW, driver="GeoJSON")
    print(f"Downloaded {len(feats)} features")

# ---------- 2. One tidy table: kind, name, point ----------
def kind_of(row):
    if row.get("amenity") in TAGS["amenity"]:
        return row["amenity"]
    if row.get("leisure") == "park":
        return "park"
    return "beach" if row.get("natural") == "beach" else None

feats["kind"] = feats.apply(kind_of, axis=1)
feats = feats[feats["kind"].notna()].to_crs(UTM)
feats["area_ha"] = feats.geometry.area / 10_000
feats["geometry"] = feats.geometry.representative_point()      # outlines become one point inside them
print("Raw features by kind:", feats["kind"].value_counts().to_dict())

# Parks: major ones only. Everything: must have a name (the map shows names).
feats = feats[(feats["kind"] != "park") | (feats["area_ha"] >= MIN_PARK_HA)]
unnamed = feats["name"].isna() | (feats["name"].astype(str).str.strip() == "")
print(f"Dropping {unnamed.sum()} features without a name")
feats = feats[~unnamed]

# Merge duplicates (same kind and name, close together)
feats["cell"] = list(zip(feats["kind"], feats["name"], (feats.geometry.x // DUPLICATE_M).astype(int), (feats.geometry.y // DUPLICATE_M).astype(int)))
feats = feats.drop_duplicates("cell")

out = feats[["kind", "name", "geometry"]].to_crs(4326)
out.to_file(OUT, driver="GeoJSON", COORDINATE_PRECISION=5)

print(f"\nExported {len(out)} places to {OUT.name} ({OUT.stat().st_size / 1e3:.0f} KB):")
print(out["kind"].value_counts().to_string())
