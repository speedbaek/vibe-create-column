import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("ANTHROPIC_API_KEY")

url = "https://api.anthropic.com/v1/models"
headers = {
    "x-api-key": api_key,
    "anthropic-version": "2023-06-01"
}

try:
    response = requests.get(url, headers=headers)
    models = response.json()
    with open("models.json", "w", encoding="utf-8") as f:
        json.dump(models, f, indent=4)
    print("Models saved to models.json")
except Exception as e:
    print(f"Error: {e}")
