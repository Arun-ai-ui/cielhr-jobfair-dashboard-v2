import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests


# ---------------------------------------------------------
# CIEL HR Job Fair Dashboard V2
# Tavily research → events.json
# ---------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
EVENTS_FILE = ROOT / "events.json"

TAVILY_API_URL = "https://api.tavily.com/search"
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()

TODAY = date.today().isoformat()


ALLOWED_CATEGORIES = [
    "NSDC & MSDE Flagship Rozgar Melas",
    "District Employment Exchange Fairs",
    "Skill Sector Councils (SSCs) Job Fairs",
    "Chamber of Commerce & Industrial Association Fairs",
    "Sector-Specific Tech & Startup Aggregators",
    "Media House & Publication Job Fairs",
    "Equity, Diversity & Inclusion (DEI) Foundations",
]


ALLOWED_SKILLS = [
    "BE /B Tech and Post Graduate",
    "Graduates",
    "ITI / Diploma",
    "10th Pass and Above",
    "Below 10th",
]


SEARCH_QUERIES = [
    (
        "Upcoming job fairs and recruitment fairs in India from "
        f"{TODAY} onward employers recruiter participation 2026 2027"
    ),
    (
        "site:ncs.gov.in upcoming job fair rojgar mela India "
        f"{TODAY} 2026 2027"
    ),
    (
        "upcoming government rojgar mela job fair India district employment "
        f"2026 2027 after {TODAY}"
    ),
    (
        "upcoming technology startup career fair hiring fair India "
        f"2026 2027 after {TODAY}"
    ),
    (
        "upcoming virtual career fair India employers recruitment "
        f"2026 2027 after {TODAY}"
    ),
    (
        "upcoming skill council job fair India NSDC MSDE NIELIT BFSI "
        f"2026 2027 after {TODAY}"
    ),
    (
        "upcoming chamber commerce industrial association job fair India "
        f"2026 2027 after {TODAY}"
    ),
]


def load_existing_events():
    print("Loading existing events...")

    if not EVENTS_FILE.exists():
        print("events.json does not exist yet.")
        return []

    with EVENTS_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise RuntimeError("events.json must contain a JSON array.")

    print(f"Existing events: {len(data)}")
    return data


def normalize_url(url):
    if not url:
        return ""

    url = str(url).strip()

    try:
        parts = urlsplit(url)

        scheme = parts.scheme.lower() or "https"
        netloc = parts.netloc.lower().replace("www.", "")
        path = parts.path.rstrip("/")

        return urlunsplit((scheme, netloc, path, "", ""))

    except Exception:
        return url.lower().rstrip("/")


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def tavily_search(query):
    if not TAVILY_API_KEY:
        raise RuntimeError(
            "TAVILY_API_KEY is missing. "
            "Add it as a GitHub Actions repository secret."
        )

    extraction_instruction = f"""
Find genuine upcoming job fairs, recruitment fairs, rojgar melas,
career fairs, employment fairs or hiring events in India.

Today is {TODAY}.

Only include events that are either:
1. scheduled on or after today, or
2. explicitly recurring / rolling / district-wise.

Focus on events where an employer or recruitment company such as
CIEL HR could potentially participate, recruit or attend.

Using the search evidence, return ONLY a valid JSON array.
Do not include Markdown.
Do not include commentary before or after the JSON.

Each object must have exactly these fields:

{{
  "name": "event name",
  "date": "YYYY-MM-DD OR Recurring — description",
  "region": "city/state/region",
  "category": "one allowed category",
  "org": "organizer",
  "fmt": "In-person OR Virtual OR Hybrid",
  "fee": "Free OR On request",
  "regClose": "YYYY-MM-DD OR Rolling OR empty string",
  "est": 0,
  "skills": ["one or more allowed skill labels"],
  "url": "best direct source URL"
}}

Allowed categories:
{json.dumps(ALLOWED_CATEGORIES, ensure_ascii=False)}

Allowed skills:
{json.dumps(ALLOWED_SKILLS, ensure_ascii=False)}

Rules:
- Never invent a date.
- Never invent a registration deadline.
- Never invent a participation fee.
- If the participation fee is not clearly stated, use "On request".
- If estimated footfall is unavailable, use 0.
- Prefer official government, organizer, institution or event URLs.
- Do not include clearly expired events.
- Do not include ordinary job vacancies that are not job fairs.
- Do not include college admissions fairs.
- Do not include foreign events unless physically or virtually relevant to India.
- Keep the event name concise and factual.
"""

    payload = {
    "query": (
    query
    + " Return ONLY a JSON array of genuine upcoming India job fairs. "
    + "Each item must contain: name,date,region,category,org,fmt,fee,"
    + "regClose,est,skills,url. No markdown or explanation."
),
    "search_depth": "advanced",
    "topic": "general",
    "max_results": 10,
    "include_answer": "advanced",
    "include_raw_content": False,
    "include_images": False,
    "include_favicon": False,
    "safe_search": True,
}

    headers = {
        "Authorization": f"Bearer {TAVILY_API_KEY}",
        "Content-Type": "application/json",
    }

    print()
    print("Searching Tavily:")
    print(query)

    response = requests.post(
        TAVILY_API_URL,
        headers=headers,
        json=payload,
        timeout=90,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Tavily API error {response.status_code}: {response.text}"
        )

    return response.json()


