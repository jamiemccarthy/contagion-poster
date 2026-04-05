# Contagion Poster

A Python script that posts weekly summaries of airborne respiratory illness activity in the Metro DC area to Discord.

The script monitors three CDC data sources—wastewater, ED visits, and hospital admissions—for COVID, flu, and RSV. It classifies illness activity into concern levels (Low, Moderate, High, Very High) and posts a formatted summary to a Discord channel every Friday.

## Quick Start

```bash
# Set up venv
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the script
DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/YOUR_SECRET' python post_to_discord.py
```

## Configuration

- `DISCORD_WEBHOOK_URL` (required for Discord posting): Webhook URL for your Discord channel. If not set, output prints to stdout only.
- `--detail` (optional): Control message verbosity. Choices: `low` (default), `medium`, `high`.

Example:
```bash
python post_to_discord.py --detail medium
```

## Data Sources

- **Wastewater (NWSS)**: Viral activity levels, updated Fridays (most current signal)
- **ED Visits (NSSP)**: Percentage of emergency department visits, reported weekly
- **Hospital Admissions (NHSN)**: Weekly new admissions per 100k population

See `DATA_SOURCES.md` for details on data definitions, calibration, and update cadence.

## Automation

The included GitHub Actions workflow (`.github/workflows/weekly-post.yml`) runs every Friday at 16:00 UTC, automatically posting to Discord. Set `DISCORD_WEBHOOK_URL` as a repository secret to enable.
