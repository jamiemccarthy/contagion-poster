"""
Polls CDC data sources and logs their latest-update timestamps to update_log.csv.

Run periodically (e.g. every 6 hours) to build up a picture of when each
source updates during the week. Each run appends one row.

Usage:
    python check_update_times.py
"""

import csv
import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone


RETRY_BASE = 10
RETRY_MAX = 5


LOG_FILE = os.path.join(os.path.dirname(__file__), "update_log.csv")

FIELDNAMES = [
    "checked_at",
    "ww_rows_updated_at",
    "ww_week_end",
    "ed_rows_updated_at",
    "ed_week_end",
    "hosp_final_rows_updated_at",
    "hosp_final_week_end",
    "hosp_prelim_rows_updated_at",
    "hosp_prelim_week_end",
]

WASTEWATER_URL = (
    "https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/NWSS_WVAL_metric/NWSSWVALStateDatabites.json"
)
SOCRATA_META = "https://data.cdc.gov/api/views/{}.json"
SOCRATA_DATA = "https://data.cdc.gov/resource/{}.json"


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(RETRY_MAX):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read()
            # Handle UTF-8 BOM (CDC wastewater files)
            return json.loads(raw.decode("utf-8-sig"))
        except urllib.error.HTTPError as e:
            if e.code in (502, 503) and attempt < RETRY_MAX - 1:
                wait = RETRY_BASE * (2 ** attempt)
                print(f"{e.code} on {url}, retrying in {wait}s (attempt {attempt + 1}/{RETRY_MAX})")
                time.sleep(wait)
            else:
                raise


def unix_to_iso(ts):
    """Convert a Unix timestamp (int or None) to an ISO 8601 string in UTC."""
    if ts is None:
        return ""
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()


def parse_wastewater_date_updated(s):
    """Parse the wastewater feed's Date_Updated string to ISO-8601 (naive).

    Input:  "May 21, 2026 3:32 AM"
    Output: "2026-05-21T03:32:00"

    Timezone is unspecified in the source, so the output is naive.
    """
    if not s:
        return ""
    try:
        return datetime.strptime(s, "%B %d, %Y %I:%M %p").isoformat()
    except ValueError:
        return s


def check_wastewater():
    data = fetch_json(WASTEWATER_URL)
    # Feed has 53 states x 3 pathogens for one week; all rows share Week_End
    # and Date_Updated, so any row will do.
    record = data[0] if data else {}
    return {
        "ww_rows_updated_at": parse_wastewater_date_updated(record.get("Date_Updated", "")),
        "ww_week_end": record.get("Week_End", ""),
    }


def check_socrata_dataset(dataset_id, date_field):
    """Check a Socrata dataset's metadata timestamp and most recent data row."""
    meta = fetch_json(SOCRATA_META.format(dataset_id))
    rows_updated_at = unix_to_iso(meta.get("rowsUpdatedAt"))

    latest = fetch_json(
        f"{SOCRATA_DATA.format(dataset_id)}?$order={date_field}%20DESC&$limit=1"
    )
    week_end = latest[0][date_field][:10] if latest else ""

    return rows_updated_at, week_end


def main():
    checked_at = datetime.now(tz=timezone.utc).isoformat()

    ww = check_wastewater()

    ed_updated, ed_week_end = check_socrata_dataset("rdmq-nq56", "week_end")
    hf_updated, hf_week_end = check_socrata_dataset("ua7e-t2fy", "weekendingdate")
    hp_updated, hp_week_end = check_socrata_dataset("mpgq-jmmr", "weekendingdate")

    row = {
        "checked_at": checked_at,
        "ww_rows_updated_at": ww["ww_rows_updated_at"],
        "ww_week_end": ww["ww_week_end"],
        "ed_rows_updated_at": ed_updated,
        "ed_week_end": ed_week_end,
        "hosp_final_rows_updated_at": hf_updated,
        "hosp_final_week_end": hf_week_end,
        "hosp_prelim_rows_updated_at": hp_updated,
        "hosp_prelim_week_end": hp_week_end,
    }

    write_header = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    print(f"Logged at {checked_at}")
    for k, v in row.items():
        if k != "checked_at":
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
