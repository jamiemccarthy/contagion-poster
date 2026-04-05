# Data Sources

## Comparison

As of 2026-04-04, all three sources report data through the week ending 2026-03-28.

| Source | Diseases | Geography | What it measures | Freshness | Notes |
|---|---|---|---|---|---|
| Wastewater (NWSS) | COVID, Flu, RSV | State (DC, MD, VA) | Categorical activity level (Very Low–Very High) | Updated Fridays, ~5 day lag | Undocumented CDC endpoints; stable in practice |
| ED Visits (NSSP) | COVID, Flu, RSV | County | % of ED visits + trend direction | Updated weekly, ~7 day lag | data.cdc.gov SODA API (Tyler Technologies/Socrata platform); can filter to specific DMV counties |
| Hospital Admissions (NHSN) | COVID, Flu, RSV | State (DC, MD, VA) | Confirmed new admissions per 100k population | Updated weekly, ~7 day lag | data.cdc.gov SODA API (Tyler Technologies/Socrata platform) |

**Tradeoffs:**
- Wastewater is the earliest signal (detects community spread before people show up at hospitals) but only at state level
- ED visits are county-level, so we can focus on the DC metro area specifically, but they lag wastewater
- Hospital admissions show severity but are state-wide (includes all of VA/MD, not just DMV)

## In Use

### CDC Wastewater Viral Activity Levels (NWSS)

Undocumented JSON endpoints that power the CDC NWSS dashboard. Return state-by-state Wastewater Viral Activity Level (WVAL) categories: Very Low / Low / Moderate / High / Very High. Updated weekly on Fridays.

| Virus | URL |
|---|---|
| COVID (SARS-CoV-2) | `https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/sc2/nwsssc2statemapDL.json` |
| Influenza A | `https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/flua/nwssfluastatemapDL.json` |
| RSV | `https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/rsv/nwssrsvstatemapDL.json` |

Record schema:
```json
{
  "State/Territory": "Alabama",
  "State_Abbreviation": "AL",
  "WVAL_Category": "Very Low",
  "Number_of_Sites": "6",
  "Time_Period": "March 15, 2026 - March 21, 2026",
  "Coverage": null,
  "date_updated": "2026-03-26T08:03:31.383805Z"
}
```

Notes:
- Files have a UTF-8 BOM — use `resp.encoding = "utf-8-sig"` before calling `resp.json()`
- The Bluesky bot `covid-wastewater.bsky.social` uses these same endpoints (source: https://github.com/EricWVGG/covid-wastewater-bluesky), suggesting they are stable enough for a weekly bot
- These are undocumented internal CDC endpoints and could change without notice

### NSSP ED Visit Trajectories

| Dataset | Socrata ID | Endpoint |
|---|---|---|
| NSSP ED Visit Trajectories | `rdmq-nq56` | `https://data.cdc.gov/resource/rdmq-nq56.json` |

Covers COVID, flu, and RSV in one dataset. County-level data for DC, MD, VA confirmed available. Key fields: `week_end`, `geography`, `county`, `percent_visits_covid`, `percent_visits_influenza`, `percent_visits_rsv`, `ed_trends_covid`, `ed_trends_influenza`, `ed_trends_rsv` (trends: "Increasing"/"Decreasing"/"No Change"). No API key required.

Metro DC counties to query:
- **DC:** District of Columbia
- **MD:** Prince Georges, Montgomery, Charles, Anne Arundel, Howard, Frederick
- **VA:** Arlington, Fairfax, Fairfax City, Falls Church City, Loudoun, Prince William, Alexandria City

Example query:
```
https://data.cdc.gov/resource/rdmq-nq56.json?$where=geography in('District of Columbia','Maryland','Virginia')&$order=week_end DESC&$limit=10
```

### NHSN Hospital Admissions

| Dataset | Socrata ID | Endpoint |
|---|---|---|
| Weekly Hospital Respiratory Data (final) | `ua7e-t2fy` | `https://data.cdc.gov/resource/ua7e-t2fy.json` |
| Weekly Hospital Respiratory Data (preliminary) | `mpgq-jmmr` | `https://data.cdc.gov/resource/mpgq-jmmr.json` |

State-level confirmed hospital admissions for COVID, flu, and RSV in DC, MD, VA. Key fields: `weekendingdate`, `jurisdiction`, `totalconfc19newadmper100k`, `totalconfflunewadmper100k`, `totalconfrsvnewadmper100k` (new hospital admissions per 100,000 population during the reporting week). No API key required.

**Reporting completeness:** Each record includes `totalconfc19newadmperchosprep` (and flu/RSV equivalents) — the % of hospitals in that jurisdiction that reported for that week. There are also binary flags like `totalconfc19newadmperchosprepabove80pct` (1 if >80% reported). The most recent week typically has low reporting because not all hospitals have submitted yet.

**Update cadence:** Reporting weeks run Sunday–Saturday. Preliminary data (`mpgq-jmmr`) publishes the following Wednesday. Final data (`ua7e-t2fy`) publishes the following Friday — observed at ~14:00 UTC (10:00 AM Eastern) on 2026-04-03, but this may vary. If the script runs before the update lands, the "(latest complete)" label in the output will reflect the prior week.

**DC structural under-reporting:** DC only has ~11 hospitals and consistently reports around 73% even for older weeks — this appears to be non-participating hospitals, not a lag. MD and VA reach 78–93% for completed weeks. We average reporting % across DC+MD+VA and require ≥80% to consider a week complete; this typically means skipping the most recent week and using the one before it.

Example query:
```
https://data.cdc.gov/resource/ua7e-t2fy.json?$where=jurisdiction in('DC','MD','VA')&$order=weekendingdate DESC&$limit=10
```

## Evaluated But Not Used

### data.cdc.gov Socrata API — Lab Test Positivity (NREVSS)

Percent positivity from clinical lab testing, by HHS Region. Covers SARS-CoV-2, RSV, Adenovirus, HCOV, HMPV, PIV, RV/EV but **not Influenza**. Region-level only (not state/county), so less useful for DMV. Socrata IDs: `gvsb-yw6g`, `3cxc-4k8q`, `rgnm-fkqb`.

### data.cdc.gov — Combined Wastewater Dataset

Dataset `atcp-73re` exists on data.cdc.gov but returns 403 — not publicly accessible.

### Bluesky Bot

`covid-wastewater.bsky.social` posts COVID wastewater levels every Friday. Only covers COVID (not flu/RSV), and requires parsing emoji text. Better to use the CDC JSON endpoints directly.
