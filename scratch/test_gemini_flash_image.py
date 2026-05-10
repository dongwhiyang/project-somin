"""
gemini-2.5-flash-image(Nano Banana 계열) 이미지 생성 스모크 테스트.
실행: 프로젝트 루트에서  python scratch/test_gemini_flash_image.py
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

MODEL = "gemini-2.5-flash-image"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"


def main() -> int:
    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not key:
        print("FAIL: GEMINI_API_KEY 또는 GOOGLE_API_KEY가 .env에 없습니다.")
        return 1

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "Photorealistic civil engineering construction site, "
                            "excavator and safety cones, wide angle, daylight, "
                            "no text, no letters, no watermark."
                        )
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
        },
    }

    print(f"요청 모델: {MODEL}")
    r = requests.post(API_URL, params={"key": key}, json=payload, timeout=120)
    if r.status_code != 200:
        print(f"FAIL HTTP {r.status_code}")
        print(r.text[:1200])
        return 1

    data = r.json()
    candidates = data.get("candidates") or []
    if not candidates:
        print("FAIL: candidates 없음")
        print(json.dumps(data, ensure_ascii=False)[:800])
        return 1

    parts = (candidates[0].get("content") or {}).get("parts") or []
    root = Path(__file__).resolve().parent.parent
    out_dir = root / "images"
    out_dir.mkdir(parents=True, exist_ok=True)

    saved = False
    for part in parts:
        inline = part.get("inlineData") or part.get("inline_data")
        if inline:
            raw_b64 = inline.get("data") or ""
            mime = (inline.get("mimeType") or inline.get("mime_type") or "image/png").lower()
            ext = ".jpg" if "jpeg" in mime or "jpg" in mime else ".png"
            out_path = out_dir / f"test_gemini_flash_image_{int(time.time())}{ext}"
            out_path.write_bytes(base64.b64decode(raw_b64))
            print(f"OK 이미지 저장: {out_path}")
            saved = True
        elif part.get("text"):
            t = part["text"].strip()
            if t:
                print(f"모델 텍스트(일부): {t[:400]}...")

    if not saved:
        print("FAIL: 응답에 inlineData 이미지 없음")
        print(json.dumps(data, ensure_ascii=False)[:1500])
        return 1

    print("테스트 성공.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
