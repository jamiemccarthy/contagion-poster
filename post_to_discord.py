import os
import requests


DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

DMV_STATES = {"DC", "MD", "VA"}

CDC_ENDPOINTS = {
    "COVID": "https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/sc2/nwsssc2statemapDL.json",
    "Flu": "https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/flua/nwssfluastatemapDL.json",
    "RSV": "https://www.cdc.gov/wcms/vizdata/NCEZID_DIDRI/rsv/nwssrsvstatemapDL.json",
}


def fetch_data():
    """Fetch wastewater viral activity levels for DC, MD, and VA."""
    results = {}
    for virus, url in CDC_ENDPOINTS.items():
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        # CDC JSON files have a UTF-8 BOM; re-decode to handle it
        resp.encoding = "utf-8-sig"  # CDC files have a UTF-8 BOM
        records = resp.json()
        dmv = [r for r in records if r.get("State_Abbreviation") in DMV_STATES]
        results[virus] = dmv
    return results


def format_message(data):
    """Format CDC wastewater data into a Discord message."""
    # Grab the time period from any record (they all share the same week)
    any_record = next(r for records in data.values() for r in records)
    time_period = any_record.get("Time_Period", "unknown period")

    lines = [f"**Wastewater Viral Activity — DMV Area**", f"_{time_period}_\n"]

    for virus, records in data.items():
        lines.append(f"**{virus}**")
        for r in sorted(records, key=lambda r: r["State_Abbreviation"]):
            state = r["State_Abbreviation"]
            level = r.get("WVAL_Category", "No data")
            lines.append(f"  {state}: {level}")
        lines.append("")

    return "\n".join(lines).strip()


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
    print("---")
    post_to_discord(message)


if __name__ == "__main__":
    main()
