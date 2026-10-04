"""Phase 1: build the model's inputs on one 100 m grid (UTM 11N).

Makes, in experiments/spread/cache/:
  grid.npz    elevation, slope, aspect, ndvi (all on the same grid) + grid info
  wind.csv    hourly wind for Aug 7-10 2026 near Summerland
Needs internet. If a download fails the script stops; it never fills in made-up values.
"""
import numpy as np
import pandas as pd
import requests
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling, transform_bounds
from rasterio.windows import from_bounds, Window
from pathlib import Path
from pyproj import Transformer

CACHE = Path(__file__).parent / "cache"
CACHE.mkdir(exist_ok=True)
CELL = 100.0                       # metres
CRS = "EPSG:32611"                 # UTM zone 11N

# Study area (lon/lat) -> a grid snapped to 100 m
LON0, LON1, LAT0, LAT1 = -120.10, -119.50, 49.40, 49.80
to_utm = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
xs, ys = zip(*[to_utm.transform(lo, la) for lo in (LON0, LON1) for la in (LAT0, LAT1)])
x_min, x_max = np.floor(min(xs) / CELL) * CELL, np.ceil(max(xs) / CELL) * CELL
y_min, y_max = np.floor(min(ys) / CELL) * CELL, np.ceil(max(ys) / CELL) * CELL
W, H = int((x_max - x_min) / CELL), int((y_max - y_min) / CELL)
transform = from_origin(x_min, y_max, CELL, CELL)
print(f"grid: {W} x {H} cells = {W * H:,}")


def onto_grid(src, band=1, resampling=Resampling.average, scale=None):
    """Read one raster band (file or URL) and resample it onto our grid. Cells with no data stay NaN."""
    out = np.full((H, W), np.nan, dtype="float32")
    # read only the part of the raster that overlaps our grid (the Sentinel-2 tile is huge)
    box = transform_bounds(CRS, src.crs, x_min, y_min, x_max, y_max)
    window = from_bounds(*box, transform=src.transform).round_offsets().round_lengths()
    window = window.intersection(Window(0, 0, src.width, src.height))
    data = src.read(band, window=window).astype("float32")
    data[data == (src.nodata if src.nodata is not None else 0)] = np.nan
    if src.nodata is None:
        data[data == 0] = np.nan                      # Sentinel-2 uses 0 for "no data" outside the tile
    reproject(data, out, src_transform=src.window_transform(window), src_crs=src.crs, src_nodata=np.nan,
              dst_transform=transform, dst_crs=CRS, dst_nodata=np.nan, resampling=resampling)
    return out


# ---------- 1. Elevation: Copernicus DEM GLO-30 (free, AWS open data) ----------
dem = np.full((H, W), np.nan, dtype="float32")
for west in ("W121", "W120"):                      # the two 1-degree tiles that cover the area
    name = f"Copernicus_DSM_COG_10_N49_00_{west}_00_DEM"
    path = CACHE / f"{name}.tif"
    if not path.exists():
        url = f"https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif"
        print("downloading", url)
        r = requests.get(url, timeout=300)
        r.raise_for_status()
        path.write_bytes(r.content)
    with rasterio.open(path) as src:
        tile = onto_grid(src)
    dem = np.where(np.isnan(dem), tile, dem)
print(f"elevation: {np.nanmin(dem):.0f} to {np.nanmax(dem):.0f} m, empty cells: {np.isnan(dem).sum()}")

# slope (degrees) and aspect (compass direction the ground faces, 0 = north)
dz_dy, dz_dx = np.gradient(dem, CELL)              # rows go south, so dz_dy is "per cell going south"
slope = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))
aspect = (np.degrees(np.arctan2(-dz_dx, dz_dy)) + 360) % 360   # downhill direction measured clockwise from north

# ---------- 2. Fuel proxy: Sentinel-2 NDVI, the newest clear scenes before Aug 7 2026 ----------
# One orbit does not cover the whole area, so newest scenes come first and older ones only fill the gaps.
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
body = {"collections": ["sentinel-2-l2a"], "bbox": [LON0, LAT0, LON1, LAT1],
        "datetime": "2026-07-25T00:00:00Z/2026-08-06T23:59:59Z", "query": {"eo:cloud_cover": {"lt": 10}},
        "sortby": [{"field": "datetime", "direction": "desc"}], "limit": 40}
items = requests.post(STAC + "/search", json=body, timeout=60).json()["features"]
token = requests.get("https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-2-l2a", timeout=60).json()["token"]
ndvi = np.full((H, W), np.nan, dtype="float32")
date_used = np.full((H, W), "", dtype="U10")
for item in items:
    if np.isfinite(ndvi).all():
        break
    layers = []
    for band in ("B04", "B08"):
        with rasterio.open(item["assets"][band]["href"] + "?" + token) as src:
            layers.append((onto_grid(src) - 1000) / 10000)          # L2A offset used since 2022
    red, nir = layers
    new = (nir - red) / (nir + red)
    fill = np.isnan(ndvi) & np.isfinite(new)
    if fill.any():
        ndvi[fill] = new[fill]
        date_used[fill] = item["properties"]["datetime"][:10]
        print(item["properties"]["datetime"][:10], item["id"][-30:-16], "cloud", round(item["properties"]["eo:cloud_cover"], 1), "filled", int(fill.sum()))
dates, counts = np.unique(date_used[date_used != ""], return_counts=True)
print("NDVI date by cell:", dict(zip(dates, counts)), "| still empty:", int(np.isnan(ndvi).sum()))
print("ndvi 5/50/95 percentiles:", np.nanpercentile(ndvi, [5, 50, 95]).round(2))

np.savez_compressed(CACHE / "grid.npz", dem=dem, slope=slope, aspect=aspect, ndvi=ndvi,
                    x_min=x_min, y_max=y_max, cell=CELL)

# ---------- 3. Wind: Open-Meteo historical archive (ERA5-based), one point near the fire ----------
url = ("https://archive-api.open-meteo.com/v1/archive?latitude=49.62&longitude=-119.80"
       "&start_date=2026-08-07&end_date=2026-08-10&hourly=wind_speed_10m,wind_gusts_10m,wind_direction_10m"
       "&wind_speed_unit=ms&timezone=America%2FVancouver")
hourly = requests.get(url, timeout=60).json()["hourly"]
wind = pd.DataFrame(hourly).rename(columns={"time": "time_pacific", "wind_speed_10m": "speed_ms",
                                            "wind_gusts_10m": "gust_ms", "wind_direction_10m": "from_deg"})
wind.to_csv(CACHE / "wind.csv", index=False)
print("wind rows:", len(wind), "missing:", int(wind.isna().sum().sum()))
