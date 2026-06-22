"""Probe NVIDIA API connectivity and video model wiring.

This script is intentionally standalone: it only needs NVIDIA-related
environment variables and a network connection.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys

import httpx
from dotenv import load_dotenv


DEFAULT_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_VIDEO_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
DEFAULT_TEXT_MODEL = "meta/llama-3.1-70b-instruct"
DEFAULT_SAMPLE_VIDEO = "https://assets.ngc.nvidia.com/products/api-catalog/active-speaker-detection/video_1.mp4"


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


async def _post(client: httpx.AsyncClient, url: str, api_key: str, body: dict) -> dict:
    response = await client.post(url, headers=_headers(api_key), json=body)
    response.raise_for_status()
    return response.json()


def _extract_message_text(payload: dict) -> str:
    choice = payload.get("choices", [{}])[0]
    message = choice.get("message", {})
    text = message.get("content") or message.get("reasoning") or choice.get("text") or ""
    if isinstance(text, list):
        return json.dumps(text, ensure_ascii=False)
    return str(text).strip()


async def main() -> int:
    parser = argparse.ArgumentParser(description="Probe NVIDIA chat and video APIs.")
    parser.add_argument("--video-url", default=DEFAULT_SAMPLE_VIDEO, help="Public mp4 URL for video understanding test.")
    parser.add_argument("--api-url", default=os.getenv("NVIDIA_API_BASE_URL", DEFAULT_API_URL))
    parser.add_argument("--video-model", default=os.getenv("NVIDIA_VIDEO_MODEL", DEFAULT_VIDEO_MODEL))
    parser.add_argument("--text-model", default=os.getenv("NVIDIA_TEXT_MODEL", DEFAULT_TEXT_MODEL))
    parser.add_argument("--base64", action="store_true", help="Also test base64 video payload by downloading the sample video.")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("NVIDIA_API_KEY", "").strip()
    if not api_key:
        print("NVIDIA_API_KEY is missing", file=sys.stderr)
        return 2

    async with httpx.AsyncClient(timeout=60) as client:
        print(f"API URL: {args.api_url}")
        print(f"Text model: {args.text_model}")
        print(f"Video model: {args.video_model}")

        text_body = {
            "model": args.text_model,
            "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
            "max_tokens": 16,
            "temperature": 0,
        }
        text_json = await _post(client, args.api_url, api_key, text_body)
        text_answer = _extract_message_text(text_json)
        print(f"Text test: {text_answer}")

        video_body = {
            "model": args.video_model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this video in one short sentence."},
                    {"type": "video_url", "video_url": {"url": args.video_url}},
                ],
            }],
            "max_tokens": 128,
            "temperature": 0.2,
            "mm_processor_kwargs": {"use_audio_in_video": True},
        }
        video_json = await _post(client, args.api_url, api_key, video_body)
        video_answer = _extract_message_text(video_json)
        if not video_answer:
            print("Video response JSON:")
            print(json.dumps(video_json, ensure_ascii=False, indent=2)[:4000])
            return 1
        print(f"Video-url test: {video_answer}")

        if args.base64:
            sample_bytes = (await client.get(args.video_url)).content
            b64 = base64.b64encode(sample_bytes).decode()
            base64_body = {
                "model": args.video_model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this video in one short sentence."},
                        {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{b64}"}},
                    ],
                }],
                "max_tokens": 128,
                "temperature": 0.2,
                "mm_processor_kwargs": {"use_audio_in_video": True},
            }
            base64_json = await _post(client, args.api_url, api_key, base64_body)
            base64_answer = _extract_message_text(base64_json)
            print(f"Video-base64 test: {base64_answer}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
