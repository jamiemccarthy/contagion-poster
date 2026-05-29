import argparse
import os
from collections import defaultdict

import requests


DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# 2020-census populations used to compute a population-weighted average of the
# CDC's per-100k admission rates across the three jurisdictions. This gives a
# single DMV-region figure rather than treating DC (689k people) the same as
# VA (8.7M people) in a simple average.
DMV_POPULATIONS = {"DC": 689_000, "MD": 6_177_000, "VA": 8_744_000}
DMV_TOTAL_POP = sum(DMV_POPULATIONS.values())

# Metro DC counties for ED visit data. ED visits are reported per-county,
# unlike wastewater and hospital admissions which are state-level.
METRO_DC_COUNTIES = {
    "District of Columbia": ["District of Columbia"],
    "Maryland": [
        "Anne Arundel", "Charles", "Frederick", "Howard",
        "Montgomery", "Prince Georges",
    ],
    "Virginia": [
        "Alexandria City", "Arlington", "Fairfax", "Fairfax City",
        "Falls Church City", "Loudoun", "Prince William",
    ],
}

# Undocumented CDC endpoint for NWSS wastewater viral activity levels (WVAL).
# Returns one row per state per pathogen — categorical levels
# (Very Low / Low / Moderate / High / Very High). Wastewater is the earliest
# signal — it detects community spread before people show up at hospitals.
# This feed replaced the per-pathogen nwss{sc2,flua,rsv}statemap.json files
# in May 2026; updates land Wed/Thu.
WASTEWATER_URL = (
    "https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/NWSS_WVAL_metric/NWSSWVALStateDatabites.json"
)

# The new feed identifies pathogens by full name; map to our virus keys.
WASTEWATER_PATHOGEN_MAP = {
    "SARS-CoV-2": "COVID",
    "Influenza A virus": "Flu",
    "RSV": "RSV",
}

# The new feed identifies states by full name; we want abbreviations.
DMV_STATE_NAMES = {
    "District of Columbia": "DC",
    "Maryland": "MD",
    "Virginia": "VA",
}

# Official Socrata API on data.cdc.gov. % of ED visits for each disease plus
# a trend direction (Increasing / Decreasing / No Change). County-level.
ED_VISITS_URL = "https://data.cdc.gov/resource/rdmq-nq56.json"

# Official Socrata API on data.cdc.gov. Confirmed new hospital admissions for
# COVID, flu, and RSV. State-level (covers all of MD/VA, not just the metro).
HOSPITAL_ADMISSIONS_URL = "https://data.cdc.gov/resource/ua7e-t2fy.json"


# ---------------------------------------------------------------------------
# Concern level classification
#
# All three data sources use the same four-level scale: Low / Moderate / High /
# Very High. For each source the thresholds are calibrated independently
# against its own historical peaks and troughs.
# ---------------------------------------------------------------------------

# CDC wastewater levels mapped to our concern scale.
WASTEWATER_TO_CONCERN = {
    "Very Low": "Low",
    "Low":      "Low",
    "Moderate": "Moderate",
    "High":     "High",
    "Very High": "Very High",
}

# ED visit thresholds (% of DC-metro ED visits, averaged across DMV counties).
# Calibrated from 2022-2026 data:
#   COVID: recent seasonal peaks ~2.8-3.2%; off-season baseline ~0.3-0.5%
#   Flu:   winter 2025 peak ~11.1%; off-season baseline ~0.05-0.2%
#   RSV:   peak ~1.75% (Oct 2022); off-season baseline ~0.01%
ED_VISIT_THRESHOLDS = {
    "COVID": {"Low": 0.80, "Moderate": 1.60, "High": 2.40},
    "Flu":   {"Low": 2.80, "Moderate": 5.60, "High": 8.30},
    "RSV":   {"Low": 0.44, "Moderate": 0.88, "High": 1.31},
}

