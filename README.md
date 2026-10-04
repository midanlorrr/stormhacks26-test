# Summerland wildfire evacuation replay

A hackathon prototype that replays the Bald Range wildfire (BC Wildfire Service fire K51490, Aug 7–10, 2026) on a map. Real NASA FIRMS satellite fire detections are laid over the real OpenStreetMap road network. Roads near detections are marked as likely affected, and estimated drive times to exits are recomputed at each 3-hour step.

> **Disclaimer:** this is an illustrative planning tool built from public data. It is **not official guidance**. For real evacuation decisions follow the BC Wildfire Service, EmergencyInfoBC and your local evacuation orders.

## Setup

You need **Python 3.12 or newer** (the pinned packages do not install on 3.11). Tested on 3.12 and 3.14.

```
python -m venv .venv
.venv\Scripts\activate          # Windows (on Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
```

### FIRMS key (free)
1. Request a MAP_KEY at https://firms.modaps.eosdis.nasa.gov/api/map_key/
2. Copy `.env.example` to `.env` and put the key in `.env` (never in `.env.example`; `.env` is git-ignored).

## Run the scripts in order (from the project folder)

| Step | Command | What it does |
|---|---|---|
| 1 | `python data_prep/01_fetch_firms.py` | Downloads FIRMS detections, converts UTC to Pacific time, merges, prints a sanity summary. |
| 2 | `python data_prep/02_fetch_roads.py` | Downloads the drivable road network from OpenStreetMap. |
| 3 | `python data_prep/03_analysis.py` | Marks affected roads, computes drive times, writes the files in `web/data/`. |
| 4 | `python data_prep/04_check_perimeter.py` | Compares our data with the official BCWS perimeter (optional, see below). |

Downloads are cached in `data_raw/`, so reruns do not download again. The exported files in `web/data/` are committed, so you can view the map without running steps 1–3.

**Step 4 needs the official perimeter:** download "BC Wildfire Fire Perimeters - Current" (zipped shapefile) from https://catalogue.data.gov.bc.ca/dataset/bc-wildfire-fire-perimeters-current and unzip it into `data_raw/bcws_perimeters/`.

## View the map

```
cd web
python -m http.server 8000
```
Open http://localhost:8000. (Opening `index.html` directly will not work, because the page fetches its data files.) The page needs internet for the MapLibre library and the OpenStreetMap background tiles.

## Known limits
- FIRMS only sees fire when a satellite passes over, so the replay shows when detections appeared, not how the fire moved between passes. The data is near-real-time (NRT); standard-processing data was not yet available for these dates.
- "Likely affected" roads are those within 100 m of a detection. This is a simple rule, not an official closure list.
- Drive times are estimated minimum times (free-flow, no congestion). Only about 15% of OSM roads here have a real speed limit; the rest use default speeds by road type. The exits were chosen by the team.
- No detections were found near Peachland.

## Data sources
NASA FIRMS (VIIRS and MODIS active fire), OpenStreetMap (roads, via osmnx), BC Wildfire Service (perimeter, for checking only), DriveBC (one closure, compared by hand).
