import base64
import os
import requests
from typing import List, Optional
from schema import Photo

class TinderVision:
    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url.rstrip("/")
        self.model = os.getenv("VISION_MODEL", "moondream")

    def describe_photo(self, photo: Photo) -> Optional[str]:
        # Step 1: Get image bytes
        image_bytes = None
        if photo.path and os.path.exists(photo.path):
            try:
                with open(photo.path, "rb") as f:
                    image_bytes = f.read()
            except Exception as e:
                print(f"[vision] Failed to read local photo {photo.path}: {e}")
        elif photo.url:
            try:
                resp = requests.get(photo.url, timeout=10)
                if resp.status_code == 200:
                    image_bytes = resp.content
                else:
                    print(f"[vision] Failed to download {photo.url}, status code: {resp.status_code}")
            except Exception as e:
                print(f"[vision] Exception downloading photo {photo.url}: {e}")

        if not image_bytes:
            print(f"[vision] No image bytes available for photo {photo.id}")
            # Offline test mode fallback
            if os.getenv("TESTING_OFFLINE") == "true":
                return f"Mock description for photo {photo.id}"
            return None

        # Step 2: Base64 encode
        base64_str = base64.b64encode(image_bytes).decode("utf-8")

        prompt = (
            "Describe this dating profile photo in rich detail. "
            "Identify and describe the background setting, environment, and setting location. "
            "Describe the person's clothing style, the specific garments worn, their colors, items, and fit. "
            "Describe their facial expression, smile, eye contact, hair style, facial hair (beard, mustache, or clean-shaven), grooming, and face features. "
            "Describe their body structure, posture, posing, body language, and image framing (headshot, torso-up, full-body). "
            "Mention any accessories like glasses, watches, hats, or jewelry. "
            "Estimate the image quality and resolution (clear, high-res, blurry, original, or screenshot). "
            "Be extremely objective, thorough, descriptive, and provide a detailed multi-paragraph description."
        )

        # Step 3: Check vision backend preference (defaults to gemini if key is present, else ollama)
        vision_backend = os.getenv("VISION_BACKEND", "gemini" if os.getenv("GEMINI_API_KEY") else "ollama").lower()
        if vision_backend == "gemini":
            gemini_key = os.getenv("GEMINI_API_KEY")
            if gemini_key:
                # Determine mime type from photo.url or path (default to image/jpeg)
                mime_type = "image/jpeg"
                test_target = (photo.url or photo.path or "").lower()
                if ".png" in test_target:
                    mime_type = "image/png"
                elif ".webp" in test_target:
                    mime_type = "image/webp"

                print(f"[vision] Calling Google Gemini API (gemini-2.5-flash) for photo {photo.id}")
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
                    payload = {
                        "contents": [
                            {
                                "parts": [
                                    {
                                        "inline_data": {
                                            "mime_type": mime_type,
                                            "data": base64_str
                                        }
                                    },
                                    {
                                        "text": prompt
                                    }
                                ]
                            }
                        ]
                    }
                    resp = requests.post(url, json=payload, timeout=30)
                    if resp.status_code == 200:
                        result = resp.json()
                        candidates = result.get("candidates", [])
                        if candidates:
                            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            if text:
                                return text.strip()
                        print(f"[vision] Gemini returned empty/unexpected candidates payload: {result}")
                    else:
                        print(f"[vision] Gemini API returned status {resp.status_code}: {resp.text}")
                except Exception as e:
                    print(f"[vision] Exception calling Gemini: {e}")
                print("[vision] Gemini failed or returned invalid response. Falling back to local Ollama...")

        # Step 4: Call local Ollama vision model (fallback)
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "images": [base64_str],
                    "stream": False
                },
                timeout=120
            )
            if resp.status_code == 200:
                result = resp.json()
                return result.get("response", "").strip()
            else:
                print(f"[vision] Ollama returned status {resp.status_code}: {resp.text}")
                if os.getenv("TESTING_OFFLINE") == "true":
                    return f"Mock description for photo {photo.id}"
                return None
        except Exception as e:
            print(f"[vision] Exception calling Ollama at {self.ollama_url}: {e}")
            if os.getenv("TESTING_OFFLINE") == "true":
                return f"Mock description for photo {photo.id}"
            return None

    def describe_photos(self, photos: List[Photo]) -> List[Photo]:
        updated_photos = []
        for photo in photos:
            if photo.description:
                # Already described
                updated_photos.append(photo)
                continue
            
            print(f"[vision] Analyzing photo {photo.id}...")
            desc = self.describe_photo(photo)
            if desc:
                photo.description = desc
            updated_photos.append(photo)
        return updated_photos