# Hospital admission thresholds (weekly new admissions per 100k population,
# population-weighted across DC+MD+VA). Calibrated from the 2025-06 through
# 2026-03 season using the CDC's own per-100k fields.
#
# Note: these counts include all patients admitted *with* confirmed disease,
# not only those admitted *for* the disease as the primary reason. The same
# definition applies consistently to all three diseases, so they are
# comparable to each other but may overcount severity.
#
#   COVID: summer 2025 peak 2.61/100k (Sep 6), winter peak 2.06/100k (Jan 10),
#          off-season trough ~0.59/100k
#   Flu:   winter peak 13.28/100k (Jan 3); off-season baseline ~0.07-0.20/100k
#   RSV:   winter peak 2.26/100k (Jan 10); off-season baseline <0.10/100k
ADMISSION_THRESHOLDS = {
    "COVID": {"Low": 0.70, "Moderate": 1.50, "High": 2.10},
    "Flu":   {"Low": 1.50, "Moderate": 5.00, "High": 10.0},
    "RSV":   {"Low": 0.30, "Moderate": 1.00, "High": 1.80},
}

# Trend thresholds: % change of current week vs prior 3-week average.
# Positive means admissions are rising. Only flags concern when rising;
# a stable or declining trend is always Low concern.
TREND_THRESHOLDS = {"Low": 0.15, "Moderate": 0.40, "High": 0.70}

CONCERN_LEVELS = ["Low", "Moderate", "High", "Very High"]

# Standard abbreviated month names (AP style; May/June/July are not shortened)
MONTH_ABBREVS = {
    1: "Jan.", 2: "Feb.", 3: "Mar.", 4: "Apr.", 5: "May",
    6: "June", 7: "July", 8: "Aug.", 9: "Sep.", 10: "Oct.",
    11: "Nov.", 12: "Dec.",
}


def format_date(iso_date):
    """Format an ISO date string (YYYY-MM-DD) as 'Mon. DD', e.g. 'Mar. 21'."""
    year, month, day = iso_date.split("-")
    return f"{MONTH_ABBREVS[int(month)]} {int(day)}"


def max_concern(*concerns):
    """Return the highest concern level from the given values."""
    return CONCERN_LEVELS[max(CONCERN_LEVELS.index(c) for c in concerns)]


def classify_wastewater_concern(level):
    """Map a CDC wastewater activity level to our concern scale."""
    return WASTEWATER_TO_CONCERN.get(level, "Low")


def classify_ed_visit_concern(pct, virus):
    """Classify the % of ED visits for a virus.

    Returns one of: Low, Medium, High, Very High.
    Calibrated against 2022-2026 seasonal peaks for DC-metro counties.
    """
    t = ED_VISIT_THRESHOLDS[virus]
    if pct < t["Low"]:      return "Low"
    elif pct < t["Moderate"]: return "Moderate"
    elif pct < t["High"]:   return "High"
    else:                   return "Very High"


def classify_absolute_concern(admissions, virus):
    """Classify the absolute level of hospital admissions for a virus.

    Returns one of: Low, Medium, High, Very High.
    Based on where this week's combined DC+MD+VA admissions fall relative
    to peaks observed in the 2025-2026 season.
    """
    t = ADMISSION_THRESHOLDS[virus]
    if admissions < t["Low"]:      return "Low"
    elif admissions < t["Moderate"]: return "Moderate"
    elif admissions < t["High"]:   return "High"
    else:                          return "Very High"


def classify_trend_concern(current, prior_3wk_avg):
    """Classify whether hospital admissions are rising relative to recent weeks.

    Compares the current week to the average of the prior 3 weeks.
    Returns one of: Low, Medium, High, Very High.
    Only flags concern when admissions are *increasing*; a decline is always Low.
    """
    if prior_3wk_avg == 0:
        return "Low"
    pct_change = (current - prior_3wk_avg) / prior_3wk_avg
    if pct_change <= TREND_THRESHOLDS["Low"]:      return "Low"
    elif pct_change <= TREND_THRESHOLDS["Moderate"]: return "Moderate"
    elif pct_change <= TREND_THRESHOLDS["High"]:   return "High"
    else:                                          return "Very High"