def extract_json_array(answer):
    if not answer:
        return []

    text = str(answer).strip()

    # Remove Markdown code fences if Tavily ever returns them.
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)

    # First try the entire response.
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        pass

    # Fallback: find the first JSON-array-looking block.
    match = re.search(r"\[[\s\S]*\]", text)

    if not match:
        print("No JSON array found in Tavily answer.")
        return []

    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError as exc:
        print(f"Could not parse Tavily JSON answer: {exc}")
        return []


def clean_event(raw):
    if not isinstance(raw, dict):
        return None

    name = str(raw.get("name", "")).strip()
    event_date = str(raw.get("date", "")).strip()
    region = str(raw.get("region", "")).strip()
    category = str(raw.get("category", "")).strip()
    org = str(raw.get("org", "")).strip()
    fmt = str(raw.get("fmt", "")).strip()
    fee = str(raw.get("fee", "")).strip()
    reg_close = str(raw.get("regClose", "")).strip()
    url = str(raw.get("url", "")).strip()

    if not name or not url:
        return None

    if not url.lower().startswith(("http://", "https://")):
        return None

    if category not in ALLOWED_CATEGORIES:
        category = "District Employment Exchange Fairs"

    fmt_lookup = {
        "in person": "In-person",
        "in-person": "In-person",
        "physical": "In-person",
        "offline": "In-person",
        "virtual": "Virtual",
        "online": "Virtual",
        "hybrid": "Hybrid",
    }

    fmt = fmt_lookup.get(fmt.lower(), fmt)

    if fmt not in {"In-person", "Virtual", "Hybrid"}:
        fmt = "In-person"

    if fee.lower() == "free":
        fee = "Free"
    else:
        fee = "On request"

    try:
        est = int(raw.get("est", 0) or 0)
        if est < 0:
            est = 0
    except (TypeError, ValueError):
        est = 0

    raw_skills = raw.get("skills", [])

    if isinstance(raw_skills, str):
        raw_skills = [raw_skills]

    skills = [
        skill
        for skill in raw_skills
        if skill in ALLOWED_SKILLS
    ]

    if not skills:
        skills = ["Graduates"]

    return {
        "name": name,
        "date": event_date,
        "region": region,
        "category": category,
        "org": org,
        "fmt": fmt,
        "fee": fee,
        "regClose": reg_close,
        "est": est,
        "skills": skills,
        "url": url,
    }


def looks_duplicate(candidate, existing):
    candidate_url = normalize_url(candidate.get("url"))
    candidate_name = normalize_text(candidate.get("name"))
    candidate_date = normalize_text(candidate.get("date"))

    for event in existing:
        existing_url = normalize_url(event.get("url"))
        existing_name = normalize_text(event.get("name"))
        existing_date = normalize_text(event.get("date"))

        if candidate_url and existing_url and candidate_url == existing_url:
            return True

        if (
            candidate_name
            and existing_name
            and candidate_name == existing_name
            and candidate_date == existing_date
        ):
            return True

    return False


def next_auto_number(events):
    highest = 0

    for event in events:
        event_id = str(event.get("id", ""))

        match = re.fullmatch(r"auto-(\d+)", event_id)

        if match:
            highest = max(highest, int(match.group(1)))

    return highest + 1


def research_new_events(existing_events):
    discovered = []
    auto_number = next_auto_number(existing_events)

    for query in SEARCH_QUERIES:
        try:
            result = tavily_search(query)
        except Exception as exc:
            print(f"Tavily query failed: {exc}")
            continue

        answer = result.get("answer", "")
        candidates = extract_json_array(answer)

        print(f"Structured candidates returned: {len(candidates)}")

        for raw in candidates:
            event = clean_event(raw)

            if not event:
                continue

            combined = existing_events + discovered

            if looks_duplicate(event, combined):
                print(f"Duplicate skipped: {event['name']}")
                continue

            event["id"] = f"auto-{auto_number}"
            auto_number += 1

            # Put id first to match the existing events.json style.
            ordered_event = {
                "id": event["id"],
                "name": event["name"],
                "date": event["date"],
                "region": event["region"],
                "category": event["category"],
                "org": event["org"],
                "fmt": event["fmt"],
                "fee": event["fee"],
                "regClose": event["regClose"],
                "est": event["est"],
                "skills": event["skills"],
                "url": event["url"],
            }

            discovered.append(ordered_event)

            print(
                "NEW EVENT:",
                ordered_event["name"],
                "|",
                ordered_event["date"],
                "|",
                ordered_event["region"],
            )

    return discovered


def sort_events(events):
    def sort_key(event):
        event_date = str(event.get("date", ""))

        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", event_date):
            return (0, event_date)

        return (1, event_date.lower())

    return sorted(events, key=sort_key)


def save_events(events):
    with EVENTS_FILE.open("w", encoding="utf-8") as f:
        json.dump(
            events,
            f,
            ensure_ascii=False,
            indent=2,
        )

        f.write("\n")


def main():
    print("=" * 60)
    print("CIEL HR JOB FAIR DASHBOARD V2 — TAVILY REFRESH")
    print("=" * 60)
    print(f"Today: {TODAY}")

    existing_events = load_existing_events()

    print("Starting Tavily research...")

    new_events = research_new_events(existing_events)

    if not new_events:
        print()
        print("No new unique job fairs found.")
        print("events.json will remain unchanged.")
        return

    merged = existing_events + new_events
    merged = sort_events(merged)

    save_events(merged)

    print()
    print(f"New events added: {len(new_events)}")
    print(f"Total events now: {len(merged)}")
    print("events.json updated successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
