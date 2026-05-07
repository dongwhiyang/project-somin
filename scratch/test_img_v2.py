import os
import requests
import base64
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("NVIDIA_API_KEY")
# Testing the 'Hosted' style URL
invoke_url = "https://ai.api.nvidia.com/v1/genai/stabilityai/stable-diffusion-xl"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Accept": "application/json",
}
payload = {
    "prompt": "A futuristic city in technical drawing style",
    "cfg_scale": 7,
    "sampler": "K_EULER_ANCESTRAL",
    "steps": 30,
    "seed": 0
}
response = requests.post(invoke_url, headers=headers, json=payload)
print(f"Status: {response.status_code}")
print(f"Response: {response.text[:500]}")
