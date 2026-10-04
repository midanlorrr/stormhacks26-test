# Caveats and limits

Everything below applies to this project as of Oct 4, 2026. Read this before quoting any number from the tool.

## What this is
- An **illustrative planning tool** built from public data. It is **not official guidance** and was not made or reviewed by the BC Wildfire Service, EmergencyInfoBC or any evacuation authority. For real decisions follow them and local evacuation orders.
- It is a **replay of real satellite detections**, not a fire-spread simulation or forecast. The Layer 2 simulation is a design document only.
- Evacusense is meant to show different wildfires, but today it has **one example**: the Bald Range fire near Summerland, BC (Aug 2026). Every figure and caveat below is about that example.

## Fire data (NASA FIRMS)
- Satellites only see fire when they pass overhead, hours apart. The replay shows **when detections appeared**, not how the fire moved between passes. True road or area effects may have happened earlier than shown.
- All detections are **near-real-time (NRT)** data. The higher-quality standard-processing data was empty for these dates.
- A detection is a pixel (375 m for VIIRS, 1 km for MODIS) with location error, not a precise fire line.
- Start time: three sources give three times, and we cannot reconcile them. (1) BCWS records discovery at 4:29 pm Aug 7. (2) The first satellite detection in our FIRMS data is **4:48 pm**; this is the time the page and the briefings use, always worded as the "first satellite detection". (3) A Regional District spokesperson quoted by CBC said "first detected" at 5:30 pm; we do not use it.
- Fire size from detection pixels is only a rough footprint (about 32 km² at 8:30 pm Aug 7, about 133 km² at 8 am Aug 8, against news figures of 50 and 95 km²). The earlier area estimate in the data script was removed as unreliable.

## Roads and "likely affected"
- A road is marked **"likely affected" if it lies within 100 m of a detection**. This is a simple rule of ours, not an official closure list, and it is treated as fully impassable.
- Against the official perimeter, some marked roads lie outside it, and the tool does not mark roads that were closed for smoke or safety without a detection nearby.
- OpenStreetMap may be incomplete or out of date. Forest service roads are included in the network even though the Aug 8 alert said not to use them (except 201 FSR).

## Highway 97 and closures
- The official Highway 97 closure (Antlers Beach to the Pyramid Picnic Area in Kickininee Provincial Park, about 21 km) is **longer** than what the tool marks (about lat 49.62 to 49.69). The tool **under-marks** it.
- We do not know when the official closure began or whether evacuees were allowed to use it.
- **One range everywhere (page, README, this file):** The default estimate is about 820 to 1,440 residents cut off (roads within 50 m to 100 m of a satellite detection are treated as closed). Two separate scenarios give different answers: treating only the official Highway 97 closure as closed gives about 390, and treating both together as closed seals in nearly everyone (about 13,000), which cannot be right because Summerland was evacuated toward Penticton. In the test, fire marks only gives a 12-minute drive to Penticton and the official closure only gives 59 minutes.
- The only independent closure check we have is a DriveBC screenshot of a single forest-road closure (Princeton-Summerland Road), from an unknown date.

## Drive times
- They are **estimated minimum times**: free-flow speed, no congestion, no queues, no stops, no one driving slowly or blocked by smoke.
- Only about 15% of roads here have a real speed limit in OpenStreetMap. The rest use default speeds by road type, chosen by us.
- They come from **74 sample points** in Summerland, not every address. The longest (21.2 min) and average (14.1 min) never change during the replay, because everyone's nearest exit is Penticton.
- The **exits** (Highway 97 north of Peachland, the far-south end of Highway 97, and central Penticton) were chosen by the team. They are not official evacuation destinations, although the Aug 8 alert did name reception centres in Penticton and West Kelowna.

