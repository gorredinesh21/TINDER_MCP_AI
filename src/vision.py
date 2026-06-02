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

        # Step 3: Call local Ollama vision model
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
