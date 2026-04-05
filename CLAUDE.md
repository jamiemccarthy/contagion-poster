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

# Run the script
DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/YOUR_SECRET' python post_to_discord.py
```

## Discord

- Webhook URL: `https://discord.com/api/webhooks/YOUR_SECRET`
- Webhooks are channel-specific — no separate guild/channel ID needed
- The webhook URL is the only secret; it must be stored as `DISCORD_WEBHOOK_URL` in GitHub repo secrets for the Actions workflow

## Architecture

Single-file Python script (`post_to_discord.py`) with three-stage pipeline:
1. `fetch_data()` - Retrieves data from external sources
2. `format_message()` - Transforms data into Discord message content
3. `post_to_discord()` - Sends message via Discord webhook

GitHub Actions workflow (`.github/workflows/weekly-post.yml`) runs every Friday at 16:00 UTC (noon Eastern), after CDC NHSN data typically publishes in the morning (observed ~14:00 UTC, but timing may vary).

See `DATA_SOURCES.md` for data source details.
