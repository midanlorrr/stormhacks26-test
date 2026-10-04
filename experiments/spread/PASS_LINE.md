# Pass line and parameters (written BEFORE the first model run)

## Pass line (both must hold)
1. The simulated fire (burn probability >= 0.5 over 20 runs) reaches within 1 km of the west edge of Summerland
   within 3 hours of when FIRMS first shows a detection there.
2. IoU against the cumulative FIRMS footprint is 0.4 or better at the final step (Aug 10 18:00 Pacific).

Anything else is a fail. Precision, recall and IoU at every 3-hour step are reported either way.

## Fixed parameters (chosen from general reference ranges, NOT tuned on this fire)
| Parameter | Value | Why |
|---|---|---|
| Cell size | 100 m, 8 neighbours | matches the DEM / NDVI grid |
| Base spread rate | 8 cells/hour per neighbour = 800 m/h | typical grass-and-forest surface fire is ~0.5-1.5 km/h in moderate conditions |
| Fuel factor | 0 if NDVI < 0.1 (lake, bare, built); else 0.4 at NDVI 0.1 rising to 1.0 at NDVI >= 0.6 | NDVI only says "is there vegetation"; it cannot say how flammable it is |
| Slope factor | exp(3.5 x rise/run), kept between 0.25 and 6 | common Rothermel-style rule of thumb: rate roughly doubles on a 10 degree upslope |
| Wind factor | exp(0.2 x speed(m/s) x cos(angle to downwind)) | gives ~2.7x downwind and ~0.4x upwind at 5 m/s, a typical head-to-back spread ratio |
| Wind speed used | sustained 10 m speed (not gusts) | simplest choice; gusts are probably what drove the real fire (see report) |
| Diagonal moves | rate divided by 1.414 | longer distance |
| Ignition | cells within 300 m of the two first MODIS detections at 16:48 PDT Aug 7 | MODIS pixel is ~1 km so the true spot is uncertain |
| Randomness | each neighbour-to-neighbour ignition takes a random Exponential delay with the rate above; seeds 0..19 | fixed seeds, repeatable |

## One calibration knob
`scale` multiplies every rate. It is chosen from {0.25, 0.5, 1, 2, 4} to maximise IoU at the Aug 7 21:00 step
(the only 3-hour step inside the first 6 hours that has FIRMS detections), then **frozen** for everything after.
Any further tuning on this single fire would be overfitting.

## Deviation from the brief, and why
The brief asked for a cellular automaton with 15-30 minute steps. With 100 m cells and 15-minute steps a fire can move
at most one cell per step, i.e. 400 m/h, but FIRMS shows detections about 14 km apart only 3.3 hours after ignition.
So the model is the continuous-time version of the same idea (random waiting time to each neighbour, solved with a
priority queue); burn times are then read off at 15-minute / 3-hour steps.
