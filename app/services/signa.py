import os

import requests
from dotenv import load_dotenv

BASE_URL = "https://app.getsigna.ai"

load_dotenv()
SIGNA_KEY = os.getenv("SIGNA_KEY")
headers = {"Authorization": f"Bearer {SIGNA_KEY}"}


def signal_request(ticker: str):
    endpoint = f"/api/v1/signal?sym={ticker}"
    url = BASE_URL + endpoint

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return None


def analysis_request(ticker: str):
    response = requests.get(
        f"{BASE_URL}/api/v1/analysis?ticker={ticker}", headers=headers
    )
    return response.json()


if __name__ == "__main__":
    ticker = "AAPL"
    signal_data = analysis_request(ticker)
    print(signal_data)
