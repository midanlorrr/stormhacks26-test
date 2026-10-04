# Evacusense

A hackathon prototype for seeing what a wildfire does to roads and people. It replays real wildfires from open NASA satellite data (FIRMS) over the real OpenStreetMap road network, marks roads near detections as likely affected, and estimates how many residents were cut off from every exit and how long the drive to an exit takes, step by step (every 3 hours).

**First example:** the Bald Range wildfire (BC Wildfire Service fire K51490, Aug 7–10, 2026) near Summerland, BC. The example's name, place, dates and map area are described in one place (`EXAMPLE` near the top of `web/app.js`). Adding another nearby area still means running the data scripts for a new bounding box (`data_prep/config.py`) and giving the page an example picker; neither exists yet.

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
| 4 | `python data_prep/03_analysis.py` | Marks affected roads, estimates residents cut off and drive times, writes the files in `web/data/` (including `area_cut_shares.json` for the click-to-inspect card). |
| 5 | `python data_prep/04_check_perimeter.py` | Compares our data with the official BCWS perimeter (optional, see below). |
| 6 | `python data_prep/06_sensitivity_hwy97.py` | Optional test: reruns the end-of-replay numbers with the whole official Highway 97 closure treated as impassable. Does not change the main results. |
| 7 | `python data_prep/07_briefings.py` | Generates plain-language briefings with Gemini (needs `GEMINI_API_KEY` in `.env`; the page reads the saved files in `web/briefings/`). Use `--dry-run` first (no API call). A normal run makes ONE call; `--all` makes about 12, and the free tier allows about 20 per day per model. |
| 8 | `python data_prep/08_pois.py` | Gets named places (hospitals, fire stations, police, schools, community centres, parks over 20 ha, beaches) from OpenStreetMap for the map. Cached in `data_raw/`. |
| 9 | `python data_prep/09_burn_scar.py` | Downloads Sentinel-2 images (before: Aug 4, after: Aug 24, 2026) from the Microsoft Planetary Computer (free, no key), makes true-colour pictures and a burn-severity map (dNBR), and checks it against the official perimeter. Writes the small images and `burn_scar.json` into `web/data/`. Cached in `data_raw/`. |
| 10 | `python data_prep/10_route_replay.py` | Finds the fastest route to an exit from 10 preset starting points at every step, in two separate scenarios, and writes `web/data/route_replay.json` (about 80 KB). Needs the same cached downloads as step 4. |

Downloads are cached in `data_raw/`, so reruns do not download again. The exported files in `web/data/` are committed, so you can view the map without running steps 1–4.

**Step 5 needs the official perimeter:** download "BC Wildfire Fire Perimeters - Current" (zipped shapefile) from https://catalogue.data.gov.bc.ca/dataset/bc-wildfire-fire-perimeters-current and unzip it into `data_raw/bcws_perimeters/`.

## View the map

```
cd web
python -m http.server 8000
```
Open http://localhost:8000. (Opening `index.html` directly will not work, because the page fetches its data files.) The page needs internet for the MapLibre library and the OpenStreetMap background tiles.

## Design
The look follows the Evacusense design handoff (direction 4a "Graphite") kept in `design/` (read `design/DESIGN.md`). `web/evacusense-theme.css` is a copy of the handoff stylesheet with one change: the Google Fonts import is replaced by local font files, so the page works offline. `web/style.css` holds the app's own layout on top of it, and the map colours are set in `web/app.js`. Set `ROAD_STYLE` near the top of `app.js` to `"typed"` or `"original"` for the earlier road looks.

