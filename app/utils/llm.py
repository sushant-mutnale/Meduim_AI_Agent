from openai import OpenAI
import json
import re
from app.core.config import settings

client = OpenAI(
    api_key=settings.OPENROUTER_API_KEY,
    base_url=settings.OPENROUTER_BASE_URL
)

def extract_json(text: str) -> dict:
    """Attempts to robustly parse JSON from an LLM string that might include markdown block formatting."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON block inside markdown
        match = re.search(r'```(?:json)?\s*(\{.*\}|\[.*\])\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Last ditch effort on curly braces
        match = re.search(r'(\{.*\})', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
                
        raise ValueError(f"Could not parse JSON from string: {text[:100]}...")

def generate_structured_response(system_prompt: str, user_prompt: str, model: str = None) -> dict:
    model = model or settings.DEFAULT_MODEL
    
    # Enforce strict JSON direction in the system prompt
    strict_sys = system_prompt + "\n\nCRITICAL: You must respond ONLY with valid JSON. Do not include markdown blocks or any other commentary."
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": strict_sys},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
        # OpenRouter doesn't uniformly support response_format={"type":"json_object"} on all models, 
        # so we strip it internally via regex fallback if it fails.
    )
    content = response.choices[0].message.content
    return extract_json(content)

def run_llm(system_prompt: str, user_prompt: str, model: str = None, temperature: float = 0.7) -> str:
    model = model or settings.DEFAULT_MODEL
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=temperature
    )
    return response.choices[0].message.content
