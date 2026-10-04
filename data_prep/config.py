"""Shared settings for the data_prep scripts."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data_raw"          # cached downloads (git-ignored)
RAW.mkdir(exist_ok=True)

# Bounding box around Summerland, Faulder and Peachland (lon/lat, WGS84)
WEST, SOUTH, EAST, NORTH = -120.3, 49.3, -119.4, 49.9

# Fire window (4 days starting on START_DATE)
START_DATE = "2026-08-07"
DAY_RANGE = 4

TIMEZONE = "America/Vancouver"

# FIRMS source names (checked against the FIRMS area API docs).
# Standard processing (SP) is preferred for old dates; NRT is the fallback.
# Each entry: (label, SP name or None, NRT name)
FIRMS_SOURCES = [
    ("VIIRS_SNPP",   "VIIRS_SNPP_SP",   "VIIRS_SNPP_NRT"),
    ("VIIRS_NOAA20", "VIIRS_NOAA20_SP", "VIIRS_NOAA20_NRT"),
    ("VIIRS_NOAA21", None,              "VIIRS_NOAA21_NRT"),  # no SP listed in docs
    ("MODIS",        "MODIS_SP",        "MODIS_NRT"),
]
