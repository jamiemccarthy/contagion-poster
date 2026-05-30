# Project Overview

A Python script that posts messages about airborne communicable diseases (flu, Covid, RSV) to Discord via webhook, triggered weekly by GitHub Actions.

The goal is to share information with friends on Discord in advance of a weekly get-together.

This isn't a hard project. Don't make it complicated. Don't go down rabbit holes.

## Commands

```bash
# Set up venv (one-time)
python3 -m venv .venv

# Activate venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure location (one-time, required before running the poster)
python setup_location.py LAT LON   # e.g. 38.95 -77.02 for Washington DC

# Run the script
DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/YOUR_SECRET' python post_to_discord.py
```

## Discord

- Webhook URL: `https://discord.com/api/webhooks/YOUR_SECRET`
- Webhooks are channel-specific — no separate guild/channel ID needed
- The webhook URL is the only secret; it must be stored as `DISCORD_WEBHOOK_URL` in GitHub repo secrets for the Actions workflow

## Architecture

Two scripts:

**`setup_location.py`** — one-time setup. Takes a lat/long, fetches the NWSS wastewater site map, finds nearby monitoring sites using a population/distance sweet-spot algorithm, and writes `location.json`. Must be run before `post_to_discord.py`.

**`post_to_discord.py`** — weekly poster. Reads `location.json` for the configured states and site IDs, then runs a three-stage pipeline:
1. `fetch_data()` - Retrieves data from external sources
2. `format_message()` - Transforms data into Discord message content
3. `post_to_discord()` - Sends message via Discord webhook

Data sources (see `DATA_SOURCES.md` for details):
- **Wastewater (NWSS):** site-level WVAL categories from `NWSSWVALSiteMap.json`, population-weighted across the selected sites, grouped by state
- **ED visits (NSSP):** state-level % of ED visits from data.cdc.gov Socrata API
- **Hospital admissions (NHSN):** state-level confirmed new admissions per 100k from data.cdc.gov Socrata API

GitHub Actions workflow (`.github/workflows/weekly-post.yml`) runs every Friday at 16:00 UTC (noon Eastern), after CDC NHSN data typically publishes in the morning (observed ~14:00 UTC, but timing may vary).
