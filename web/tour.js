// Guided tour: darkens the page and highlights one part of the screen at a time. Plain DOM, no libraries.
// startTour() opens it, endTour() closes it. The page's own buttons are blocked while it is open.

const TOUR_STEPS = [
  { target: "#tour-time", title: "Date and time",
    text: "The replay moves through the fire in 3-hour steps. The big date and time show the moment you are looking at. All counts are up to that moment." },
  { target: "#tour-controls", title: "Playback",
    text: "Press play to watch it unfold, or drag the playhead. Dragging pauses playback. The marks on the line are key moments, and the day names sit underneath." },
  { target: "#tour-stats", title: "What is counted",
    text: "Fire detections are hot spots seen by satellites. Roads affected are road segments within 100 m of a detection, treated as closed. Residents cut off is an estimated range (50 m to 100 m rule): people with no drivable route to any exit. \"est.\" means estimated." },
  { target: "#tour-data", title: "Data tabs", before: () => window.selectDataTab?.("moments"),
    text: "Use the tabs on the side. Moments: real events and the model's milestones (click one to jump there). Areas: 1 km squares that were cut off. Drive: estimated minimum drive to an exit. About: how the figures are made." },
  { target: "#legend", title: "Map key",
    text: "Orange dots are fire detections, red lines are affected roads, and the pale blue line is the longest estimated drive out. Zoom in for road names and places." },
  { target: "#callout", title: "Briefing",
    text: "A plain-language briefing written by an AI model from these figures only. Drag it by its title, close it with the cross, and switch language. It is not official guidance." },
  { target: "#play", title: "Your turn",
    text: "Press play when you are ready. You can reopen this tour any time from the Tour button." },
];

let tourEl = null;
let tourIndex = 0;

function startTour() {
  if (tourEl) return;
  tourEl = document.createElement("div");
  tourEl.id = "tour";
  tourEl.innerHTML =
    '<div class="tour-dim" data-side="top"></div><div class="tour-dim" data-side="bottom"></div>' +
    '<div class="tour-dim" data-side="left"></div><div class="tour-dim" data-side="right"></div>' +
    '<div class="tour-ring"></div>' +
    '<div class="tour-card es-panel" role="dialog" aria-label="Tour">' +
    '<div class="tour-count"></div><h3 class="tour-title"></h3><p class="tour-text"></p>' +
    '<div class="tour-actions"><button type="button" class="es-btn es-btn--secondary tour-skip">Skip tour</button>' +
    '<span><button type="button" class="es-btn es-btn--secondary tour-back">Back</button> ' +
    '<button type="button" class="es-btn tour-next">Next</button></span></div></div>';
  document.body.appendChild(tourEl);
  tourEl.querySelector(".tour-skip").addEventListener("click", endTour);
  tourEl.querySelector(".tour-back").addEventListener("click", () => showTourStep(tourIndex - 1));
  tourEl.querySelector(".tour-next").addEventListener("click", () => (tourIndex === TOUR_STEPS.length - 1 ? endTour() : showTourStep(tourIndex + 1)));
  window.addEventListener("resize", placeTour);
  document.addEventListener("keydown", tourKey);
  showTourStep(0);
}

function endTour() {
  if (!tourEl) return;
  tourEl.remove();
  tourEl = null;
  window.removeEventListener("resize", placeTour);
  document.removeEventListener("keydown", tourKey);
  document.getElementById("play").removeEventListener("click", endTour);
}

function tourKey(e) {
  if (e.key === "Escape") endTour();
  if (e.key === "ArrowRight" && tourIndex < TOUR_STEPS.length - 1) showTourStep(tourIndex + 1);
  if (e.key === "ArrowLeft" && tourIndex > 0) showTourStep(tourIndex - 1);
}

function showTourStep(i) {
  tourIndex = Math.max(0, Math.min(TOUR_STEPS.length - 1, i));
  const step = TOUR_STEPS[tourIndex];
  const last = tourIndex === TOUR_STEPS.length - 1;
  step.before?.();                                                                // e.g. open the right tab
  if (step.target === "#callout") window.openCallout?.();                          // make sure the briefing is on screen
  tourEl.querySelector(".tour-count").textContent = "Step " + (tourIndex + 1) + " of " + TOUR_STEPS.length;
  tourEl.querySelector(".tour-title").textContent = step.title;
  tourEl.querySelector(".tour-text").textContent = step.text;
  tourEl.querySelector(".tour-back").hidden = tourIndex === 0;
  tourEl.querySelector(".tour-next").textContent = last ? "Done" : "Next";
  // On the last step the highlighted Play button works, and pressing it ends the tour
  tourEl.querySelector(".tour-ring").style.pointerEvents = last ? "none" : "auto";
  document.getElementById("play").removeEventListener("click", endTour);
  if (last) document.getElementById("play").addEventListener("click", endTour);
  placeTour();
  tourEl.querySelector(".tour-next").focus();
}

// Put the four dark panels, the outline and the text card around the highlighted element
function placeTour() {
  if (!tourEl) return;
  const target = document.querySelector(TOUR_STEPS[tourIndex].target);
  if (!target) return;
  target.scrollIntoView({ block: "nearest" });
  const r = target.getBoundingClientRect();
  const pad = 8;
  const x1 = Math.max(0, r.left - pad), y1 = Math.max(0, r.top - pad);
  const x2 = Math.min(innerWidth, r.right + pad), y2 = Math.min(innerHeight, r.bottom + pad);
  const box = (el, left, top, width, height) => Object.assign(el.style, { left: left + "px", top: top + "px", width: width + "px", height: height + "px" });
  box(tourEl.querySelector('[data-side="top"]'), 0, 0, innerWidth, y1);
  box(tourEl.querySelector('[data-side="bottom"]'), 0, y2, innerWidth, innerHeight - y2);
  box(tourEl.querySelector('[data-side="left"]'), 0, y1, x1, y2 - y1);
  box(tourEl.querySelector('[data-side="right"]'), x2, y1, innerWidth - x2, y2 - y1);
  box(tourEl.querySelector(".tour-ring"), x1, y1, x2 - x1, y2 - y1);

  const card = tourEl.querySelector(".tour-card");
  const w = card.offsetWidth, h = card.offsetHeight, gap = 16;
  let left, top = Math.max(12, Math.min(y1, innerHeight - h - 12));
  if (x2 + gap + w <= innerWidth) left = x2 + gap;                         // prefer the right of the highlighted part
  else if (x1 - gap - w >= 0) left = x1 - gap - w;                        // else its left
  else {                                                                  // else below or above it
    left = Math.max(12, Math.min(x1, innerWidth - w - 12));
    top = y2 + gap + h <= innerHeight ? y2 + gap : Math.max(12, y1 - gap - h);
  }
  card.style.left = left + "px";
  card.style.top = top + "px";
}
