import os
from collections import defaultdict

import requests


DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

DMV_STATES = {"DC", "MD", "VA"}

# 2020-census populations used to compute a population-weighted average of the
# CDC's per-100k admission rates across the three jurisdictions. This gives a
# single DMV-region figure rather than treating DC (689k people) the same as
# VA (8.7M people) in a simple average.
DMV_POPULATIONS = {"DC": 689_000, "MD": 6_177_000, "VA": 8_744_000}
DMV_TOTAL_POP = sum(DMV_POPULATIONS.values())

# Counties in the DC metro area for ED visit data.
# ED visits are reported per-county, unlike wastewater and hospital admissions
# which are state-level.
DMV_COUNTIES = {
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

# Undocumented CDC endpoints for wastewater viral activity levels (NWSS).
# Return categorical levels (Very Low / Low / Moderate / High / Very High)
# per state. Wastewater is the earliest signal — it detects community spread
# before people show up at hospitals. Updated Fridays.
WASTEWATER_ENDPOINTS = {
    "COVID": "https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/sc2/nwsssc2statemapDL.json",
    "Flu": "https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/flua/nwssfluastatemapDL.json",
    "RSV": "https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/rsv/nwssrsvstatemapDL.json",
}

# Official Socrata API on data.cdc.gov. % of ED visits for each disease plus
# a trend direction (Increasing / Decreasing / No Change). County-level.
ED_VISITS_URL = "https://data.cdc.gov/resource/rdmq-nq56.json"

# Official Socrata API on data.cdc.gov. Confirmed new hospital admissions for
# COVID, flu, and RSV. State-level (covers all of MD/VA, not just the metro).
HOSPITAL_ADMISSIONS_URL = "https://data.cdc.gov/resource/ua7e-t2fy.json"


# ---------------------------------------------------------------------------
# Hospital admission concern levels
#
# Thresholds are weekly new admissions per 100,000 population, using a
# population-weighted average across DC+MD+VA. Calibrated from the
# 2025-06 through 2026-03 season using the CDC's own per-100k fields.
#
# Note: these counts include all patients admitted *with* confirmed disease,
# not only those admitted *for* the disease as the primary reason. The same
# definition applies consistently to all three diseases, so they are
# comparable to each other but may overcount severity.
#
#   COVID: summer 2025 peak 2.61/100k (week of Sep 6),
#          winter 2025 peak 2.06/100k (week of Jan 10),
#          off-season trough ~0.59/100k
#   Flu:   winter peak 13.28/100k (week of Jan 3),
#          off-season baseline ~0.07-0.20/100k
#   RSV:   winter peak 2.26/100k (week of Jan 10),
#          off-season baseline <0.10/100k
#
# "Low" means near off-season baseline.
# "Very High" means at or near the season peak.
# ---------------------------------------------------------------------------

ADMISSION_THRESHOLDS = {
    "COVID": {"low": 0.70, "medium": 1.50, "high": 2.60},
    "Flu":   {"low": 1.50, "medium": 5.00, "high": 10.0},
    "RSV":   {"low": 0.30, "medium": 1.00, "high": 1.80},
}

# Trend thresholds: % change of current week vs prior 3-week average.
# Positive means admissions are rising.
TREND_THRESHOLDS = {"low": 0.15, "medium": 0.40, "high": 0.70}


def classify_absolute_concern(admissions, virus):
    """Classify the absolute level of hospital admissions for a virus.

    Returns one of: Low, Medium, High, Very High.
    Based on where this week's combined DC+MD+VA admissions fall relative
    to peaks observed in the 2025-2026 season.
    """
    thresholds = ADMISSION_THRESHOLDS[virus]
    if admissions < thresholds["low"]:
        return "Low"
    elif admissions < thresholds["medium"]:
        return "Medium"
    elif admissions < thresholds["high"]:
        return "High"
    else:
        return "Very High"


def classify_trend_concern(current, prior_3wk_avg):
    """Classify whether admissions are rising relative to recent weeks.

    Compares the current week to the average of the prior 3 weeks.
    Returns one of: Low, Medium, High, Very High.
    Only flags concern when admissions are *increasing*; a decline is always Low.
    """
    if prior_3wk_avg == 0:
        return "Low"
    pct_change = (current - prior_3wk_avg) / prior_3wk_avg
    if pct_change <= TREND_THRESHOLDS["low"]:
        return "Low"
    elif pct_change <= TREND_THRESHOLDS["medium"]:
        return "Medium"
    elif pct_change <= TREND_THRESHOLDS["high"]:
        return "High"
    else:
        return "Very High"


def overall_concern(absolute, trend):
    """Overall concern is the greater of absolute and trend concern."""
    levels = ["Low", "Medium", "High", "Very High"]
    return levels[max(levels.index(absolute), levels.index(trend))]


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_wastewater():
    """Fetch wastewater viral activity levels for DC, MD, VA."""
    results = {}
    for virus, url in WASTEWATER_ENDPOINTS.items():
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8-sig"  # CDC files have a UTF-8 BOM
        records = resp.json()
        results[virus] = [r for r in records if r.get("State_Abbreviation") in DMV_STATES]
    return results


def fetch_ed_visits():
    """Fetch ED visit percentages for DC-metro counties.

    Returns the most recent week of data for each county in DMV_COUNTIES.
    """
    # Build a SoQL filter for our specific counties within each state
    county_clauses = []
    for state, counties in DMV_COUNTIES.items():
        for county in counties:
            county_clauses.append(
                f"(geography='{state}' AND county='{county}')"
            )
    where = " OR ".join(county_clauses)

    resp = requests.get(ED_VISITS_URL, params={
        "$where": where,
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
    # (689k residents) from having equal influence to VA (8.7M residents)
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
    all submitted yet. Final data publishes Fridays; our script runs Mondays,
    so typically the second-most-recent week is the first complete one.
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
# Message formatting — wastewater
# ---------------------------------------------------------------------------

def summarize_wastewater(ww):
    """Distill raw wastewater records into a simple summary dict.

    Returns: {virus: {state: level, ...}, "period": "..."}
    All records share the same reporting week, so we grab the period from any.
    """
    any_record = next(r for records in ww.values() for r in records)
    summary = {"period": any_record.get("Time_Period", "unknown period")}
    for virus, records in ww.items():
        summary[virus] = {r["State_Abbreviation"]: r.get("WVAL_Category", "No data")
                          for r in records}
    return summary


def format_wastewater(ww):
    """Format wastewater summary into Discord text."""
    summary = summarize_wastewater(ww)
    lines = [
        "**Wastewater Viral Activity (DC, MD, VA)**",
        f"_{summary['period']}_",
    ]
    for virus in ["COVID", "Flu", "RSV"]:
        levels = ", ".join(f"{st}: {summary[virus][st]}" for st in ["DC", "MD", "VA"])
        lines.append(f"  {virus}: {levels}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Message formatting — ED visits
# ---------------------------------------------------------------------------

def summarize_ed_visits(ed):
    """Distill raw ED visit records into per-disease averages and trends.

    Averages % of visits across all DMV counties for a metro-wide summary.
    For trend, if any county is Increasing we call the whole metro Increasing;
    if all are Decreasing we call it Decreasing; otherwise Stable.

    Returns: {"week_end": "...", virus: {"pct": "1.2%", "trend": "Stable"}, ...}
    """
    if not ed:
        return None

    def avg_pct(field):
        vals = [float(r[field]) for r in ed if r.get(field)]
        return f"{sum(vals) / len(vals):.1f}%" if vals else "N/A"

    def metro_trend(field):
        trends = {r.get(field) for r in ed if r.get(field)}
        if "Increasing" in trends:
            return "Increasing"
        if "Decreasing" in trends and "No Change" not in trends:
            return "Decreasing"
        return "Stable"

    return {
        "week_end": ed[0]["week_end"][:10],
        "COVID": {"pct": avg_pct("percent_visits_covid"),   "trend": metro_trend("ed_trends_covid")},
        "Flu":   {"pct": avg_pct("percent_visits_influenza"), "trend": metro_trend("ed_trends_influenza")},
        "RSV":   {"pct": avg_pct("percent_visits_rsv"),     "trend": metro_trend("ed_trends_rsv")},
    }


def format_ed_visits(ed):
    """Format ED visit summary into Discord text."""
    summary = summarize_ed_visits(ed)
    if not summary:
        return None
    lines = [f"**ED Visits — DC Metro Counties** (week ending {summary['week_end']})"]
    for virus in ["COVID", "Flu", "RSV"]:
        pct = summary[virus]["pct"]
        trend = summary[virus]["trend"]
        lines.append(f"  {virus}: {pct} of visits ({trend})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Message formatting — hospital admissions
# ---------------------------------------------------------------------------

def summarize_hospital_admissions(weeks):
    """Distill weekly hospital admission history into per-disease concern levels.

    Selects the most recent complete week, computes a 3-week trailing average
    for trend detection, and classifies absolute and trend concern for each virus.

    Returns: {"week": "...", "skipped_incomplete": bool,
              virus: {"count": int, "absolute": str, "trend": str, "concern": str}, ...}
    """
    idx = pick_latest_complete_week(weeks)
    current = weeks[idx]
    prior_3 = weeks[idx + 1 : idx + 4]

    summary = {
        "week": current["week"],
        "skipped_incomplete": idx > 0,
    }
    for virus in ["COVID", "Flu", "RSV"]:
        per100k = current[virus]  # already normalised in fetch_hospital_admissions
        absolute = classify_absolute_concern(per100k, virus)
        if len(prior_3) >= 3:
            prior_avg = sum(w[virus] for w in prior_3) / 3
            trend = classify_trend_concern(per100k, prior_avg)
        else:
            trend = "Low"
        summary[virus] = {
            "count": per100k,  # per-100k value; field name kept for compatibility
            "absolute": absolute,
            "trend": trend,
            "concern": overall_concern(absolute, trend),
        }
    return summary


def format_hospital_admissions(weeks):
    """Format hospital admissions summary into Discord text."""
    summary = summarize_hospital_admissions(weeks)
    week_label = summary["week"]
    if summary["skipped_incomplete"]:
        week_label += " (latest complete)"
    lines = [f"**Hospital Admissions (DC, MD, VA)** (week ending {week_label})"]
    for virus in ["COVID", "Flu", "RSV"]:
        v = summary[virus]
        lines.append(f"  {virus}: {v['count']:.2f}/100k — concern: {v['concern']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Top-level message assembly
# ---------------------------------------------------------------------------

def format_message(data):
    """Assemble all three sections into a single Discord message."""
    sections = [
        format_wastewater(data["wastewater"]),
        format_ed_visits(data["ed_visits"]),
        format_hospital_admissions(data["hospital_admissions"]),
    ]
    return "\n\n".join(s for s in sections if s)


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
    data = fetch_data()
    message = format_message(data)
    print(message)


if __name__ == "__main__":
    main()
