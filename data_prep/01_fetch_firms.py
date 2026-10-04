"""Download NASA FIRMS fire detections, convert times to Pacific, merge, print a summary."""
import os
import sys
from io import StringIO

import pandas as pd
import requests
from dotenv import load_dotenv

import config

load_dotenv(config.ROOT / ".env")
MAP_KEY = os.getenv("MAP_KEY")
if not MAP_KEY:
    sys.exit("MAP_KEY missing. Copy .env.example to .env and put your FIRMS key in it.")

BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
AREA = f"{config.WEST},{config.SOUTH},{config.EAST},{config.NORTH}"


def fetch(source):
    """Return a DataFrame for one FIRMS source (cached as CSV), or None if no usable data."""
    cache = config.RAW / f"firms_{source}_{config.START_DATE}_{config.DAY_RANGE}d.csv"
    if cache.exists():
        print(f"  {source}: using cache")
        return pd.read_csv(cache)
    url = f"{BASE}/{MAP_KEY}/{source}/{AREA}/{config.DAY_RANGE}/{config.START_DATE}"
    r = requests.get(url, timeout=120)
    # FIRMS returns errors as plain text with status 200, so check the content too
    if r.status_code != 200 or not r.text.startswith("latitude"):
        print(f"  {source}: no data ({r.status_code}) {r.text[:120]!r}")
        return None
    cache.write_text(r.text)
    print(f"  {source}: downloaded")
    return pd.read_csv(StringIO(r.text))


frames = []
for label, sp, nrt in config.FIRMS_SOURCES:
    print(label)
    df = fetch(sp) if sp else None
    if df is None or df.empty:      # SP missing or empty: try NRT
        df = fetch(nrt)
    if df is not None and not df.empty:
        df["source"] = label
        frames.append(df)

if not frames:
    sys.exit("No detections downloaded.")

fires = pd.concat(frames, ignore_index=True)

# acq_date + acq_time are UTC; acq_time is HHMM without leading zeros
t = fires["acq_time"].astype(int).astype(str).str.zfill(4)
fires["time_utc"] = pd.to_datetime(fires["acq_date"].astype(str) + " " + t, format="%Y-%m-%d %H%M", utc=True)
fires["time_pacific"] = fires["time_utc"].dt.tz_convert(config.TIMEZONE)
fires["date_pacific"] = fires["time_pacific"].dt.date
fires = fires.sort_values("time_utc").reset_index(drop=True)

out = config.RAW / "fires_merged.csv"
fires.to_csv(out, index=False)
print(f"\nSaved {len(fires)} detections to {out}")

# ---- Sanity summary ----
print("\n=== SANITY SUMMARY ===")
print("Detections per source:\n", fires["source"].value_counts().to_string())
print("\nDetections per Pacific day:\n", fires["date_pacific"].value_counts().sort_index().to_string())
print("\nEarliest:", fires["time_pacific"].min(), "| Latest:", fires["time_pacific"].max())

# Unique pixel centres (a count only: summing pixel areas over several satellites and passes
# double-counts overlaps, so we do NOT report an area from detections)
uniq = fires.drop_duplicates(subset=["source", "latitude", "longitude"])
print(f"\nUnique pixel centres: VIIRS {uniq['source'].str.startswith('VIIRS').sum()}, "
      f"MODIS {(uniq['source'] == 'MODIS').sum()}")

# Where did it start? Compare the earliest detections with Summerland (approx lon -119.68, lat 49.60)
first = fires.head(5)[["time_pacific", "source", "latitude", "longitude"]]
print("\nFirst 5 detections:\n", first.to_string())
if first["longitude"].mean() > -119.68:
    print("\nWARNING: earliest detections are NOT west of Summerland. Check the data before trusting the story.")
else:
    print("\nOK: earliest detections are west of Summerland.")