## Using the page
- **Start the replay** (or **Skip intro**) flies to Summerland and opens a short guided tour. The replay does not play until you press Play.
- The date, time, Play button and playhead sit in a bar along the bottom. Drag the playhead to move through time (this pauses playback). Click a line in **Key moments** to jump to that time.
- **Tour** (top of the side panel) shows the tour again; **Intro** goes back to the globe; **Hide** collapses the panel (the **Panel** button brings it back).
- The side panel is a set of tabs: **Summary** (the headline counts at the current moment), Moments, Briefing, Areas, Drive and About. The **Briefing** tab shows the AI-written briefing (pick the language at the top). On the bottom bar, bars above the line are key moments and diamonds are times with a briefing; hover for details, click to jump there.
- The **Routes** tab (route replay): pick a starting point and a scenario (fire detections only, or what if the official Highway 97 closure were impassable) to see the fastest route to an exit, and its estimated drive time, change as the slider moves. It is about routes a driver could take, not routes people took.
- **Click an empty spot on the map** (or click a road and press **Inspect this spot** in its popup) to inspect it: the first fire detection within 1 km, the nearest road's status, and the estimated residents and share cut off in that 1 km area, with a small timeline. The map outlines what is being used: a solid square for the 1 km area (residents) and a dashed circle for the 1 km fire-detection radius. Esc or the cross closes it. It is switched off in the Burn scar view.
- The **Burn scar** tab turns the map to look straight down and lays two Sentinel-2 images over it: drag the divider to compare before (Aug 4) and after (Aug 24). **Show burn severity** adds the dNBR colours and the official perimeter. Leaving the tab restores the replay view.
- During the replay the map is limited to about 100 km around Summerland (a flat map, not the globe).

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
- **Residents cut off, one range everywhere:** The default estimate is about 820 to 1,440 residents cut off (roads within 50 m to 100 m of a satellite detection are treated as closed). Two separate scenarios give different answers: treating only the official Highway 97 closure as closed gives about 390, and treating both together as closed seals in nearly everyone (about 13,000), which cannot be right because Summerland was evacuated toward Penticton. The sensitivity test (`06_sensitivity_hwy97.py`) found: fire marks only (what the map shows): about 1,440 cut off, Penticton 12 min; official closure only: about 390 cut off, Penticton 59 min; both together: every road out of the study area sealed. So the results depend heavily on what "closed" meant on the road, and we do not know that.
- **Not used as model input:** none of these facts drive the model. They are only for checking it.
- **Source:** the CBC article was published Aug 8 at 9:15 pm PT and describes events through 8 am that morning. Its order times are the news outlet's account, not an official notice; confirm against an RDOS or District of Summerland notice before relying on them.

## Prize tracks

| Track | How this project fits |
|---|---|
| ALEASAT | Reads open satellite archives (NASA FIRMS VIIRS/MODIS fire detections) and checks the result against the official BC Wildfire Service perimeter: 97% of detections fall inside it and 87% of its area is within 1 km of a detection. Aimed at disaster relief. |
| Gemini | Briefings are written by Gemini only from numbers our code computed. A code check (`07_briefings.py`) rejects any invented or rounded number, and the files are pre-generated so the demo needs no key. |
| Enactus UNSDG | Climate action and resilient communities: shows how a wildfire cuts off roads and neighbourhoods, in English, Punjabi and Spanish. |
| Beginner | Built by a team of beginners. Estimates are labelled "est.", and `CAVEATS.md` lists what is and is not validated. |
| IATSU Best Design | Dark "Graphite" design system, globe fly-in, guided tour, and a briefing pinned to the map. See `design/`. |
| SSSS Python | The whole data pipeline is Python (`data_prep/01` to `08`): pandas, geopandas, osmnx, networkx, rasterio and the Gemini SDK. The page itself is plain JavaScript. |

## Data sources
Copernicus Sentinel-2 L2A images (before and after the fire; modified Copernicus Sentinel data 2026, read from the Microsoft Planetary Computer), NASA FIRMS (VIIRS and MODIS active fire), WorldPop (population, CC BY 4.0: Bondarenko et al., WorldPop, University of Southampton, DOI 10.5258/SOTON/WP00839), OpenStreetMap (roads, via osmnx), Noto Sans map label fonts (SIL Open Font License; glyph files in `web/fonts/` from the MapLibre demo font server), Sora and JetBrains Mono interface fonts (SIL Open Font License; `web/fonts/ui/`), BC Wildfire Service (perimeter, for checking only), DriveBC (one closure, compared by hand).

## To do
- Confirm the evacuation-order time against an official notice (RDOS or the District of Summerland); today it is cited as reported by CBC.
- Have a native Punjabi and Spanish speaker review the briefings.
- The free Gemini tier allows about 20 calls per day per model; keep test runs to one call until things are confirmed.
- ElevenLabs spoken briefings: tabled for now.
- Highway 97: confirm when the official closure began and whether evacuees could use it (see `06_sensitivity_hwy97.py`).
- More examples: parameterize `data_prep/config.py` and the `web/data` paths per area, and add an example picker to the landing page.
- Layer 2 fire-spread hindcast: design only, see `docs/superpowers/specs/`.
