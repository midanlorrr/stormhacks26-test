# Summerland wildfire evacuation replay

A hackathon prototype that replays the Bald Range wildfire (BC Wildfire Service fire K51490, Aug 7–10, 2026) on a map. Real NASA FIRMS satellite fire detections are laid over the real OpenStreetMap road network. Roads near detections are marked as likely affected, and estimated drive times to exits are recomputed at each 3-hour step.

> **Disclaimer:** this is an illustrative planning tool built from public data. It is **not official guidance**. For real evacuation decisions follow the BC Wildfire Service, EmergencyInfoBC and your local evacuation orders.

**Read [CAVEATS.md](CAVEATS.md) before quoting any number from this project.**

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
| 3 | `python data_prep/05_population.py` | Gets WorldPop gridded population (downloads a ~200 MB Canada file once, keeps a small clip, deletes the big file) and assigns people to road nodes. |
| 4 | `python data_prep/03_analysis.py` | Marks affected roads, estimates residents cut off and drive times, writes the files in `web/data/`. |
| 5 | `python data_prep/04_check_perimeter.py` | Compares our data with the official BCWS perimeter (optional, see below). |
| 6 | `python data_prep/06_sensitivity_hwy97.py` | Optional test: reruns the end-of-replay numbers with the whole official Highway 97 closure treated as impassable. Does not change the main results. |
| 7 | `python data_prep/07_briefings.py` | Generates plain-language briefings with Gemini (needs `GEMINI_API_KEY` in `.env`; the page reads the saved files in `web/briefings/`). Use `--dry-run` first (no API call). A normal run makes ONE call; `--all` makes about 12, and the free tier allows about 20 per day per model. |

Downloads are cached in `data_raw/`, so reruns do not download again. The exported files in `web/data/` are committed, so you can view the map without running steps 1–4.

**Step 5 needs the official perimeter:** download "BC Wildfire Fire Perimeters - Current" (zipped shapefile) from https://catalogue.data.gov.bc.ca/dataset/bc-wildfire-fire-perimeters-current and unzip it into `data_raw/bcws_perimeters/`.

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
- Resident counts come from WorldPop 100 m gridded population (2025 estimate, WorldPop marks it alpha). It is modelled, not a census, so treat numbers as rough.
- No detections were found near Peachland.

## Validation notes (public sources, checked by hand)

All times are Pacific (PDT). "Tool" rows come from this project; the rest are from the sources listed below.

| When | What | Source |
|---|---|---|
| Aug 7, 4:29 pm | Fire discovered at lat 49.626, lon -119.884 (about 15 km west of Summerland) | BCWS incident record, K51490 |
| Aug 7, 4:48 pm | First satellite detection (two MODIS pixels, about 3 km from that point) | FIRMS (this project) |
| Aug 7, 5:30 pm | "First detected" per a Regional District of Okanagan-Similkameen spokesperson | CBC article |
| Aug 7, about 8:30 pm | Fire quoted at 50 km² (FIRMS pixel footprint at that time: about 32 km², rough) | CBC article; this project |
| Aug 8, just after midnight | Entire District of Summerland ordered to evacuate; about an hour later, orders for properties near Peachland | CBC article |
| Aug 8, 2:13 am | First Highway 97 segments north of Summerland marked "likely affected" | Tool |
| Aug 8, 8:00 am | Fire quoted at over 95 km² (FIRMS pixel footprint: about 133 km², rough) | CBC article; this project |
| Aug 8, 12:45 pm | BC Emergency Alert, "evacuate immediately" for Summerland, Faulder, Garnet Valley Rd and others; reception centres in Penticton and West Kelowna; Highway 97 closed from Antlers Beach to Pyramid Picnic Area | BC Emergency Alert |
| Aug 29 | Final mapped size 25,163 ha (about 252 km²) | BCWS perimeter file |

What this does and does not show:
- **Start time:** BCWS records discovery at 4:29 pm and FIRMS first sees fire at 4:48 pm. The "5:30 pm" figure is a spokesperson's statement in the news. These disagree and we cannot resolve it; cite the source with any time you quote.
- **Highway 97:** the alert and the news both confirm Highway 97 near Summerland was closed. The alert's closure runs from Antlers Beach Regional Park (about lat 49.739) and the news places its south end at the Pyramid Picnic Area in Kickininee Provincial Park (about lat 49.546, just south of Summerland). That is about 21 km of highway; the tool marks only about lat 49.62 to 49.69, so it **under-marks** the official closure. We do not know when the closure began, or whether evacuees were allowed to use it.
- **Timing:** the whole-town order came just after midnight, before the tool's first Highway 97 effect (2:13 am) and before most of its estimated residents cut off. The 12:45 pm alert is therefore not the first alert. The tool's "cut off" counts residents with no drivable route out; the orders covered everyone, so the two numbers measure different things.
- **Sizes:** FIRMS pixel footprints are the same order of magnitude as the quoted sizes but not close enough to claim agreement; the footprint method is rough.
- **Sensitivity test (`06_sensitivity_hwy97.py`):** treating the whole official Highway 97 closure as impassable gives very different answers. Fire marks only (what the map shows): about 1,440 residents cut off, Penticton 12 min. Official closure only: about 390 cut off, but Penticton 59 min. Both together: every road out of the study area is sealed (all 74 sample points, about 13,000 residents), which cannot be what happened, since Summerland was evacuated toward Penticton. So the closure must have allowed evacuation traffic, and the results depend heavily on what "closed" meant on the road. We do not know that.
- **Not used as model input:** none of these facts drive the model. They are only for checking it.
- **Source label:** the CBC text we saved is labelled "Aug 7 9:15pm" but describes events through 8 am Saturday, so the label is probably wrong; check the original page before citing it.

## Data sources
NASA FIRMS (VIIRS and MODIS active fire), WorldPop (population, CC BY 4.0: Bondarenko et al., WorldPop, University of Southampton, DOI 10.5258/SOTON/WP00839), OpenStreetMap (roads, via osmnx), Noto Sans map label fonts (SIL Open Font License; glyph files in `web/fonts/` from the MapLibre demo font server), BC Wildfire Service (perimeter, for checking only), DriveBC (one closure, compared by hand).

## To do
- Briefings: add the official evacuation-order timing (whole District of Summerland ordered out just after midnight on Aug 8, per CBC) as a fact, without turning it into an instruction, then regenerate. Today the briefings do not know about the order, so wording like "prepare belongings in advance" can read oddly after midnight.
- Briefings: regenerate Punjabi for steps 2 and 4 (the first attempts came back in Latin letters and were removed), and have a native Punjabi and Spanish speaker review the text.
- Briefings: the free Gemini tier allows about 20 calls per day per model; keep test runs to one call until things are confirmed.
- ElevenLabs spoken briefings: tabled for now.
- Highway 97: confirm when the official closure began and whether evacuees could use it (see `06_sensitivity_hwy97.py`).
- Layer 2 fire-spread hindcast: design only, see `docs/superpowers/specs/`.
