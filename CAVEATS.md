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
- The sensitivity test shows the answers depend heavily on this. Fire marks only gives about 1,440 residents cut off and a 12-minute drive to Penticton. The official closure only gives about 390 cut off and 59 minutes. Both together seal in everyone, which cannot be what happened, since Summerland was evacuated.
- The only independent closure check we have is a DriveBC screenshot of a single forest-road closure (Princeton-Summerland Road), from an unknown date.

## Drive times
- They are **estimated minimum times**: free-flow speed, no congestion, no queues, no stops, no one driving slowly or blocked by smoke.
- Only about 15% of roads here have a real speed limit in OpenStreetMap. The rest use default speeds by road type, chosen by us.
- They come from **74 sample points** in Summerland, not every address. The longest (21.2 min) and average (14.1 min) never change during the replay, because everyone's nearest exit is Penticton.
- The **exits** (Highway 97 north of Peachland, the far-south end of Highway 97, and central Penticton) were chosen by the team. They are not official evacuation destinations, although the Aug 8 alert did name reception centres in Penticton and West Kelowna.

## Residents cut off
- Population comes from **WorldPop** (100 m grid, 2025 estimate, CC BY 4.0). WorldPop is modelled, not a census, and labels this release as alpha. Counts are approximate; we round to the nearest 10.
- Each grid cell's people are assigned to the nearest road node (cells over 1.5 km from any road are dropped, 47 people). A real address may be served by a different road.
- The page shows residents cut off as a **range**: about **820 to 1,440** by Aug 8 6 am (roads within 50 m or 100 m of a detection treated as impassable). The answer is very sensitive to that rule: 25 m gives about 280, 250 m about 3,000, 500 m about 4,560. Closing only the roads that touch the official fire perimeter (Aug 29 shape, end state only) gives about 470, and the official Highway 97 closure alone gives about 390. So 1,440 is probably the high side. Those two cross-checks are not time-resolved, so they appear only as a note on the page.
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
