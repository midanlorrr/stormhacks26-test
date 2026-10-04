"""The fire-spread model (Phase 2). Parameters are listed in PASS_LINE.md and fixed before any run.

Idea: each burning cell lights each of its 8 neighbours after a random waiting time. The average waiting
time is shorter when the neighbour has fuel, is uphill, or is downwind. We find when every cell first burns
with a priority queue (like Dijkstra's shortest path, but with random times).
"""
import heapq
import numpy as np
import pandas as pd
from pathlib import Path

CACHE = Path(__file__).parent / "cache"
BASE_RATE = 8.0            # cells per hour per neighbour, before the factors below
SLOPE_K = 3.5              # slope factor = exp(SLOPE_K * rise/run)
WIND_K = 0.2               # wind factor = exp(WIND_K * speed * cos(angle to downwind))
IGNITION_RADIUS_M = 300
T0 = pd.Timestamp("2026-08-07 16:48", tz="America/Vancouver")      # first FIRMS detection
T_END_H = 73.2             # Aug 10 18:00 Pacific, in hours after T0

# the 8 neighbours: (row step, column step). Rows go south, so a negative row step is north.
STEPS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def load_inputs():
    g = np.load(CACHE / "grid.npz")
    wind = pd.read_csv(CACHE / "wind.csv")
    wind["time"] = pd.to_datetime(wind["time_pacific"]).dt.tz_localize("America/Vancouver")
    hours = ((wind["time"] - T0).dt.total_seconds() / 3600).to_numpy()          # hour offset of each wind row
    return g, wind, hours


def fuel_factor(ndvi):
    f = 0.4 + 0.6 * np.clip((ndvi - 0.1) / 0.5, 0, 1)
    return np.where(ndvi < 0.1, 0.0, f)


def build_rates(g, wind, hours):
    """Per-direction rate arrays. slope_rate[d] is (H, W): rate of spreading INTO cell (r, c) from its neighbour in direction d."""
    dem, ndvi = g["dem"], g["ndvi"]
    H, W = dem.shape
    fuel = fuel_factor(ndvi)
    cell = float(g["cell"])
    static = []                                    # fuel * slope * 1/distance, per direction, for the TARGET cell
    wind_table = []                                # wind factor per direction for every wind hour
    for dr, dc in STEPS:
        dist = cell * np.hypot(dr, dc)
        # elevation of the source cell, lined up with each target cell
        src = np.full((H, W), np.nan, dtype="float32")
        src[max(dr, 0):H + min(dr, 0), max(dc, 0):W + min(dc, 0)] = dem[max(-dr, 0):H + min(-dr, 0), max(-dc, 0):W + min(-dc, 0)]
        rise_run = (dem - src) / dist
        slope_f = np.clip(np.exp(SLOPE_K * np.nan_to_num(rise_run)), 0.25, 6.0)
        static.append(BASE_RATE * fuel * slope_f / np.hypot(dr, dc))
        # compass bearing of this move (north = row -1)
        bearing = np.degrees(np.arctan2(dc, -dr))
        downwind = (wind["from_deg"].to_numpy() + 180) % 360
        wind_table.append(np.exp(WIND_K * wind["speed_ms"].to_numpy() * np.cos(np.radians(bearing - downwind))))
    return np.array(static), np.array(wind_table), hours


def ignition_cells(g, detections):
    """Cells within IGNITION_RADIUS_M of the earliest detections (the two MODIS pixels at 16:48)."""
    first = detections[detections["t"] == detections["t"].min()]
    cells = set()
    r = int(IGNITION_RADIUS_M / g["cell"])
    for _, d in first.iterrows():
        row, col = to_cell(g, d["x"], d["y"])
        for dr in range(-r, r + 1):
            for dc in range(-r, r + 1):
                if np.hypot(dr, dc) * g["cell"] <= IGNITION_RADIUS_M:
                    cells.add((row + dr, col + dc))
    return sorted(cells)


def to_cell(g, x, y):
    return int((float(g["y_max"]) - y) // float(g["cell"])), int((x - float(g["x_min"])) // float(g["cell"]))


def run(static, wind_table, wind_hours, start_cells, seed, scale=1.0):
    """One stochastic run. Returns the burn time (hours after T0) for every cell; inf = never burned."""
    n_dir, H, W = static.shape
    rng = np.random.default_rng(seed)
    waits = rng.exponential(1.0, size=(n_dir, H, W)).astype("float32")           # a random wait for every possible move
    rate = (static * scale).reshape(n_dir, -1)
    waits = waits.reshape(n_dir, -1)
    burn = np.full(H * W, np.inf)
    heap = []
    for r, c in start_cells:
        burn[r * W + c] = 0.0
        heap.append((0.0, r * W + c))
    heapq.heapify(heap)
    wind_idx = np.clip(np.searchsorted(wind_hours, np.arange(0, T_END_H + 1), side="right") - 1, 0, len(wind_hours) - 1)
    while heap:
        t, i = heapq.heappop(heap)
        if t > burn[i] or t > T_END_H:
            continue
        r, c = divmod(i, W)
        wi = wind_idx[int(t)]
        for d, (dr, dc) in enumerate(STEPS):
            rr, cc = r + dr, c + dc
            if rr < 0 or rr >= H or cc < 0 or cc >= W:
                continue
            j = rr * W + cc
            rt = rate[d, j]
            if rt <= 0:
                continue
            arrive = t + waits[d, j] / (rt * wind_table[d, wi])
            if arrive < burn[j]:
                burn[j] = arrive
                heapq.heappush(heap, (arrive, j))
    return burn.reshape(H, W)
