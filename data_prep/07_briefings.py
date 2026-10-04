"""Generate plain-language briefings with Gemini from the numbers we computed (steps.json, areas.geojson, roads.geojson).

Run once, ahead of the demo. The page only reads the saved files in web/briefings/, so it needs no API key or internet.
The key lives in .env (GEMINI_API_KEY) and is only ever used here, never sent to the browser.

  python data_prep/07_briefings.py --dry-run          # show the facts and prompt, no API call
  python data_prep/07_briefings.py                    # ONE test briefing (first key step, English): 1 API call
  python data_prep/07_briefings.py --all              # all key steps x all languages (~12 calls; free tier is ~20/day/model)
  python data_prep/07_briefings.py --step 3 --language English [--area "near Prairie Valley Road"]
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone

from dotenv import load_dotenv
from pydantic import BaseModel, Field

import config

MODEL = "gemini-3.5-flash-lite"                  # small, cheap model; names checked against the Gemini API docs on 2026-10-04
LANGUAGES = ["English", "Punjabi", "Spanish"]    # English plus two others (confirmed by the team)
OUT = config.ROOT / "web" / "briefings"
DATA = config.ROOT / "web" / "data"


class Briefing(BaseModel):
    summary: str = Field(description="2-3 calm, plain sentences describing the situation using only the supplied numbers")
    steps: list[str] = Field(description="General preparedness steps people commonly take; no numbers, no orders")
    what_to_bring: list[str] = Field(description="Commonly suggested items to bring; no numbers")
    pets: list[str] = Field(description="Commonly suggested pet and animal considerations; no numbers")
    caveats: list[str] = Field(description="Limits of the estimates, and where to get official information")


SYSTEM = """You write short, calm, plain-language briefings about a wildfire near Summerland, British Columbia, Canada.
You are given a JSON object called FACTS. Rules:
1. Use ONLY the numbers that appear in FACTS. Copy each number exactly as given, including decimal points (keep a period, not a comma). Never round, add, subtract or invent figures, dates, places or road names.
2. Do not say "you must evacuate" and do not give official instructions or tell anyone whether to leave or stay. Describe the situation and offer general, commonly suggested preparedness ideas only.
3. State clearly that these are illustrative estimates from public data (satellite fire detections, OpenStreetMap roads and modelled population), not official guidance, and that drive times are estimated minimums with no congestion.
4. Tell readers to rely on the BC Wildfire Service, EmergencyInfoBC and local evacuation orders for real decisions. Write the names "BC Wildfire Service" and "EmergencyInfoBC" exactly like that, even in other languages.
5. Write calmly and plainly, at a reading level suitable for the general public. No jargon, no alarmist words.
6. Write all text values in the requested language, including weekday and month names in the date. For Punjabi use Gurmukhi script, not Latin letters. Keep JSON keys in English.
7. If FACTS says a number is unknown or zero, say so plainly rather than guessing.
"""


def clean_name(name):
    """OSM names sometimes arrive as "['Okanagan Highway']" strings."""
    name = re.sub(r"[\[\]']", "", str(name or "")).strip()
    return "" if name in ("", "None", "nan") else name


def build_facts(step_index, area_name=None):
    steps = json.load(open(DATA / "steps.json"))
    s = steps[step_index]
    t0 = datetime.fromisoformat(s["first_detection"])
    now = datetime.fromisoformat(s["time"])
    areas = [f["properties"] for f in json.load(open(DATA / "areas.geojson"))["features"]]
    cut = [a for a in areas if a["cut_step"] is not None and a["cut_step"] <= step_index]
    cut.sort(key=lambda a: -a["residents"])
    roads = [f["properties"] for f in json.load(open(DATA / "roads.geojson"))["features"]]
    names = {}
    for r in roads:
        if r["affected_step"] is not None and r["affected_step"] <= step_index and clean_name(r["name"]):
            names[clean_name(r["name"])] = names.get(clean_name(r["name"]), 0) + 1
    facts = {
        "place": "Summerland, British Columbia (Bald Range wildfire)",
        "time_of_this_snapshot_pacific": now.strftime("%A %B %d, %I:%M %p").replace(" 0", " "),
        "hours_since_first_satellite_detection": round((now - t0).total_seconds() / 3600, 1),
        "satellite_fire_detections_so_far": s["fires_so_far"],
        "road_segments_likely_affected": s["roads_affected"],
        "road_names_most_affected": [n for n, _ in sorted(names.items(), key=lambda kv: -kv[1])[:5]],
        "estimated_residents_cut_off_from_all_exits": s["residents_cut_off"],
        "estimated_minimum_drive_minutes_longest_sample": s["longest_drive_min"],
        "estimated_minimum_drive_minutes_average_sample": s["mean_drive_min"],
        "drive_time_note": "free-flow minimum, no congestion, from 74 sample points in Summerland",
        "areas_cut_off_so_far": [
            {"area": a["name"], "estimated_residents": a["residents"],
             "hours_after_first_detection_when_cut_off": round((datetime.fromisoformat(a["cut_time"]) - t0).total_seconds() / 3600, 1),
             "estimated_minimum_drive_minutes": round(a["baseline_drive_min"], 1)} for a in cut[:3]],
    }
    if area_name:   # restrict to one area
        match = [a for a in areas if a["name"] == area_name]
        if not match:
            sys.exit(f"No area called {area_name!r}. Names look like 'near Prairie Valley Road'.")
        a = match[0]
        facts["focus_area"] = {"area": a["name"], "estimated_residents": a["residents"],
                               "estimated_minimum_drive_minutes": round(a["baseline_drive_min"], 1),
                               "cut_off_yet": a["cut_step"] is not None and a["cut_step"] <= step_index}
    return facts


def numbers_in(text):
    """All numbers in a text, converting any script's digits (e.g. Gurmukhi) to 0-9."""
    text = "".join(str(unicodedata.digit(c)) if c.isdigit() else c for c in text)
    return {m.replace(",", "") for m in re.findall(r"\d[\d,]*\.?\d*", text)}


