# Evacusense design handoff (direction 4a, Graphite)

Read this file first, then `evacusense-theme.css` (header + section 3), then match the reference mock.

## Files
- `evacusense-theme.css`: all tokens, components, layouts. Link it; do not copy values into other CSS.
- `Evacusense Brand Directions.dc.html`: visual reference. Open the "4a Graphite" card. Mocks are 1280x800 screens shown at 53%.
- `evacusense-2a-icon.svg`, `evacusense-2a-wordmark.svg`, `evacusense-2a-lockup.svg`: the logo. Do not redraw, recolour or restyle.

## Rules
1. Change only markup classes and CSS. Do not change JS behavior, IDs, data attributes or event handlers.
2. Add `es-` classes to existing elements. Do not rename existing classes.
3. Orange (#ff6a2b) = fire detections, slider fill, focus ring, logo only. Never a button fill.
4. Red (#e5484d) = affected roads only. Pale blue (#9cc9f0) = exit route only.
5. One primary (off-white) button per view. Radius 2px everywhere. No shadows, no gradients, no emoji.
6. Every estimated number: `<span class="es-est">1,240</span><span class="es-est-tag">est.</span>`
7. Tone: calm, credible, serious. Small type, lots of space, no animation beyond the globe spin, the globe fly-to and the replay itself.
8. Fonts load from the `@import` in the CSS. If offline, the system stack in `--es-font` and `--es-mono` is acceptable.

## Screen 1: Landing
Two columns on a near-black page (`--es-bg`), 64px side padding, 40px top.
- Top-left: logo lockup (`es-brand`): icon 40px + "EVACUSENSE" (Sora 600, 20px, letter-spacing .14em).
- Left column, vertically centered, max 600px wide, in this order:
  1. Eyebrow (`es-eyebrow`): "Bald Range fire · Summerland, BC · August 2026"
  2. Title (`es-title`): "See how the Bald Range fire unfolded."
  3. Description (`es-lede`): "A replay of the August 2026 fire near Summerland, built from open NASA satellite data."
  4. Buttons (`es-actions`, 16px gap): primary "Start the replay", secondary "How it works"
- Right column: the spinning globe (`es-globe`), roughly 640px square, vertically centered. Globe base colour #0e1116, graticule lines `--es-line`. A fire marker with a soft orange halo sits on Summerland, BC, labelled "SUMMERLAND, BC" in mono muted text. The globe later flies down to Summerland.

## Screen 2: Replay
Full-viewport dark satellite map (`es-map`, MapLibre) with a floating panel (`es-panel es-sidebar`): 24px from left/top/bottom, 380px wide, 24px padding, 16px gap between blocks, translucent with blur. Block order, top to bottom:
1. Logo: icon 22px + "EVACUSENSE" (Sora 600, 12px, tracking .14em).
2. Time readout: label "Replay time" (`es-label`), then `es-readout` "18:40" with `es-readout-date` "Aug 14, 2026" on the same baseline.
3. Playback: play button (`es-play`, 38px square) + slider (`es-slider`, 2px track, orange fill, 14px square off-white thumb).
4. Three headline numbers (`es-stats`, 3 equal columns, each `es-stat` with a left hairline):
   - "Detections" 1,284 (observed, no estimate tag)
   - "Roads affected" 37 km, estimated
   - "Cut off" 1,240, estimated
   Captions use `es-label` at 10px; values use `es-number` (28px).
5. "Areas cut off" (`es-section`): heading row with count and collapse chevron (▴ open, ▾ closed), then rows (`es-row`): name left, estimated count right (Prairie Valley 480, Trout Creek 510, Garnet Valley 250). Collapsible.
6. "Briefing" (`es-section`): heading row with the language picker (`es-select`, "English ▾") at right; briefing text (`es-body`, 13px); audio row (`es-audio`): small play button, 3px progress line (off-white fill), time "0:25 / 1:10" in mono.
7. Disclaimer (`es-disclaimer`), pinned to the bottom of the panel, always visible, never collapsible: "Figures are estimates from satellite detections and road data. This is not an official evacuation order. Follow local authorities."

Map legend (`es-legend`), bottom-right, 24px inset: Fire detection (orange dot), Affected road (red line), Exit route (pale blue line).

Map styling uses the values in CSS section 6 (not CSS classes). Fire = glowing orange dots (core + soft halo). Roads = thin light lines. Affected roads red and thicker. Exit route pale blue and thickest.

All numbers, names and the briefing text above are placeholders from the mock. Keep whatever real data and copy the app already produces; apply only the styling and structure.

## Done when
- Run the app and compare each screen against the 4a mock at 1280x800. Spacing, type sizes, colours and block order should match.
- Narrow screens: landing stacks, panel docks to the bottom (rules already in the CSS).
- No existing behavior changed.
