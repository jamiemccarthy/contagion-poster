# Data Sources

## Comparison

As of 2026-04-04, all three sources report data through the week ending 2026-03-28.

| Source | Diseases | Geography | What it measures | Freshness | Notes |
|---|---|---|---|---|---|
| Wastewater (NWSS) | COVID, Flu, RSV | State (DC, MD, VA) | Categorical activity level (Very Low–Very High) | Updated Wed/Thu, ~5 day lag | Undocumented CDC endpoint; migrated May 2026 |
| ED Visits (NSSP) | COVID, Flu, RSV | County | % of ED visits + trend direction | Updated weekly, ~7 day lag | data.cdc.gov SODA API (Tyler Technologies/Socrata platform); can filter to specific DMV counties |
| Hospital Admissions (NHSN) | COVID, Flu, RSV | State (DC, MD, VA) | Confirmed new admissions per 100k population | Updated weekly, ~7 day lag | data.cdc.gov SODA API (Tyler Technologies/Socrata platform) |

**Tradeoffs:**
- Wastewater is the earliest signal (detects community spread before people show up at hospitals) but only at state level
- ED visits are county-level, so we can focus on the DC metro area specifically, but they lag wastewater
- Hospital admissions show severity but are state-wide (includes all of VA/MD, not just DMV)

## In Use

### CDC Wastewater Viral Activity Levels (NWSS)

A single undocumented JSON endpoint powers the CDC NWSS dashboard. Returns 159 rows (53 states × 3 pathogens) with Wastewater Viral Activity Level (WVAL) categories: Very Low / Low / Moderate / High / Very High. Updated weekly, observed Wed/Thu.

URL: `https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/NWSS_WVAL_metric/NWSSWVALStateDatabites.json`

Sibling files in the same directory (not currently used):
- `NWSSWVALStateActivityLevel.json` — full history with regional/national rollups
- `NWSSWVALSiteMap.json` — per-site detail

Record schema:
```json
{
  "State/Territory": "Alabama",
  "State/Territory_WVAL_Category": "Very Low",
  "Pathogen_Target": "SARS-CoV-2",
  "Week_End": "2026-05-16",
  "Date_Updated": "May 21, 2026 3:32 AM"
}
```

`Pathogen_Target` values: `"SARS-CoV-2"`, `"Influenza A virus"`, `"RSV"`.

Notes:
- File has a UTF-8 BOM — use `resp.encoding = "utf-8-sig"` before calling `resp.json()`
- `Date_Updated` is a human-readable string with no timezone. `Week_End` is already YYYY-MM-DD.
- Endpoint discovered via `data-config-url="/wastewater/modules/state-page-combined.json"` attribute on the dashboard widget at `cdc.gov/wastewater/respiratory-viruses/state.html`
- This endpoint replaced the old per-pathogen `nwss{sc2,flua,rsv}statemapDL.json` files around 2026-05-07; those files kept returning HTTP 200 with frozen content (stuck at week ending May 2) but were no longer updated
- Undocumented internal CDC endpoint — could change without notice; check the dashboard page's `data-config-url` if it goes stale again

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

Dataset `atcp-73re` exists on data.cdc.gov but returns 403 — not publicly accessible. The successor Socrata dataset `j9g8-acpt` is public but contains raw sample measurements, not the WVAL categorical levels used by the dashboard.

### Bluesky Bot

`covid-wastewater.bsky.social` posts COVID wastewater levels every Friday. Only covers COVID (not flu/RSV), and requires parsing emoji text. Better to use the CDC JSON endpoints directly.