def problems(briefing, facts, language):
    """Return a list of reasons to reject a generated briefing."""
    text = " ".join([briefing.summary, *briefing.steps, *briefing.what_to_bring, *briefing.pets, *briefing.caveats])
    allowed = numbers_in(json.dumps(facts)) | {"1", "9", "911", "97"}
    allowed |= {str(round(float(n))) for n in allowed if re.fullmatch(r"\d+\.?\d*", n)}   # whole-number versions
    found = {n.rstrip(".") for n in numbers_in(text)}
    out = [f"number not in facts: {n}" for n in sorted(found - allowed)]
    if language == "Punjabi":                     # must be Gurmukhi script, not Latin-letter transliteration
        letters = [c for c in text if c.isalpha()]
        gurmukhi = sum(1 for c in letters if "਀" <= c <= "੿")
        if not letters or gurmukhi / len(letters) < 0.5:
            out.append("Punjabi is not written in Gurmukhi script")
    for name in ("BC Wildfire Service", "EmergencyInfoBC"):
        if name not in text:
            out.append(f"missing '{name}'")
    if language == "English" and re.search(r"you must (evacuate|leave)|you should evacuate", text, re.I):
        out.append("gives an instruction to evacuate")
    return out


def generate(client, types, facts, language):
    config_ = types.GenerateContentConfig(system_instruction=SYSTEM, temperature=0.2,
                                          response_mime_type="application/json", response_schema=Briefing)
    prompt = f"Language: {language}\nFACTS:\n{json.dumps(facts, indent=1)}"
    for attempt in (1, 2, 3):                     # each attempt is one API call, so keep this small
        try:
            resp = client.models.generate_content(model=MODEL, contents=prompt, config=config_)
        except Exception as err:                  # busy or quota error: say so and stop, do not hammer the API
            print(f"    API error: {str(err)[:200]}")
            return None
        briefing = Briefing.model_validate_json(resp.text)
        bad = problems(briefing, facts, language)
        if not bad:
            return briefing
        print(f"    attempt {attempt} rejected: {bad}")
    return None


