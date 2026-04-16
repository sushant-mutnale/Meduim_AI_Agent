import matplotlib.pyplot as plt
import requests
import os
import uuid
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


class ChartAgent:
    def generate_chart(self, data_points: dict, title: str, xlabel: str, ylabel: str) -> str:
        """
        Generate a simple bar chart from a dictionary of category -> numeric value.
        Saves locally and returns the relative path.
        """
        os.makedirs("assets", exist_ok=True)
        filename = f"assets/chart_{uuid.uuid4().hex[:8]}.png"
        
        plt.figure(figsize=(10, 6))
        plt.bar(list(data_points.keys()), list(data_points.values()), color='skyblue')
        plt.title(title)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.tight_layout()
        plt.savefig(filename)
        plt.close()
        
        return filename


class VisualImageAgent:
    """
    Image generation using ImageRouter API (primary) with Google Gemini fallback.
    No OpenAI dependency required.
    """
    def generate_image(self, topic: str, core_insight: str) -> str:
        """
        Generates an editorial illustration via ImageRouter API.
        Falls back to Gemini if ImageRouter fails.
        """
        prompt = (
            f"Create a modern, high-quality, professional editorial illustration "
            f"representing the topic '{topic}'. "
            f"The core insight to visually communicate is: '{core_insight}'. "
            f"Style: Minimalist corporate tech aesthetic, smooth gradients, "
            f"no realistic human faces, isometric vector art or sleek 3D glassmorphism. "
            f"ABSOLUTELY NO TEXT OR WORDS in the image."
        )

        # Try ImageRouter first
        url = self._try_imagerouter(prompt)
        if url:
            return url

        # Fallback: Gemini image generation
        url = self._try_gemini(prompt)
        if url:
            return url

        return "failed to generate image: all providers exhausted"

    def _try_imagerouter(self, prompt: str) -> str:
        """Primary: ImageRouter API (OpenAI-compatible JSON endpoint)."""
        if not settings.IMAGEROUTER_API_KEY:
            return ""

        try:
            url = "https://api.imagerouter.io/v1/openai/images/generations"
            payload = {
                "prompt": prompt,
                "model": "openai/gpt-image-1",
                "quality": "auto",
                "size": "auto",
                "response_format": "url",
                "output_format": "webp",
            }
            headers = {
                "Authorization": f"Bearer {settings.IMAGEROUTER_API_KEY}",
                "Content-Type": "application/json",
            }

            response = requests.post(url, json=payload, headers=headers, timeout=30)

            if response.status_code in [200, 201]:
                data = response.json()
                image_data = data.get("data", [])
                if image_data:
                    return image_data[0].get("url", "")
            
            logger.warning(f"ImageRouter failed: {response.status_code} - {response.text[:200]}")
            return ""
        except Exception as e:
            logger.warning(f"ImageRouter error: {e}")
            return ""

    def _try_gemini(self, prompt: str) -> str:
        """Fallback: Google Gemini image generation."""
        if not settings.GEMINI_API_KEY:
            return ""

        try:
            from google import genai

            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model="gemini-2.0-flash-preview-image-generation",
                contents=[prompt],
            )

            # Save generated image locally
            os.makedirs("assets", exist_ok=True)
            for part in response.parts:
                if part.inline_data is not None:
                    image = part.as_image()
                    filename = f"assets/gemini_{uuid.uuid4().hex[:8]}.png"
                    image.save(filename)
                    return filename

            return ""
        except Exception as e:
            logger.warning(f"Gemini image generation failed: {e}")
            return ""
