"""Step 9: burn scar from Sentinel-2 (before vs after) for the Bald Range fire.

Reads free Sentinel-2 L2A images from the Microsoft Planetary Computer (no account or key needed), makes
  - a true-colour picture BEFORE the fire and one AFTER,
  - dNBR (burn severity) = NBR before minus NBR after, where NBR = (NIR - SWIR2) / (NIR + SWIR2),
  - the share of the official BCWS perimeter where dNBR says "burned".
Writes small web-ready images and burn_scar.json into web/data/. Does not touch any other output.
Downloads are cached in data_raw/ so a second run is quick.
"""
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import requests
from PIL import Image
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import Window, from_bounds

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data_raw"
OUT = ROOT / "web" / "data"

BEFORE_DAY = "2026-08-04"       # 3 days before the fire; 0% cloud over the perimeter
AFTER_DAY = "2026-08-24"        # 14 days after ignition; under 1% cloud over the perimeter
CHECK_DAY = "2026-09-18"        # an even clearer but later scene, used only as a cross-check of the numbers
BURNED = 0.10                   # dNBR above this = burned (see the note in the printout)
MODERATE = 0.27                 # dNBR above this = at least moderate-low severity
RES = 30.0                      # metres per pixel on the web-mercator grid (about 20 m on the ground at this latitude)

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
CLOUD_CLASSES = [3, 8, 9, 10]   # Sentinel-2 scene classification: 3 shadow, 8/9 cloud, 10 thin cirrus
WATER = 6

# ---------- the official perimeter and our pixel grid (EPSG:3857, so it lines up with the web map) ----------
fire = gpd.read_file(RAW / "bcws_perimeters" / "prot_current_fire_polys.shp")
fire = fire[fire["FIRE_NUM"] == "K51490"].to_crs(3857)
minx, miny, maxx, maxy = fire.total_bounds
margin = 1500
x0 = np.floor((minx - margin) / RES) * RES
y1 = np.ceil((maxy + margin) / RES) * RES
W = int((np.ceil((maxx + margin) / RES) * RES - x0) / RES)
H = int((y1 - np.floor((miny - margin) / RES) * RES) / RES)
transform = from_origin(x0, y1, RES, RES)
inside = rasterize(fire.geometry, out_shape=(H, W), transform=transform, fill=0, default_value=1).astype(bool)
perimeter_km2 = float(fire["FIRE_SZ_HA"].iloc[0]) / 100       # web-mercator pixels are stretched at this latitude, so use the official size
print(f"grid {W} x {H} pixels, official perimeter = {perimeter_km2:.0f} km2")
bbox_lonlat = list(gpd.GeoSeries(fire.geometry).to_crs(4326).total_bounds)

token = requests.get("https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-2-l2a", timeout=60).json()["token"]


def onto_grid(href, categorical=False):
    """Read the part of one Sentinel-2 file that overlaps our grid and resample it onto the grid (NaN = no data)."""
    out = np.full((H, W), np.nan, dtype="float32")
    with rasterio.open(href + "?" + token) as src:
        box = transform_bounds("EPSG:3857", src.crs, x0, y1 - H * RES, x0 + W * RES, y1)
        win = from_bounds(*box, transform=src.transform).round_offsets().round_lengths()
        win = win.intersection(Window(0, 0, src.width, src.height))
        data = src.read(1, window=win).astype("float32")
        data[data == 0] = np.nan                                  # 0 means "no data" outside the tile
        reproject(data, out, src_transform=src.window_transform(win), src_crs=src.crs, src_nodata=np.nan,
                  dst_transform=transform, dst_crs="EPSG:3857", dst_nodata=np.nan,
                  resampling=Resampling.nearest if categorical else Resampling.average)
    return out


def load_day(day):
    """All bands we need for one date, merged from the tiles that cover the fire. Cached in data_raw/."""
    cache = RAW / f"s2_{day}.npz"
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        return {k: z[k] for k in z.files}
    body = {"collections": ["sentinel-2-l2a"], "bbox": bbox_lonlat, "datetime": f"{day}T00:00:00Z/{day}T23:59:59Z", "limit": 20}
    items = requests.post(STAC + "/search", json=body, timeout=60).json()["features"]
    print(f"{day}: {len(items)} tiles, cloud cover per tile {[round(i['properties']['eo:cloud_cover'], 1) for i in items]}")
    bands = {name: np.full((H, W), np.nan, dtype="float32") for name in ("B02", "B03", "B04", "B08", "B12", "SCL")}
    for item in items:
        for name, layer in bands.items():
            new = onto_grid(item["assets"][name]["href"], categorical=(name == "SCL"))
            layer[:] = np.where(np.isnan(layer), new, layer)
    bands["scenes"] = np.array([i["id"] for i in items])
    np.savez_compressed(cache, **bands)
    return bands


def reflectance(dn):
    return np.clip((dn - 1000) / 10000, 0, 1.5)                   # Level-2A numbers carry a +1000 offset since 2022


def nbr(b):
    nir, swir2 = reflectance(b["B08"]), reflectance(b["B12"])
    return (nir - swir2) / (nir + swir2)