def trend_direction(current, prior_3wk_avg):
    """Describe whether admissions are rising, stable, or declining.

    Uses the same ±15% threshold as classify_trend_concern's Low boundary.
    """
    if prior_3wk_avg == 0:
        return "stable"
    pct_change = (current - prior_3wk_avg) / prior_3wk_avg
    if pct_change > TREND_THRESHOLDS["Low"]:
        return "rising"
    elif pct_change < -TREND_THRESHOLDS["Low"]:
        return "declining"
    return "stable"


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_wastewater():
    """Fetch wastewater viral activity levels for DC, MD, VA.

    The new combined feed returns 53 states × 3 pathogens. We filter to
    DMV states, group by virus, and normalize the field names so callers
    can read State_Abbreviation / WVAL_Category as before.
    """
    resp = requests.get(WASTEWATER_URL, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8-sig"  # CDC files have a UTF-8 BOM
    records = resp.json()

    results = {virus: [] for virus in WASTEWATER_PATHOGEN_MAP.values()}
    for r in records:
        state_name = r.get("State/Territory")
        if state_name not in DMV_STATE_NAMES:
            continue
        virus = WASTEWATER_PATHOGEN_MAP.get(r.get("Pathogen_Target"))
        if not virus:
            continue
        results[virus].append({
            "State_Abbreviation": DMV_STATE_NAMES[state_name],
            "WVAL_Category": r.get("State/Territory_WVAL_Category"),
            "Week_End": r.get("Week_End"),
        })
    return results


def fetch_ed_visits():
    """Fetch ED visit percentages for DC-metro counties.

    Returns the most recent week of data for each county in DMV_COUNTIES.
    """
    # Build a SoQL filter for our specific counties within each state
    county_clauses = [
        f"(geography='{state}' AND county='{county}')"
        for state, counties in METRO_DC_COUNTIES.items()
        for county in counties
    ]
    resp = requests.get(ED_VISITS_URL, params={
        "$where": " OR ".join(county_clauses),
        "$order": "week_end DESC",
        # One row per county per week; grab enough for the latest week
        "$limit": "100",
    }, timeout=15)
    resp.raise_for_status()
    records = resp.json()

    if not records:
        return []

    # All counties share the same reporting week; keep only the most recent
    latest_week = records[0]["week_end"]
    return [r for r in records if r["week_end"] == latest_week]


def fetch_hospital_admissions():
    """Fetch several weeks of hospital admissions for DC, MD, VA.

    Returns enough history to compute the current week plus a 3-week
    trailing average for trend detection. Each week includes a
    reporting_pct field indicating what fraction of hospitals reported.
    """
    resp = requests.get(HOSPITAL_ADMISSIONS_URL, params={
        "$where": "jurisdiction in('DC','MD','VA')",
        "$order": "weekendingdate DESC",
        # 6 weeks × 3 jurisdictions = 18 rows gives us a buffer
        "$limit": "18",
    }, timeout=15)
    resp.raise_for_status()
    records = resp.json()

    # Compute a population-weighted average of the CDC's per-100k fields
    # across DC+MD+VA for each week. Weighting by population prevents DC
    # (700k residents) from having equal influence to VA (8.7M residents)
    # in a simple average, since per-100k rates for a small jurisdiction
    # can be volatile.
    #
    # We also track reporting completeness (% of hospitals that submitted
    # data) to detect weeks where reporting is still in progress.
    by_week = defaultdict(lambda: {
        "COVID": 0.0, "Flu": 0.0, "RSV": 0.0,
        "_reporting_pcts": [],
    })
    for r in records:
        w = r["weekendingdate"][:10]
        jur = r["jurisdiction"]
        weight = DMV_POPULATIONS[jur] / DMV_TOTAL_POP
        by_week[w]["COVID"] += float(r.get("totalconfc19newadmper100k") or 0) * weight
        by_week[w]["Flu"]   += float(r.get("totalconfflunewadmper100k") or 0) * weight
        by_week[w]["RSV"]   += float(r.get("totalconfrsvnewadmper100k") or 0) * weight
        # Each record has a field for what % of hospitals in that jurisdiction
        # reported COVID admissions. We average across DC/MD/VA as a proxy
        # for overall completeness.
        pct = r.get("totalconfc19newadmperchosprep")
        if pct is not None:
            by_week[w]["_reporting_pcts"].append(float(pct))

    weeks = []
    for w in sorted(by_week, reverse=True):
        raw = by_week[w]
        pcts = raw["_reporting_pcts"]
        weeks.append({
            "week": w,
            "COVID": raw["COVID"],
            "Flu":   raw["Flu"],
            "RSV":   raw["RSV"],
            "reporting_pct": sum(pcts) / len(pcts) if pcts else 0,
        })
    return weeks


# The dataset includes a field for what % of hospitals have reported for each
# week. Below 80% means substantial data is still missing and the totals
# will be revised upward. We skip those weeks.
REPORTING_COMPLETENESS_THRESHOLD = 80.0


def pick_latest_complete_week(weeks):
    """Find the most recent week where ≥80% of hospitals have reported.

    The NHSN dataset tracks how many hospitals submitted data for each week.
    The most recent week often has low reporting because hospitals haven't
    all submitted yet. Final data typically publishes Fridays in the morning
    (observed ~14:00 UTC, but timing varies). Our script runs Fridays at
    16:00 UTC, so the most recent week may or may not be complete depending
    on whether CDC has published yet.
    """
    for i, week in enumerate(weeks):
        if week["reporting_pct"] >= REPORTING_COMPLETENESS_THRESHOLD:
            return i
    # Fallback: if nothing meets the threshold, use the second week
    return min(1, len(weeks) - 1)


def fetch_data():
    """Fetch all three data sources."""
    return {
        "wastewater": fetch_wastewater(),
        "ed_visits": fetch_ed_visits(),
        "hospital_admissions": fetch_hospital_admissions(),
    }


# ---------------------------------------------------------------------------
# Summarize each data source into structured dicts
# ---------------------------------------------------------------------------

def summarize_wastewater(ww):
    """Distill raw wastewater records into a summary dict.

    Returns: {"week_end": "YYYY-MM-DD", virus: {"DC": level, "MD": level,
              "VA": level, "concern": concern_level}, ...}
    All records share the same reporting week, so we grab Week_End from any.
    """
    any_record = next(r for records in ww.values() for r in records)
    summary = {"week_end": any_record.get("Week_End")}
    for virus, records in ww.items():
        levels = {}
        for r in records:
            levels[r["State_Abbreviation"]] = r.get("WVAL_Category", "No data")
        concern = max_concern(*[classify_wastewater_concern(lv) for lv in levels.values()])
        summary[virus] = {"DC": levels.get("DC"), "MD": levels.get("MD"),
                          "VA": levels.get("VA"), "concern": concern}
    return summary


def summarize_ed_visits(ed):
    """Distill raw ED visit records into per-disease averages and concern levels.

    Averages % of visits across all DMV counties for a metro-wide summary.
    For trend, if any county is Increasing we call the whole metro Increasing;
    if all are Decreasing we call it Decreasing; otherwise Stable.

    Returns: {"week_end": "...", virus: {"pct": float, "trend": str,
              "concern": str}, ...}  or None if no data.
    """
    if not ed:
        return None

    def avg_pct(field):
        vals = [float(r[field]) for r in ed if r.get(field)]
        return sum(vals) / len(vals) if vals else 0.0

    def metro_trend(field):
        trends = {r.get(field) for r in ed if r.get(field)}
        if "Increasing" in trends:
            return "increasing"
        if "Decreasing" in trends and "No Change" not in trends:
            return "declining"
        return "stable"

    result = {"week_end": ed[0]["week_end"][:10]}
    for virus, pct_field, trend_field in [
        ("COVID", "percent_visits_covid",   "ed_trends_covid"),
        ("Flu",   "percent_visits_influenza", "ed_trends_influenza"),
        ("RSV",   "percent_visits_rsv",     "ed_trends_rsv"),
    ]:
        pct = avg_pct(pct_field)
        result[virus] = {
            "pct": pct,
            "trend": metro_trend(trend_field),
            "concern": classify_ed_visit_concern(pct, virus),
        }
    return result


def summarize_hospital_admissions(weeks):
    """Distill weekly hospital admission history into per-disease concern levels.

    Selects the most recent complete week, computes a 3-week trailing average
    for trend detection, and classifies concern for each virus.

    Returns: {"week": "...", "skipped_incomplete": bool,
              virus: {"per100k": float, "concern": str, "trend_dir": str}, ...}
    """
    idx = pick_latest_complete_week(weeks)
    current = weeks[idx]
    prior_3 = weeks[idx + 1 : idx + 4]

    summary = {
        "week": current["week"],
        "skipped_incomplete": idx > 0,
    }
    for virus in ["COVID", "Flu", "RSV"]:
        per100k = current[virus]
        absolute = classify_absolute_concern(per100k, virus)
        if len(prior_3) >= 3:
            prior_avg = sum(w[virus] for w in prior_3) / 3
            trend_concern = classify_trend_concern(per100k, prior_avg)
            trend_dir = trend_direction(per100k, prior_avg)
        else:
            trend_concern = "Low"
            trend_dir = "stable"
        summary[virus] = {
            "per100k": per100k,
            "concern": max_concern(absolute, trend_concern),
            "trend_dir": trend_dir,
        }
    return summary


def compute_overall_concerns(ww_summary, ed_summary, hosp_summary):
    """Combine all three data sources into a single overall concern per disease.

    Returns: {virus: concern_level, ...}
    """
    result = {}
    for virus in ["COVID", "Flu", "RSV"]:
        ww_concern = ww_summary[virus]["concern"]
        ed_concern = ed_summary[virus]["concern"] if ed_summary else "Low"
        hosp_concern = hosp_summary[virus]["concern"]
        result[virus] = max_concern(ww_concern, ed_concern, hosp_concern)
    return result


# ---------------------------------------------------------------------------
# Message formatting — three detail levels
# ---------------------------------------------------------------------------

def format_low(overall_concerns):
    """Single-line summary. All three diseases listed, grouped by level, highest first."""
    by_level = defaultdict(list)
    for virus in ["COVID", "Flu", "RSV"]:
        by_level[overall_concerns[virus]].append(virus)
    sorted_levels = sorted(by_level, key=CONCERN_LEVELS.index, reverse=True)
    parts = ["/".join(by_level[level]) + f" {level.lower()}" for level in sorted_levels]
    return "Contagion levels: " + ", ".join(parts)


def format_medium(overall_concerns, ww_summary, ed_summary, hosp_summary, date_iso=None):
    """Per-disease summary. Elevated diseases show the contributing factors."""
    if date_iso is None:
        date_iso = hosp_summary["week"]
    week = format_date(date_iso)
    lines = [f"Contagion update — as of {week}"]

    for virus in ["COVID", "Flu", "RSV"]:
        concern = overall_concerns[virus]
        if concern == "Low":
            lines.append(f"{virus}: low")
            continue

        # Collect the factors that are driving the concern
        factors = []

        ww = ww_summary[virus]
        if ww["concern"] != "Low":
            ww_display_order = ["Very Low", "Low", "Moderate", "High", "Very High"]
            ww_vals = [ww[st] for st in ["DC", "MD", "VA"] if ww[st]]
            unique = sorted(set(ww_vals), key=ww_display_order.index)
            if len(unique) == 1:
                factors.append(f"wastewater {unique[0].lower()}")
            else:
                factors.append(f"wastewater {unique[0].lower()} to {unique[-1].lower()}")

        hosp = hosp_summary[virus]
        if hosp["concern"] != "Low":
            factors.append(
                f"hospital admissions {hosp['concern'].lower()} and {hosp['trend_dir']}"
            )

        if ed_summary:
            ed = ed_summary[virus]
            if ed["concern"] != "Low":
                factors.append(f"ED visits {ed['concern'].lower()}")

        lines.append(f"{virus}: {concern.lower()} ({'; '.join(factors)})")

    return "\n".join(lines)


def format_high(overall_concerns, ww_summary, ed_summary, hosp_summary, date_iso=None):
    """Full detail: all three data sources, all numbers, per disease."""
    if date_iso is None:
        date_iso = hosp_summary["week"]
    week = format_date(date_iso)
    lines = [f"Contagion update — as of {week}", ""]

    for virus in ["COVID", "Flu", "RSV"]:
        concern = overall_concerns[virus]
        lines.append(f"**{virus}: {concern}**")

        # Wastewater
        ww = ww_summary[virus]
        ww_states = [ww[st] for st in ["DC", "MD", "VA"] if ww[st]]
        if len(set(ww_states)) == 1:
            lines.append(f"  Wastewater: {ww_states[0]} across DMV")
        else:
            state_str = ", ".join(f"{st} {ww[st]}" for st in ["DC", "MD", "VA"])
            lines.append(f"  Wastewater: {state_str}")

        # ED visits
        if ed_summary:
            ed = ed_summary[virus]
            lines.append(
                f"  ED visits: {ed['pct']:.1f}% ({ed['concern']}, {ed['trend']})"
            )

        # Hospital admissions
        hosp = hosp_summary[virus]
        lines.append(
            f"  Hospital admissions: {hosp['per100k']:.2f}/100k"
            f" ({hosp['concern']}, {hosp['trend_dir']})"
        )

        lines.append("")

    return "\n".join(lines).rstrip()


def format_message(data, detail="low"):
    """Format all data into a Discord message at the requested detail level."""
    ww_summary   = summarize_wastewater(data["wastewater"])
    ed_summary   = summarize_ed_visits(data["ed_visits"])
    hosp_summary = summarize_hospital_admissions(data["hospital_admissions"])
    overall      = compute_overall_concerns(ww_summary, ed_summary, hosp_summary)

    # Use the wastewater week_end (most current data source)
    date_to_use = ww_summary.get("week_end") or hosp_summary["week"]

    if detail == "low":
        return format_low(overall)
    elif detail == "medium":
        return format_medium(overall, ww_summary, ed_summary, hosp_summary, date_to_use)
    else:
        return format_high(overall, ww_summary, ed_summary, hosp_summary, date_to_use)


def post_to_discord(content):
    """Post a message to a Discord channel via webhook."""
    response = requests.post(
        DISCORD_WEBHOOK_URL,
        json={"content": content},
        timeout=10,
    )
    response.raise_for_status()
    print(f"Posted to Discord (status {response.status_code})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--detail",
        choices=["low", "medium", "high"],
        default="low",
        help="Amount of detail to include in the Discord message (default: low)",
    )
    args = parser.parse_args()

    data = fetch_data()
    message = format_message(data, detail=args.detail)
    print(message)
    if DISCORD_WEBHOOK_URL:
        post_to_discord(message)
    else:
        print("(no DISCORD_WEBHOOK_URL set — skipping Discord post)")


if __name__ == "__main__":
    main()
