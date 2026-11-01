"""Extremely simple OpenRouter API client."""
import requests
import json
from typing import Optional, Dict, List
from services.ai_setup_api import get_ai_setup, DEFAULT_AI_URL, DEFAULT_AI_MODEL


def _get_ai_config() -> Dict[str, str]:
    setup = get_ai_setup()
    api_url = (setup.get("api_url") or "").strip() or DEFAULT_AI_URL
    api_key = (setup.get("api_key") or "").strip()
    model = (setup.get("model") or "").strip() or DEFAULT_AI_MODEL
    return {"api_url": api_url, "api_key": api_key, "model": model}


def _parse_candidates(value: str, default_value: Optional[str] = None) -> List[str]:
    raw = (value or "").replace("\n", ",").replace(";", ",")
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if parts:
        return parts
    if default_value:
        return [default_value]
    return []


def ask(prompt: str, model: Optional[str] = None) -> str:
    """
    Sends a simple text prompt to OpenRouter and returns the string response.
    
    Args:
        prompt: The text you want to send to the AI.
        model: The model to use (defaults to a free Mistral model).
    """
    cfg = _get_ai_config()
    selected_model = (model or "").strip() or cfg["model"]
    api_urls = _parse_candidates(cfg["api_url"], DEFAULT_AI_URL)
    api_keys = _parse_candidates(cfg["api_key"])
    models = _parse_candidates(selected_model, DEFAULT_AI_MODEL)

    if not api_keys:
        raise RuntimeError("Please set your API_KEY.")

    attempts = max(len(api_urls), len(api_keys), len(models))
    errors: List[str] = []

    for idx in range(attempts):
        api_url = api_urls[min(idx, len(api_urls) - 1)]
        api_key = api_keys[min(idx, len(api_keys) - 1)]
        current_model = models[min(idx, len(models) - 1)]

        try:
            response = requests.post(
                url=api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                data=json.dumps({
                    "model": current_model,
                    "stream": False,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt or "Please response 'Something went wrong' if prompt is empty."
                        }
                    ],
                    "temperature": 0,
                    "max_tokens": -1,
                    "seed": 0,
                    "top_p": 1
                }),
                timeout=30,
            )

            if not response.ok:
                errors.append(
                    f"attempt {idx + 1} failed ({response.status_code}) at {api_url}: {response.text[:200]}"
                )
                continue

            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                errors.append(f"attempt {idx + 1} returned empty content at {api_url}")
                continue
            return content
        except Exception as e:
            errors.append(f"attempt {idx + 1} exception at {api_url}: {str(e)}")

    raise RuntimeError("All AI API attempts failed. " + " | ".join(errors))