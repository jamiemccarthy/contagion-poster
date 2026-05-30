# Contagion Poster

A Python script that posts weekly summaries of airborne respiratory illness activity to Discord, configurable for any location in the US.

The script monitors three CDC data sources—wastewater, ED visits, and hospital admissions—for COVID, flu, and RSV. It classifies illness activity into concern levels (Low, Moderate, High, Very High) and posts a formatted summary to a Discord channel every Friday.

## Quick Start

```bash
# Set up venv
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure your location (one-time; lat/long in decimal degrees)
python setup_location.py LAT LON
# e.g. python setup_location.py 38.87 -77.01   # Washington DC
#      python setup_location.py 40.35 -74.66   # Princeton NJ
#      python setup_location.py 41.88 -87.62   # Chicago IL

# Run the script
DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/YOUR_SECRET' python post_to_discord.py
```

`setup_location.py` fetches the NWSS site map, finds wastewater monitoring sites near your coordinates using a population/distance algorithm, and writes `location.json`. The poster reads this file to determine which states and sites to report on.

## Configuration

- `DISCORD_WEBHOOK_URL` (required for Discord posting): Webhook URL for your Discord channel. If not set, output prints to stdout only.
- `--detail` (optional): Control message verbosity. Choices: `low` (default), `medium`, `high`.

Example:
```bash
python post_to_discord.py --detail medium
```

## Data Sources

- **Wastewater (NWSS)**: Site-level viral activity levels, population-weighted across nearby sites, updated Wed/Thu (most current signal)
- **ED Visits (NSSP)**: Percentage of emergency department visits by state, reported weekly
- **Hospital Admissions (NHSN)**: Weekly new admissions per 100k population by state

See `DATA_SOURCES.md` for details on data definitions, calibration, and update cadence.

## Automation

The included GitHub Actions workflow (`.github/workflows/weekly-post.yml`) runs every Friday at 16:00 UTC, automatically posting to Discord. Set `DISCORD_WEBHOOK_URL` as a repository secret to enable.
