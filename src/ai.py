"""AI calls: Groq primary, NVIDIA fallback."""
import logging

import httpx

from config import GROQ_API_KEY, NVIDIA_API_KEY, MAX_TOKENS

logger = logging.getLogger(__name__)


async def _post(url: str, headers: dict, body: dict) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


def _groq_headers() -> dict:
    return {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}


def _nvidia_headers() -> dict:
    return {"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"}


async def groq_chat(messages: list[dict], model: str = "llama-3.3-70b-versatile") -> str:
    body = {"model": model, "messages": messages, "max_tokens": MAX_TOKENS, "temperature": 0.7}
    return await _post("https://api.groq.com/openai/v1/chat/completions", _groq_headers(), body)


async def nvidia_chat(messages: list[dict], model: str = "meta/llama-3.1-70b-instruct") -> str:
    body = {"model": model, "messages": messages, "max_tokens": MAX_TOKENS, "temperature": 0.7}
    return await _post("https://integrate.api.nvidia.com/v1/chat/completions", _nvidia_headers(), body)


async def groq_whisper(audio_path: str) -> str:
    with open(audio_path, "rb") as f:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                files={"file": f},
                data={"model": "whisper-large-v3-turbo", "response_format": "text"},
            )
            r.raise_for_status()
            return r.text.strip()


async def groq_vision(image_path: str, prompt: str = "Describe this image briefly.") -> str:
    import base64
    ext = image_path.rsplit(".", 1)[-1].lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    body = {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}],
        "max_tokens": MAX_TOKENS,
    }
    return await _post("https://api.groq.com/openai/v1/chat/completions", _groq_headers(), body)