def key_steps():
    """Pick the steps worth briefing on: first roads affected, first residents cut off, biggest jump, final level."""
    steps = json.load(open(DATA / "steps.json"))
    picks = [next(s["step"] for s in steps if s["roads_affected"] > 0),
             next(s["step"] for s in steps if s["residents_cut_off"] > 0)]
    jumps = [(steps[i]["residents_cut_off"] - steps[i - 1]["residents_cut_off"], i) for i in range(1, len(steps))]
    picks.append(max(jumps)[1])
    final = steps[-1]["residents_cut_off"]
    picks.append(next(s["step"] for s in steps if s["residents_cut_off"] == final))
    return sorted(set(picks))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, help="one step index")
    ap.add_argument("--language", help="one language")
    ap.add_argument("--area", help="focus on one area, e.g. 'near Prairie Valley Road'")
    ap.add_argument("--all", action="store_true", help="generate every key step in every language")
    ap.add_argument("--model", default=MODEL, help="Gemini model id (default: %(default)s)")
    ap.add_argument("--force", action="store_true", help="regenerate files that already exist")
    ap.add_argument("--dry-run", action="store_true", help="print the facts and prompt, no API call")
    args = ap.parse_args()
    MODEL = args.model                            # used by generate() and saved in each file
    # By default make ONE briefing, so a first test costs a single API call
    step_list = [args.step] if args.step is not None else (key_steps() if args.all else key_steps()[:1])
    languages = [args.language] if args.language else (LANGUAGES if args.all else LANGUAGES[:1])

    if args.dry_run:
        for i in step_list:
            print(f"--- step {i} ---\n{json.dumps(build_facts(i, args.area), indent=1)}")
        print("\nSystem prompt:\n" + SYSTEM)
        sys.exit()

    load_dotenv(config.ROOT / ".env")
    if not os.getenv("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY missing. Add it to .env (see .env.example).")
    from google import genai
    from google.genai import types
    client = genai.Client()                       # reads GEMINI_API_KEY from the environment

    OUT.mkdir(exist_ok=True)
    made = []
    for i in step_list:
        facts = build_facts(i, args.area)
        for lang in languages:
            name = f"step_{i}_{lang}.json" if not args.area else f"step_{i}_{lang}_{re.sub('[^a-z0-9]+', '-', args.area.lower())}.json"
            if (OUT / name).exists() and not args.force:
                print(f"step {i} / {lang}: already exists, skipping (use --force to redo)")
                made.append({"step": i, "language": lang, "file": name})
                continue
            print(f"step {i} / {lang} ...")
            b = generate(client, types, facts, lang)
            if b is None:
                print("    not saved. Stopping so we do not waste more API calls.")
                sys.exit(1)
            (OUT / name).write_text(json.dumps({"step": i, "time": json.load(open(DATA / "steps.json"))[i]["time"],
                                                "language": lang, "model": MODEL, "area": args.area, "facts": facts,
                                                "briefing": b.model_dump(),
                                                "generated_at": datetime.now(timezone.utc).isoformat()},
                                               indent=1, ensure_ascii=False), encoding="utf-8")
            made.append({"step": i, "language": lang, "file": name})
            print("    saved", name)
            time.sleep(8)                         # stay under the free-tier rate limit
    # the page reads this list; merge with any earlier runs so single-step reruns don't erase it
    index_file = OUT / "index.json"
    old = json.load(open(index_file)) if index_file.exists() else []
    merged = {(m["step"], m["language"], m["file"]): m for m in old + made}
    index = sorted(merged.values(), key=lambda m: (m["step"], m["language"]))
    index_file.write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(made)} briefings; index has {len(index)}.")
