# Data Sources

## In Use

### CDC Wastewater Viral Activity Levels (NWSS)

Undocumented JSON endpoints that power the CDC NWSS dashboard. Return state-by-state Wastewater Viral Activity Level (WVAL) categories: Very Low / Low / Moderate / High / Very High. Updated weekly on Fridays. All share an identical schema.

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

## Evaluated But Not Used

### data.cdc.gov Socrata API — Lab Test Positivity (NREVSS)

Official documented Socrata/SODA API. Returns percent positivity from clinical lab testing, by HHS Region and National level. No API key required.

| Dataset | Socrata ID | Endpoint |
|---|---|---|
| COVID-19 percent positivity | `gvsb-yw6g` | `https://data.cdc.gov/resource/gvsb-yw6g.json` |
| RSV percent positivity | `3cxc-4k8q` | `https://data.cdc.gov/resource/3cxc-4k8q.json` |
| All respiratory viruses (NREVSS) | `rgnm-fkqb` | `https://data.cdc.gov/resource/rgnm-fkqb.json` |

Notes:
- The all-viruses dataset (`rgnm-fkqb`) covers SARS-CoV-2, RSV, Adenovirus, HCOV, HMPV, PIV, RV/EV but **not Influenza**
- Data is by HHS Region, not by state — less granular for DMV purposes
- Supports SoQL queries for filtering

### data.cdc.gov Socrata API — ED Visit Trajectories (NSSP)

| Dataset | Socrata ID | Endpoint |
|---|---|---|
| NSSP ED Visit Trajectories | `rdmq-nq56` | `https://data.cdc.gov/resource/rdmq-nq56.json` |

Covers COVID, flu, and RSV in one dataset with fields like `percent_visits_covid`, `percent_visits_influenza`, `percent_visits_rsv` and trend indicators. However, it is **county-level only** with no national or state rollups — would need manual aggregation.

### data.cdc.gov — Combined Wastewater Dataset

Dataset `atcp-73re` (Wastewater Viral Activity Level for SARS-CoV-2, Influenza A and RSV) exists on data.cdc.gov but returns 403 — not publicly accessible.

### Bluesky Bot

The account `covid-wastewater.bsky.social` posts COVID wastewater levels every Friday. Fetchable without auth via the public Bluesky API. However, only covers COVID (not flu/RSV), and requires parsing emoji-formatted text. Better to use the same CDC JSON endpoints directly.