## Residents cut off
- Population comes from **WorldPop** (100 m grid, 2025 estimate, CC BY 4.0). WorldPop is modelled, not a census, and labels this release as alpha. Counts are approximate; we round to the nearest 10.
- Each grid cell's people are assigned to the nearest road node (cells over 1.5 km from any road are dropped, 47 people). A real address may be served by a different road.
- The page shows residents cut off as a **range**: about **820 to 1,440** by Aug 8 6 am (roads within 50 m or 100 m of a detection treated as impassable). The answer is very sensitive to that rule: 25 m gives about 280, 250 m about 3,000, 500 m about 4,560. Closing only the roads that touch the official fire perimeter (Aug 29 shape, end state only) gives about 470, and the official Highway 97 closure alone gives about 390. So 1,440 is probably the high side, and the 390 above is a different scenario, not the low end of this range. Those two cross-checks are not time-resolved, so they appear only as a note on the page.
- "Cut off" means no drivable route to any of our three exits. The evacuation orders covered the whole town (about 12,000 people), so "cut off" is **not** the number of people told to leave.
- The "areas cut off" list uses a majority rule: an area counts as cut off when at least half its estimated residents have lost every route. Only 4 of 280 populated 1 km areas meet it.

## Timing and the "race"
- The 9.4 to 10.5 hours between first detection and cut-off, against a 14 to 18 minute estimated drive, is what the satellite data supports. It does **not** show whether anyone was trapped.
- We have no warning times, no traffic, and no data on when residents actually left. The whole-town order came just after midnight on Aug 8 (per CBC), before most estimated cut-offs.
- The 25% "tight" flag threshold is our choice. No area was flagged. That does not mean the real margin was comfortable.

## Peachland
- **No detections** were found near Peachland, although the project brief says it was evacuated. The tool shows nothing happening there.

## How well it has been checked
- Fire data against the official perimeter: 97% of detections are inside it (BCWS Aug 29 version, 25,163 ha), 87% of its area has a detection within 1 km, and pixels directly cover 74%. The perimeter is a later, larger snapshot, so this is a generous check and says nothing about timing.
- Everything else (roads closed, drive times, residents cut off) is **not validated** against real closure or traffic records.
- Timeline facts come from the BCWS incident record, the BC Emergency Alert of Aug 8, and a CBC article published Aug 8 at 9:15 pm PT. The article describes events through 8 am that morning. The order times in it are the news outlet's account, not an official notice.

## Burn scar (Sentinel-2)
- The before/after images are Sentinel-2 L2A from Aug 4 (3 days before ignition) and Aug 24, 2026. The after image is 14 days after ignition, so it includes any burning after Aug 10 and not just Aug 7-10. A later, clearer image (Sep 18) is used only as a cross-check.
- "Burn severity" is dNBR = NBR before minus NBR after, with NBR = (NIR - SWIR2) / (NIR + SWIR2) from bands B08 and B12. The classes (0.10, 0.27, 0.44, 0.66) are the common USGS/FIREMON ones, which were developed for forests and Landsat. Treat the colours as relative severity, not measured damage.
- About **89.5%** of the official perimeter has dNBR above 0.10 (86.3% with the Sep 18 image). FIRMS has a detection within 1 km of **87%** of it. These are different tests of different things, so they are close but not directly comparable. The perimeter is a later (Aug 29) and larger snapshot than the fire at Aug 10.
- Cloud, cloud shadow, thin cirrus and water pixels are left out. Cloud is under 1% and shadow about 3% of the perimeter in the Aug 24 image; there is one small smoke plume in the lower left of that image, away from the main scar. Haze (aerosol) was low on both dates, but smoke is not removed.
- Farm fields, grass drying out, logging and new roads between the two dates can also change NBR. Outside the perimeter 1.5% of usable pixels still pass the threshold.
- Pixels are about 20 m on the ground. The images are drawn flat on the map, which is why the map cannot be tilted or rotated in this view.

