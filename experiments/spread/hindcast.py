"""Phases 2-3: calibrate one knob on the first 6 hours, run 20 seeds, score against FIRMS, save a picture.

Run:  python experiments/spread/hindcast.py      (takes several minutes)
Pass line and parameters are in PASS_LINE.md (written before the first run).
"""
import json
import struct
import time
import zlib
import numpy as np
import pandas as pd
from pathlib import Path
from pyproj import Transformer

import model

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
N_RUNS = 20
SCALES = [0.25, 0.5, 1, 2, 4]              # the one calibration knob
CAL_STEP = pd.Timestamp("2026-08-07 21:00", tz="America/Vancouver")      # inside the first 6 hours of the fire
STEPS = list(pd.date_range("2026-08-07 18:00", "2026-08-10 18:00", freq="3h", tz="America/Vancouver"))

g, wind, wind_hours = model.load_inputs()
H, W = g["dem"].shape
CELL = float(g["cell"])
to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32611", always_xy=True)

# ---------- real fire: detections -> cells, with a buffer of half a satellite pixel ----------
det = pd.read_csv(ROOT / "data_raw" / "fires_merged.csv")
det["t"] = pd.to_datetime(det["time_pacific"], utc=True).dt.tz_convert("America/Vancouver")
det["x"], det["y"] = to_utm.transform(det["longitude"].to_numpy(), det["latitude"].to_numpy())
det = det.sort_values("t").reset_index(drop=True)
det["radius_m"] = np.where(det["instrument"] == "MODIS", 500.0, 187.5)       # half a MODIS / VIIRS pixel


def footprint_cells(row):
    r = int(np.ceil(row["radius_m"] / CELL))
    r0, c0 = model.to_cell(g, row["x"], row["y"])
    rows, cols = np.mgrid[-r:r + 1, -r:r + 1]
    keep = np.hypot(rows, cols) * CELL <= row["radius_m"] + CELL / 2
    rr, cc = rows[keep] + r0, cols[keep] + c0
    ok = (rr >= 0) & (rr < H) & (cc >= 0) & (cc < W)
    return rr[ok] * W + cc[ok]


det_cells = [footprint_cells(row) for _, row in det.iterrows()]


def observed(t):
    """Cumulative footprint of all detections up to time t (boolean H x W)."""
    mask = np.zeros(H * W, dtype=bool)
    for k in np.flatnonzero((det["t"] <= t).to_numpy()):
        mask[det_cells[k]] = True
    return mask.reshape(H, W)


# ---------- scoring helpers ----------
def scores(sim, obs):
    tp = (sim & obs).sum()
    p = tp / max(sim.sum(), 1)
    r = tp / max(obs.sum(), 1)
    return p, r, tp / max((sim | obs).sum(), 1)


def centroid_km(mask):
    rr, cc = np.nonzero(mask)
    if len(rr) == 0:
        return (np.nan, np.nan)
    return ((cc.mean() * CELL) / 1000, (rr.mean() * CELL) / 1000)          # km east, km south of the grid corner


def max_extent_km(mask):
    rr, cc = np.nonzero(mask)
    if len(rr) == 0:
        return 0.0
    return float(np.hypot(rr.max() - rr.min(), cc.max() - cc.min()) * CELL / 1000)


# ---------- model inputs ----------
static, wind_table, hours = model.build_rates(g, wind, wind_hours)
start = model.ignition_cells(g, det)
print(f"ignition cells: {len(start)}; wind hours: {len(hours)}")


def hours_after_start(t):
    return (t - model.T0).total_seconds() / 3600


# ---------- calibration: choose `scale` using ONLY the 21:00 step (first ~4 hours of the fire) ----------
t0 = time.time()
obs_cal = observed(CAL_STEP)
print(f"observed footprint at {CAL_STEP:%b %d %H:%M}: {obs_cal.sum()} cells")
cal = {}
for s in SCALES:
    burns = [model.run(static, wind_table, hours, start, seed=100 + k, scale=s) for k in range(5)]   # 5 seeds, different from the final 20
    prob = np.mean([b <= hours_after_start(CAL_STEP) for b in burns], axis=0)
    cal[s] = scores(prob >= 0.5, obs_cal)[2]
    print(f"  scale {s}: IoU at {CAL_STEP:%H:%M} = {cal[s]:.3f}  ({time.time() - t0:.0f}s)")
best = max(cal, key=cal.get)
print("chosen scale (frozen from here):", best)

# ---------- final runs ----------
burns = np.array([model.run(static, wind_table, hours, start, seed=k, scale=best) for k in range(N_RUNS)])
print(f"{N_RUNS} runs done ({time.time() - t0:.0f}s)")
mean_burn_time = np.nanmedian(np.where(np.isinf(burns), np.nan, burns), axis=0)        # median burn time over the runs that burned the cell

# ---------- Summerland west edge ----------
areas = json.load(open(ROOT / "web" / "data" / "areas.geojson"))["features"]
pts = np.array([f["geometry"]["coordinates"] for f in areas])
west = pts[(pts[:, 0] < -119.705) & (pts[:, 1] > 49.52) & (pts[:, 1] < 49.68)]       # the westmost populated 1 km areas
wx, wy = to_utm.transform(west[:, 0].mean(), west[:, 1].mean())
wr, wc = model.to_cell(g, wx, wy)
near = np.zeros((H, W), dtype=bool)
rr, cc = np.mgrid[0:H, 0:W]
near[np.hypot(rr - wr, cc - wc) * CELL <= 1000] = True            # within 1 km of the west edge
print(f"west edge of Summerland: lon {west[:, 0].mean():.3f}, lat {west[:, 1].mean():.3f} (cell {wr},{wc})")

