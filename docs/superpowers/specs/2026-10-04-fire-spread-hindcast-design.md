# Fire spread hindcast (Layer 2): design

Status: design only, approved in conversation section by section. No code written yet.

## Goal
Simulate how the Bald Range fire (K51490) could have spread from the first satellite detections on Aug 7, 2026 through Aug 10, and measure how well the simulation matches reality. This is a hindcast used for validation, not a forecast.

## Constraints
- About 4 hours of work, beginner-friendly code, short and commented.
- Free, open Earth observation data only. No API keys beyond the existing FIRMS key.
- Gemini and ElevenLabs are still out of scope.
- Layer 1 evacuation numbers (roads cut, origins cut off, drive times) stay driven by satellite detections only. The simulation does not feed them.

## Inputs
- **Grid:** 100 m cells in UTM 11N (EPSG:32611), covering the BCWS perimeter plus a margin, roughly lon -120.05 to -119.6, lat 49.45 to 49.8 (about 140,000 cells).
- **Elevation:** Copernicus 30 m DEM (free AWS open-data tiles) read with `rasterio`, resampled to 100 m, converted to slope and downhill direction. Fallback if tile access fails: SRTM. Access not yet confirmed.
- **Wind:** hourly speed and direction for Aug 7 to 10 from the Open-Meteo historical archive, at one point near the fire centre. Limitation: coarse reanalysis, no valley or lake-breeze effects.
- **Start state:** the earliest detections (Aug 7, about 4:48 pm Pacific, MODIS pixels roughly 17 km west of Summerland).
- **Vegetation:** uniform. ESA WorldCover is an optional add-on if time allows.
- **Reference data (already in the project):** FIRMS detections (`data_raw/fires_merged.csv`) and the BCWS perimeter (`data_raw/bcws_perimeters/`).

## Model
- 10-minute time step. Each cell is unburned or burned with an ignition time. Burned cells stay burned.
- Each step, every unburned cell next to a burned cell (8 neighbours) ignites with probability `p = base_rate * wind_factor * slope_factor`, capped at 1, scaled by distance for diagonals.
- `wind_factor` increases when the spread direction matches the wind direction and with wind speed. `slope_factor` increases uphill and decreases downhill. Both use fixed constants chosen from general reference values and are not tuned.
- Fixed random seed for repeatability. Run about 10 seeds and report the spread.

## Calibration
- Only `base_rate` is tuned, by a simple search, so the simulated burned area on Aug 10 matches the area covered by the detection pixels.
- The wind and slope constants stay fixed so that a good shape match is evidence the model adds information.

## Evaluation
- At the end of each Pacific day (Aug 7 to 10): intersection over union (IoU) between simulated burned cells and the cumulative detection footprint.
- On the last day: share of simulated area inside the BCWS perimeter.
- Baseline: a circle of equal area around the start point. The simulation must beat it. If it does not, report that.
- Known limit: detections cover about 74% of the perimeter area, so IoU against detections cannot reach 1. Scores are for comparison only.

## Scripts and outputs
- `data_prep/05_fetch_terrain_wind.py`: downloads and caches DEM and wind in `data_raw/`. Stops with a clear message if a download fails; no substitute values.
- `data_prep/06_simulate_fire.py`: runs, calibrates, scores, exports.
- `web/data/sim.geojson`: simulated burned outline per 3-hour step (matching Layer 1 steps).
- `web/data/sim_summary.json`: calibrated `base_rate`, area per day, IoU for the simulation and the baseline, seed spread.

## Front end
- Checkbox "Show simulated fire (hindcast)", off by default, drawing the outline for the current step.
- Side-panel block "Model vs satellite detections" with the day's IoU and the baseline.
- New dependency: `rasterio` (add to `requirements.txt`).

## Testing
- DEM check: Okanagan Lake near 340 m, surrounding hills above 1,000 m.
- Wind and slope off: result is roughly a circle. Strong wind: stretches downwind.
- Same seed gives the same result. Report spread across seeds.
- Final check is the IoU table against the circle baseline, reported as found.

## Risks
- Single-point reanalysis wind may miss the real drivers of this fire.
- Uniform vegetation ignores fuel differences (grass, forest, bare slopes, lake).
- Four days of detections is a small sample for judging a model.
- DEM tile access is unverified.

## Out of scope
Forecasting, what-if scenarios, using the simulation for evacuation numbers, spotting (embers), fire suppression.
