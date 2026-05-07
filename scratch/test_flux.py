import os
import requests
import base64
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("NVIDIA_API_KEY")
invoke_url = "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-schnell"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Accept": "application/json",
}
payload = {
    "prompt": "A technical drawing of a bridge",
    "width": 1024,
    "height": 1024,
    "seed": 0,
    "steps": 4
}
response = requests.post(invoke_url, headers=headers, json=payload)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"Keys in response: {list(data.keys())}")
    # Print first few chars of a possible image key
    if "image" in data:
        print(f"Image data (start): {data['image'][:50]}...")
else:
    print(f"Error: {response.text}")
