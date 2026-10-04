"""Compare FIRMS detections and our likely-affected roads with the official BCWS perimeter of fire K51490."""
import geopandas as gpd
import json
import pandas as pd

import config

UTM = "EPSG:32611"
per = gpd.read_file(config.RAW / "bcws_perimeters" / "prot_current_fire_polys.shp")
per = per[per["FIRE_NUM"] == "K51490"].to_crs(UTM)
poly = per.geometry.union_all()
print(f"Official perimeter: {per.iloc[0]['FIRE_SZ_HA']:.0f} ha, version date {per.iloc[0]['TRACK_DATE']:%Y-%m-%d}, "
      f"status {per.iloc[0]['FIRE_STAT']} (area from geometry: {poly.area / 1e4:.0f} ha)")

# ---- Detections vs perimeter ----
f = pd.read_csv(config.RAW / "fires_merged.csv")
pts = gpd.GeoDataFrame(f, geometry=gpd.points_from_xy(f.longitude, f.latitude), crs=4326).to_crs(UTM)
pts["dist_m"] = pts.geometry.distance(poly)            # 0 if inside the perimeter
pts["inside"] = pts["dist_m"] == 0
print(f"\nDetections inside perimeter: {pts.inside.sum()} of {len(pts)} ({pts.inside.mean():.0%})")
print(f"Within 375 m of it (one VIIRS pixel): {(pts.dist_m <= 375).mean():.0%}")
print(f"Within 1000 m: {(pts.dist_m <= 1000).mean():.0%}; furthest detection: {pts.dist_m.max():.0f} m outside")
print("\nInside share by source:\n", pts.groupby("source")["inside"].mean().round(2).to_string())
pts["date"] = pd.to_datetime(pts["time_pacific"], utc=True).dt.tz_convert(config.TIMEZONE).dt.date
print("\nInside share by Pacific day:\n", pts.groupby("date")["inside"].mean().round(2).to_string())

# How much of the perimeter do the detections cover? (each VIIRS/MODIS pixel drawn as a circle of ~190 m / 500 m radius)
covered = pts.assign(geometry=pts.buffer(pts["source"].map(lambda s: 500 if s == "MODIS" else 190))).union_all()
print(f"\nPerimeter area covered by detection pixels: {covered.intersection(poly).area / poly.area:.0%}")

# Second number: how much of the perimeter lies within 1 km of at least one detection?
near1km = pts.buffer(1000).union_all()
print(f"Perimeter area with a detection within 1 km: {near1km.intersection(poly).area / poly.area:.0%} "
      "(pixel-based coverage above is stricter; this one allows for pixel size and location error)")

# ---- Roads we mark as affected vs perimeter ----
roads = gpd.read_file(config.ROOT / "web" / "data" / "roads.geojson").to_crs(UTM)
affected = roads[roads["affected_step"].notna()]
d = affected.geometry.distance(poly)
print(f"\nRoad segments we mark as likely affected: {len(affected)}; inside perimeter: {(d == 0).sum()}; "
      f"within 500 m outside: {((d > 0) & (d <= 500)).sum()}")
print("Affected segments by road type, share inside the perimeter:")
print(affected.assign(inside=(d == 0), hw=affected["highway"].astype(str)).groupby("hw")["inside"].agg(["size", "mean"]).round(2).sort_values("size", ascending=False).head(6).to_string())
