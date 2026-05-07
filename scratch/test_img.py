import os
import requests
import base64
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("NVIDIA_API_KEY")
invoke_url = "https://integrate.api.nvidia.com/v1/images/generations"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Accept": "application/json",
}
payload = {
    "model": "stabilityai/stable-diffusion-xl-base-1.0",
    "prompt": "A simple house",
    "response_format": "b64_json"
}
response = requests.post(invoke_url, headers=headers, json=payload)
print(response.status_code)
print(response.text[:500])