# ---------- 3-hourly table ----------
rows = []
sim_masks, obs_masks = {}, {}
first_obs_west = first_sim_west = None
for t in STEPS:
    h = hours_after_start(t)
    prob = (burns <= h).mean(axis=0)
    sim = prob >= 0.5
    obs = observed(t)
    p, r, iou = scores(sim, obs)
    sim_masks[t], obs_masks[t] = sim, obs
    cs, co = centroid_km(sim), centroid_km(obs)
    rows.append({"step": t.strftime("%b %d %H:%M"), "sim_km2": sim.sum() / 100, "obs_km2": obs.sum() / 100,
                 "precision": p, "recall": r, "IoU": iou,
                 "centroid_gap_km": float(np.hypot(cs[0] - co[0], cs[1] - co[1])) if sim.any() and obs.any() else np.nan,
                 "sim_extent_km": max_extent_km(sim), "obs_extent_km": max_extent_km(obs)})
    if first_obs_west is None and (obs & near).any():
        first_obs_west = t
    if first_sim_west is None and (sim & near).any():
        first_sim_west = t
table = pd.DataFrame(rows)
pd.set_option("display.width", 200)
print(table.round(2).to_string(index=False))

# exact (not 3-hour) first-arrival times at the west edge
obs_cells_t = det["t"][[bool(np.isin(det_cells[k], np.flatnonzero(near.ravel())).any()) for k in range(len(det))]]
obs_first = obs_cells_t.min() if len(obs_cells_t) else None
near_burn = burns[:, near]
sim_first_h = np.nanpercentile(near_burn.min(axis=1)[np.isfinite(near_burn.min(axis=1))], 50) if np.isfinite(near_burn.min(axis=1)).any() else None
sim_first = model.T0 + pd.Timedelta(hours=float(sim_first_h)) if sim_first_h is not None else None
print("\nFIRMS first detection within 1 km of Summerland's west edge:", obs_first)
print("Simulation first reaches it (median over runs):", sim_first)
gap_h = (sim_first - obs_first).total_seconds() / 3600 if (sim_first is not None and obs_first is not None) else None
print("difference (sim - observed), hours:", None if gap_h is None else round(gap_h, 1))

final_iou = table["IoU"].iloc[-1]
pass1 = gap_h is not None and abs(gap_h) <= 3
pass2 = final_iou >= 0.4
print(f"\nPASS LINE  1 (west edge within 3 h): {'PASS' if pass1 else 'FAIL'}   2 (final IoU >= 0.4): {'PASS' if pass2 else 'FAIL'} (IoU {final_iou:.2f})")
print("OVERALL:", "PASS" if pass1 and pass2 else "FAIL")
table.to_csv(HERE / "cache" / "hindcast_table.csv", index=False)

# ---------- export in the same style as the FIRMS file: one point per burned cell with a timestamp ----------
final_h = hours_after_start(STEPS[-1])
burned = (burns <= final_h).mean(axis=0) >= 0.5
rr_, cc_ = np.nonzero(burned)
x = float(g["x_min"]) + (cc_ + 0.5) * CELL
y = float(g["y_max"]) - (rr_ + 0.5) * CELL
lon, lat = Transformer.from_crs("EPSG:32611", "EPSG:4326", always_xy=True).transform(x, y)
when = model.T0 + pd.to_timedelta(mean_burn_time[rr_, cc_], unit="h")
out = pd.DataFrame({"latitude": lat, "longitude": lon, "time_utc": when.tz_convert("UTC").strftime("%Y-%m-%d %H:%M"),
                    "time_pacific": when.strftime("%Y-%m-%d %H:%M"), "date_pacific": when.strftime("%Y-%m-%d"),
                    "source": "SIM", "instrument": "SIM", "burn_probability": (burns[:, rr_, cc_] <= final_h).mean(axis=0)})
out.to_csv(HERE / "sim_detections.csv", index=False)
print("wrote sim_detections.csv with", len(out), "points")


# ---------- picture: rows = 3 times, left = simulated, right = observed (FIRMS) ----------
def png(path, rgb):
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[i].tobytes() for i in range(h))
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def panel(mask, other=None):
    img = np.zeros((H, W, 3), dtype=np.uint8) + 25
    img[g["dem"] < 345] = (30, 50, 80)                                  # lake
    img[mask] = (255, 106, 43)                                          # orange = burned
    img[near] = np.where(mask[near, None], (255, 255, 255), (70, 70, 70))  # 1 km circle at Summerland's west edge
    return img


show = [pd.Timestamp("2026-08-08 00:00", tz="America/Vancouver"), pd.Timestamp("2026-08-08 12:00", tz="America/Vancouver"),
        pd.Timestamp("2026-08-10 18:00", tz="America/Vancouver")]
sep = np.full((H, 6, 3), 255, dtype=np.uint8)
strips = [np.hstack([panel(sim_masks[t]), sep, panel(obs_masks[t])]) for t in show]
gap = np.full((6, strips[0].shape[1], 3), 255, dtype=np.uint8)
image = np.vstack([s for pair in zip(strips, [gap] * 3) for s in pair][:-1])
png(HERE / "hindcast.png", image)
print("wrote hindcast.png: left = simulated, right = FIRMS; rows = ", [t.strftime("%b %d %H:%M") for t in show])