def bad_pixels(b):
    """Cloud, shadow, cirrus, water or missing: not usable for burn severity."""
    scl = b["SCL"]
    return np.isnan(scl) | np.isin(scl, CLOUD_CLASSES + [WATER])


def true_colour(b):
    rgb = np.stack([reflectance(b["B04"]), reflectance(b["B03"]), reflectance(b["B02"])], axis=-1)
    rgb = np.clip(rgb / 0.28, 0, 1) ** (1 / 1.6)                  # simple brightness stretch
    return (np.nan_to_num(rgb) * 255).astype(np.uint8)


before, after, check = load_day(BEFORE_DAY), load_day(AFTER_DAY), load_day(CHECK_DAY)


def dnbr_for(a, b):
    d = nbr(a) - nbr(b)
    d[bad_pixels(a) | bad_pixels(b)] = np.nan
    return d


def report(d, label):
    ok = inside & np.isfinite(d)
    n_in, n_ok = inside.sum(), ok.sum()
    burned = (d[ok] > BURNED).mean() * 100
    moderate = (d[ok] > MODERATE).mean() * 100
    # the other direction: of everything marked burned near the fire, how much lies inside the official perimeter?
    all_burned = np.isfinite(d) & (d > BURNED)
    precision = (all_burned & inside).sum() / max(all_burned.sum(), 1) * 100
    print(f"{label}: usable pixels in perimeter {100 * n_ok / n_in:.0f}% | dNBR > {BURNED}: {burned:.1f}% of usable | "
          f"dNBR > {MODERATE}: {moderate:.1f}% | burned pixels in the map that lie inside the perimeter: {precision:.0f}%")
    return {"usable_share": round(n_ok / n_in * 100, 1), "burned_share": round(burned, 1),
            "moderate_or_higher_share": round(moderate, 1), "burned_inside_perimeter_share": round(precision, 1)}


dnbr = dnbr_for(before, after)
print("--- dNBR (before minus after) ---")
main_stats = report(dnbr, f"{BEFORE_DAY} -> {AFTER_DAY}")
check_stats = report(dnbr_for(before, check), f"{BEFORE_DAY} -> {CHECK_DAY} (cross-check)")
bg = dnbr[np.isfinite(dnbr) & ~inside]
print(f"outside the perimeter (same map): {100 * (bg > BURNED).mean():.1f}% of usable pixels exceed {BURNED}")
print("median dNBR inside perimeter %.2f, outside %.2f" % (np.nanmedian(dnbr[inside]), np.nanmedian(dnbr[~inside])))

# ---------- web images ----------
OUT.mkdir(parents=True, exist_ok=True)
Image.fromarray(true_colour(before)).save(OUT / "burn_before.jpg", quality=82, optimize=True)
Image.fromarray(true_colour(after)).save(OUT / "burn_after.jpg", quality=82, optimize=True)

# dNBR as a colour layer: clear below the burned threshold, then four steps of increasing severity
ramp = [(BURNED, (106, 75, 214), "Low"), (MODERATE, (193, 63, 176), "Moderate-low"), (0.44, (255, 111, 161), "Moderate-high"), (0.66, (255, 242, 168), "High")]
rgba = np.zeros((H, W, 4), dtype=np.uint8)
for threshold, colour, _ in ramp:
    rgba[np.nan_to_num(dnbr, nan=-9) > threshold] = (*colour, 255)
Image.fromarray(rgba).save(OUT / "burn_dnbr.png", optimize=True)

# the official perimeter outline, simplified (about 30 m) so the page can draw it on top of the images
perimeter = gpd.GeoSeries(fire.geometry).to_crs(4326).simplify(0.0003)
json.dump(json.loads(perimeter.to_json()), open(OUT / "burn_perimeter.geojson", "w"))

# corners of the images in longitude/latitude (west, south, east, north)
to_lonlat = Transformer.from_crs(3857, 4326, always_xy=True)
w_, n_ = to_lonlat.transform(x0, y1)
e_, s_ = to_lonlat.transform(x0 + W * RES, y1 - H * RES)
info = {
    "bounds": [w_, s_, e_, n_],
    "before": {"date": BEFORE_DAY, "scenes": before["scenes"].tolist()},
    "after": {"date": AFTER_DAY, "scenes": after["scenes"].tolist()},
    "burned_threshold": BURNED, "moderate_threshold": MODERATE,
    "perimeter_km2": round(perimeter_km2, 1),
    "perimeter_source": "BCWS fire K51490, track date 2026-08-29",
    "ramp": [{"from": t, "color": "#%02x%02x%02x" % c, "label": name} for t, c, name in ramp],
    "firms_within_1km_share": 87,          # from 04_check_perimeter.py: share of the perimeter area with a FIRMS detection within 1 km
    "result": main_stats, "cross_check_scene": CHECK_DAY, "cross_check": check_stats,
}
json.dump(info, open(OUT / "burn_scar.json", "w"), indent=1)
for name in ("burn_before.jpg", "burn_after.jpg", "burn_dnbr.png", "burn_perimeter.geojson", "burn_scar.json"):
    print(f"{name}: {(OUT / name).stat().st_size / 1024:.0f} KB")
print("bounds (west, south, east, north):", [round(v, 4) for v in info["bounds"]])
