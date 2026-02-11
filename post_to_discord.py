import os
import requests


DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]


def fetch_data():
    """Fetch data from an external source. Replace with your actual data source."""
    # Example: response = requests.get("https://some-api.com/data")
    # return response.json()
    return {"message": "Hello from contagion-poster!"}


def format_message(data):
    """Format the fetched data into a Discord message. Replace with your actual formatting."""
    return data["message"]


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
    post_to_discord(message)


if __name__ == "__main__":
    main()