## Click-to-inspect card
The card shows proximity and estimates for a clicked point. It never says a home or person was affected. It is switched off in the Burn scar view, outside the study box (it says "No data here") and when the click lands on a road (that opens the road popup instead).
- **What is outlined on the map:** the solid square is the exact 1 km cell of the UTM 11N grid that the residents, cut-off share and drive time are for (the grid is fixed, so the square does not centre on the click). The dashed circle is the 1 km radius used for fire detections. It is a flat circle of 1,000 m, so it looks like an oval when the map is tilted. The nearest-road search (500 m) is not drawn.
- **Fire detections within 1 km:** every FIRMS detection within 1 km of the point, from the same 6,014 detections as the map. "First in replay" is the earliest of them and its distance; "Now" counts those up to the slider time. Detections are satellite pixels (375 m for VIIRS, about 1 km for MODIS) with location error, so a distance of a few hundred metres is not precise.
- **Nearest road:** the closest mapped road segment. Beyond 500 m the card says there is no mapped road. "Likely affected" uses the same rule as the map: a detection within 100 m. It is an estimate, not a closure notice.
- **Estimated residents:** the WorldPop 2025 100 m grid (alpha release, modelled, not a census) added up over the 1 km square (UTM 11N grid) the point is in, rounded to 10. Squares with fewer than about 20 estimated residents have no entry, so the card says "fewer than about 20 estimated residents" and no cut-off share. These small squares hold 841 of 219,407 residents in the study box.
- **Cut off now / by end:** the share of that square's estimated residents whose road node has no drivable route to any exit once the roads marked affected are removed, at the slider time. It is shown as a range from the 50 m rule to the 100 m rule, rounded to the nearest 10% ("under 5%" below that), with a word: none, some (up to half), most (over half) or all (95% or more). The word is for the range, so it can read "some to most". "First route lost" is when the first road node holding at least about one estimated resident lost every route; the share can still be small then. Written by `03_analysis.py` into `web/data/area_cut_shares.json`; it reuses the node cut-off times behind the headline, and no existing export changed.
- **Reconciliation:** adding the per-square numbers gives 1,400 at the end (100 m rule) against the headline 1,440, and 783 against 820 (50 m rule). The gap is the residents in the small squares without an entry (43 at the end) plus rounding of the headline to 10. If you multiply the card's rounded percentages by its rounded residents you get about 1,334 and 793, so the rounded card numbers can differ from the headline by up to about 7%.
- **Drive time:** the pre-fire, free-flow minimum to the nearest exit, averaged over the people in the square. It is not the drive time during the fire, which was not computed per square, and it is not valid once roads close.
- **Only 8 of 280 squares have any cut-off share at the end,** and only 4 reach "most" or "all". Everywhere else the card shows 0% (none): that means no estimated resident lost every route under our rules, not that the area was safe.

## AI briefings (Gemini)
- Written by a small Gemini model (`gemini-3.5-flash-lite`) from our computed numbers. Code rejects invented or rounded numbers, missing "BC Wildfire Service" and "EmergencyInfoBC", and (in English) instructions to evacuate. That does not guarantee every sentence is accurate or appropriate.
- The "steps", "what to bring" and "pets" lists come from the model's general knowledge, not from official guidance.
- The briefings are told that the whole District of Summerland was ordered to evacuate just after midnight on Aug 8, **as reported by CBC**. That time is the news outlet's account, not an official notice, and "just after midnight" is not an exact time. Earlier orders, if any, are not known to the tool.
- Spanish and Punjabi text was **not reviewed by a native speaker**. The Punjabi reads stiffly.
- The model sometimes words things loosely (for example describing a per-area drive time as a "longest" figure). The number check cannot catch that.
- The free Gemini tier is limited to about 20 calls per day per model, so briefings were pre-generated and saved.

## Map and display
- The satellite basemap (EOX Sentinel-2 cloudless, 2025 version) shows land **before** the 2026 fire. It is dimmed on purpose. Its licence (CC BY-NC-SA 4.0) allows **non-commercial use only**, with attribution.
- The satellite tiles and the MapLibre library still need an internet connection. If the tiles fail, the page falls back to a plain OpenStreetMap map.

## Not tested
- The page has only been checked in an automated Chromium browser and by the project lead, not on phones, other browsers or screen readers.
- Audio briefings (ElevenLabs) were not built.
