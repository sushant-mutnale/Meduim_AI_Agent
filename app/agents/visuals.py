import matplotlib.pyplot as plt
from openai import OpenAI
import os
import uuid
from app.core.config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

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
    def generate_image(self, topic: str, core_insight: str) -> str:
        """
        Generates an image via OpenAI DALL-E and returns the URL.
        """
        # A powerful, specific prompt ensuring high-quality editorial aesthetic
        prompt = f"""
        Create a modern, high-quality, professional editorial illustration representing the topic '{topic}'.
        The core insight to visually communicate is: '{core_insight}'.
        Style constraints: Minimalist corporate tech aesthetic, smooth gradients, no realistic human faces, isometric vector art style or sleek 3D glassmorphism.
        ABSOLUTELY NO TEXT OR WORDS in the image.
        """
        try:
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )
            return response.data[0].url
        except Exception as e:
            return f"failed to generate image: {str(e)}"
