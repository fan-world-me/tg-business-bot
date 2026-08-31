"""AI calls: Groq primary, NVIDIA fallback."""
import logging
from typing import Any

import httpx

from config import (
    GEMINI_API_KEY,
    GEMINI_VIDEO_MODEL,
    GROQ_API_KEY,
    GROQ_TEXT_MODELS,
    GROQ_VISION_MODELS,
    NVIDIA_API_KEY,
    MAX_TOKENS,
    NVIDIA_API_BASE_URL,
    NVIDIA_TEXT_MODELS,
    NVIDIA_VIDEO_MODELS,
    NVIDIA_VISION_MODELS,
)

logger = logging.getLogger(__name__)


class GeminiRateLimitError(RuntimeError):
    """Gemini returned 429 / RESOURCE_EXHAUSTED."""


async def _post(url: str, headers: dict, body: dict) -> str:
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
        payload = r.json()
        choice = payload["choices"][0]
        message = choice.get("message", {})
        text = message.get("content") or message.get("reasoning") or choice.get("text") or ""
        if isinstance(text, list):
            text = " ".join(
                part.get("text", "") for part in text if isinstance(part, dict)
            )
        return str(text).strip()


def _extract_http_error_text(resp: httpx.Response) -> str:
    try:
        payload = resp.json()
    except Exception:
        return resp.text.strip()
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("status") or payload).strip()
        return str(payload.get("message") or payload).strip()
    return str(payload).strip()


async def _run_chain(candidates: list[tuple[str, Any]]) -> str:
    """Try each (label, async_callable) in order; return first success, else raise last error."""
    last_exc: Exception | None = None
    for label, call in candidates:
        try:
            result = await call()
            logger.info("AI chain: %s succeeded", label)
            return result
        except Exception as exc:
            logger.warning("AI chain: %s failed (%s), trying next", label, exc)
            last_exc = exc
    raise last_exc or RuntimeError("No AI candidates configured")


def _groq_headers() -> dict:
    return {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}


def _nvidia_headers() -> dict:
    return {"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"}


async def _groq_chat_one(messages: list[dict], model: str) -> str:
    body = {"model": model, "messages": messages, "max_tokens": MAX_TOKENS, "temperature": 0.7}
    return await _post("https://api.groq.com/openai/v1/chat/completions", _groq_headers(), body)


async def _nvidia_chat_one(messages: list[dict], model: str) -> str:
    body = {"model": model, "messages": messages, "max_tokens": MAX_TOKENS, "temperature": 0.7}
    return await _post(NVIDIA_API_BASE_URL, _nvidia_headers(), body)


async def groq_chat(messages: list[dict], models: list[str] | None = None) -> str:
    """Try each configured Groq text model in order (primary, then backups)."""
    models = models or GROQ_TEXT_MODELS
    candidates = [(f"groq:{m}", lambda m=m: _groq_chat_one(messages, m)) for m in models]
    return await _run_chain(candidates)


async def nvidia_chat(messages: list[dict], models: list[str] | None = None) -> str:
    """Try each configured NVIDIA text model in order (primary, then backups)."""
    models = models or NVIDIA_TEXT_MODELS
    candidates = [(f"nvidia:{m}", lambda m=m: _nvidia_chat_one(messages, m)) for m in models]
    return await _run_chain(candidates)


async def nvidia_multimodal(
    messages: list[dict],
    models: list[str] | None = None,
    model: str | None = None,
    extra_body: dict[str, Any] | None = None,
) -> str:
    """Try each configured NVIDIA multimodal model in order.

    `model` (singular) is kept for backward compatibility with existing callers
    that pass one explicit model; `models` (list) lets a caller supply its own
    primary+backup chain. If neither is given, falls back to NVIDIA_VISION_MODELS.
    """
    if model is not None:
        models = [model]
    models = models or NVIDIA_VISION_MODELS

    async def _call(m: str) -> str:
        body: dict[str, Any] = {"model": m, "messages": messages, "max_tokens": MAX_TOKENS, "temperature": 0.2}
        if extra_body:
            body.update(extra_body)
        return await _post(NVIDIA_API_BASE_URL, _nvidia_headers(), body)

    candidates = [(f"nvidia-mm:{m}", lambda m=m: _call(m)) for m in models]
    return await _run_chain(candidates)


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


async def groq_vision(image_path: str, prompt: str = "Describe this image briefly.", models: list[str] | None = None) -> str:
    import base64
    ext = image_path.rsplit(".", 1)[-1].lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    messages = [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
    ]}]

    async def _call(m: str) -> str:
        body = {"model": m, "messages": messages, "max_tokens": MAX_TOKENS}
        return await _post("https://api.groq.com/openai/v1/chat/completions", _groq_headers(), body)

    models = models or GROQ_VISION_MODELS
    candidates = [(f"groq-vision:{m}", lambda m=m: _call(m)) for m in models]
    return await _run_chain(candidates)


async def gemini_youtube_video(url: str, prompt: str, model: str = GEMINI_VIDEO_MODEL) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    body = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"fileData": {"fileUri": url, "mimeType": "video/mp4"}},
            ]
        }]
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": GEMINI_API_KEY},
            headers={"Content-Type": "application/json"},
            json=body,
        )
        if resp.status_code == 429:
            raise GeminiRateLimitError(_extract_http_error_text(resp) or "Gemini rate limit reached")
        resp.raise_for_status()
        payload = resp.json()

    try:
        candidates = payload.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            texts = [p.get("text", "") for p in parts if "text" in p]
            result = " ".join(texts).strip()
            if result:
                return result
    except Exception as exc:
        logger.error("Gemini response parse error: %s — payload: %s", exc, str(payload)[:500])
    return str(payload).strip()
