"""
setup_location.py — Find NWSS wastewater monitoring sites near a lat/long and
write location.json for use by post_to_discord.py.

Site selection targets (guidelines, not hard limits):
  - At least 500k population served by selected sites
  - At least 3 sites per pathogen (SARS-CoV-2, Influenza A virus, RSV)
  - Within 400 km
  - Stop before exceeding 10M population served

Usage:
    python setup_location.py LAT LON

Examples:
    python setup_location.py 38.90 -77.03   # Washington DC
    python setup_location.py 40.35 -74.66   # Princeton NJ
    python setup_location.py 41.88 -87.63   # Chicago IL
"""

import json
import math
import os
import sys
import urllib.request
from datetime import datetime, timezone


SITE_MAP_URL = (
    "https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/NWSS_WVAL_metric/NWSSWVALSiteMap.json"
)
LOCATION_FILE = os.path.join(os.path.dirname(__file__), "location.json")

MIN_POPULATION = 1_000_000
MIN_SITES_PER_PATHOGEN = 5
MAX_POPULATION = 10_000_000
MAX_RADIUS_KM = 400

PATHOGENS = {"SARS-CoV-2", "Influenza A virus", "RSV"}

US_ABBREVIATIONS = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI",
    "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME",
    "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE",
    "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH",
    "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
    "Puerto Rico": "PR", "Guam": "GU", "Virgin Islands": "VI",
    "American Samoa": "AS", "Northern Mariana Islands": "MP",
}


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def fetch_site_map():
    req = urllib.request.Request(SITE_MAP_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw.decode("utf-8-sig"))


def main():
    if len(sys.argv) != 3:
        print("Usage: python setup_location.py LAT LON")
        print("Example: python setup_location.py 38.90 -77.03   # Washington DC")
        sys.exit(1)

    user_lat = float(sys.argv[1])
    user_lon = float(sys.argv[2])
    print(f"Location: {user_lat}, {user_lon}")
    print("Fetching NWSS site map...")

    records = fetch_site_map()
    print(f"  {len(records)} records")

    # Deduplicate by site ID — each site appears once per pathogen in the feed
    sites = {}
    for r in records:
        site_id = r.get("Site")
        if not site_id:
            continue
        try:
            lat = float(r["Latitude_jitter"])
            lon = float(r["Longitude_jitter"])
        except (KeyError, ValueError, TypeError):
            continue
        if site_id not in sites:
            sites[site_id] = {
                "site_id": site_id,
                "state": r.get("State/Territory", ""),
                "counties": [
                    c.strip()
                    for c in r.get("Counties_Served", "").split(",")
                    if c.strip()
                ],
                "population": int(r.get("Population_Served") or 0),
                "lat": lat,
                "lon": lon,
                "pathogens": set(),
            }
        sites[site_id]["pathogens"].add(r.get("Pathogen_Target", ""))

    print(f"  {len(sites)} unique sites")

    for s in sites.values():
        s["distance_km"] = haversine_km(user_lat, user_lon, s["lat"], s["lon"])

    sorted_sites = sorted(sites.values(), key=lambda s: s["distance_km"])

    # Walk sites in distance order; stop at the smallest radius where minimums are met.
    # If population would exceed the cap before minimums are met, treat that as the
    # stopping point anyway (the cap is a guideline, not a hard limit).
    running_pop = 0
    running_pathogen_counts = {p: 0 for p in PATHOGENS}
    sweet_spot_radius = None

    for site in sorted_sites:
        if site["distance_km"] > MAX_RADIUS_KM:
            break
        running_pop += site["population"]
        for p in PATHOGENS:
            if p in site["pathogens"]:
                running_pathogen_counts[p] += 1

        minimums_met = (
            running_pop >= MIN_POPULATION
            and all(running_pathogen_counts[p] >= MIN_SITES_PER_PATHOGEN for p in PATHOGENS)
        )
        if minimums_met:
            sweet_spot_radius = site["distance_km"]
            break
        if running_pop >= MAX_POPULATION:
            sweet_spot_radius = site["distance_km"]
            break

    if sweet_spot_radius is None:
        reachable = [s for s in sorted_sites if s["distance_km"] <= MAX_RADIUS_KM]
        if not reachable:
            print("No sites found within range.")
            sys.exit(1)
        sweet_spot_radius = reachable[-1]["distance_km"]

    # Include ALL sites within the sweet-spot radius (not just those visited above)
    included = [s for s in sorted_sites if s["distance_km"] <= sweet_spot_radius]

    total_pop = sum(s["population"] for s in included)
    pathogen_counts = {
        p: sum(1 for s in included if p in s["pathogens"]) for p in PATHOGENS
    }

    states = {}  # full state name → abbreviation
    for s in included:
        name = s["state"]
        if name and name not in states:
            states[name] = US_ABBREVIATIONS.get(name, name[:2].upper())

    print(f"\nSelected {len(included)} sites within "
          f"{sweet_spot_radius:.1f} km ({sweet_spot_radius / 1.60934:.0f} mi)")
    print(f"Population served: {total_pop:,}")
    states_display = ", ".join(
        f"{abbrev} ({name})"
        for name, abbrev in sorted(states.items(), key=lambda x: x[1])
    )
    print(f"States: {states_display}")
    print("Sites per pathogen:")
    for p in sorted(PATHOGENS):
        count = pathogen_counts[p]
        flag = "OK " if count >= MIN_SITES_PER_PATHOGEN else "LOW"
        print(f"  [{flag}] {p}: {count}")

    if total_pop < MIN_POPULATION:
        print(f"\nWarning: population ({total_pop:,}) is below target ({MIN_POPULATION:,})")
    if any(pathogen_counts[p] < MIN_SITES_PER_PATHOGEN for p in PATHOGENS):
        print(f"\nWarning: some pathogens have fewer than {MIN_SITES_PER_PATHOGEN} sites")

    config = {
        "lat": user_lat,
        "lon": user_lon,
        "radius_km": round(sweet_spot_radius, 1),
        "states": states,
        "site_ids": [s["site_id"] for s in included],
        "population_served": total_pop,
        "site_counts_by_pathogen": {p: pathogen_counts[p] for p in PATHOGENS},
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    with open(LOCATION_FILE, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\nSaved to {LOCATION_FILE}")


if __name__ == "__main__":
    main()
