import asyncio
import base64
import logging
import os
import shutil
import tempfile
from typing import Optional

from aiogram import Bot
from aiogram.types import Message

from ai import groq_whisper, groq_vision, nvidia_chat
from config import MAX_FILE_MB

logger = logging.getLogger(__name__)


def _unlink(*paths: str) -> None:
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.unlink(p)
        except OSError:
            pass


async def _ffmpeg(args: list[str]) -> bool:
    if not shutil.which("ffmpeg"):
        logger.error("ffmpeg not found")
        return False
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        if proc.returncode != 0:
            logger.warning("ffmpeg failed: %s", stderr.decode()[:200] if stderr else "no stderr")
        return proc.returncode == 0
    except asyncio.TimeoutError:
        logger.error("ffmpeg timeout")
        return False
    except Exception as exc:
        logger.error("ffmpeg error: %s", exc)
        return False


async def _vision(image_path: str, prompt: str) -> str:
    try:
        return await groq_vision(image_path, prompt)
    except Exception as exc:
        logger.warning("Groq vision failed (%s), trying NVIDIA", exc)
        ext = image_path.rsplit(".", 1)[-1].lower()
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        messages = [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}]
        return await nvidia_chat(messages, model="microsoft/phi-3.5-vision-instruct")


async def _extract_frames(video: str) -> list[str]:
    frames = []
    for i, offset in enumerate(["00:00:01", "00:00:03"]):
        path = f"{video}_frame{i}.jpg"
        if await _ffmpeg(["-ss", offset, "-i", video, "-vframes", "1", "-q:v", "2", path]):
            frames.append(path)
    if not frames:
        path = f"{video}_frame0.jpg"
        if await _ffmpeg(["-i", video, "-vframes", "1", "-q:v", "2", path]):
            frames.append(path)
    return frames


async def _analyze_impl(message: Message, bot: Bot) -> Optional[str]:
    m = message

    if m.photo:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f:
            path = f.name
        try:
            await bot.download(m.photo[-1].file_id, destination=path)
            return await _vision(path, "Describe this image briefly (2-3 sentences).")
        except Exception as exc:
            logger.error("Photo analysis failed: %s", exc)
            return None
        finally:
            _unlink(path)

    if m.sticker:
        if m.sticker.is_animated or m.sticker.is_video:
            return f"[Sticker: {m.sticker.emoji or ''}]"
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webp") as f:
            path = f.name
        try:
            await bot.download(m.sticker.file_id, destination=path)
            return await _vision(path, "This is a Telegram sticker. Describe it briefly.")
        except Exception as exc:
            logger.error("Sticker analysis failed: %s", exc)
            return f"[Sticker: {m.sticker.emoji or ''}]"
        finally:
            _unlink(path)

    if m.animation:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as f:
            path = f.name
        frame = path + ".jpg"
        try:
            await bot.download(m.animation.file_id, destination=path)
            if await _ffmpeg(["-ss", "0", "-i", path, "-vframes", "1", "-q:v", "2", frame]):
                return await _vision(frame, "Describe this GIF/animation briefly.")
            return "[GIF]"
        except Exception as exc:
            logger.error("GIF analysis failed: %s", exc)
            return "[GIF]"
        finally:
            _unlink(path, frame)

    if m.voice:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as f:
            path = f.name
        try:
            await bot.download(m.voice.file_id, destination=path)
            return await groq_whisper(path)
        except Exception as exc:
            logger.error("Whisper failed: %s", exc)
            return None
        finally:
            _unlink(path)

    if m.video_note:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as f:
            video = f.name
        audio = video + ".wav"
        frames: list[str] = []
        try:
            await bot.download(m.video_note.file_id, destination=video)
            parts: list[str] = []
            frames = await _extract_frames(video)
            if frames:
                try:
                    descs = [await _vision(fr, "Describe this video note frame briefly.") for fr in frames]
                    parts.append("[Visual] " + " | ".join(descs))
                except Exception as exc:
                    logger.warning("Vision on video note failed: %s", exc)
            if await _ffmpeg(["-i", video, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio]):
                try:
                    t = await groq_whisper(audio)
                    if t:
                        parts.append("[Speech] " + t)
                except Exception as exc:
                    logger.warning("Whisper on video note failed: %s", exc)
            return "\n".join(parts) if parts else "[Video note — no analysis]"
        except Exception as exc:
            logger.error("Video note analysis failed: %s", exc)
            return None
        finally:
            _unlink(video, audio, *frames)

    if m.video or (m.document and (m.document.mime_type or "").startswith("video/")):
        obj = m.video or m.document
        logger.info("Video received: size=%s duration=%s", obj.file_size, getattr(obj, "duration", None))
        if (obj.file_size or 0) > MAX_FILE_MB * 1024 * 1024:
            return f"[Video too large: {obj.file_size / 1024 / 1024:.1f} MB]"
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as f:
            video = f.name
        audio = video + ".wav"
        frames = []
        try:
            logger.info("Downloading video...")
            await bot.download(obj.file_id, destination=video)
            actual_size = os.path.getsize(video)
            logger.info("Video downloaded: %d bytes (expected %d)", actual_size, obj.file_size)
            if actual_size == 0:
                return "[Video download failed — empty file]"
            
            # Try frames with shorter timeout
            parts = []
            try:
                frames = await asyncio.wait_for(_extract_frames(video), timeout=30)
                logger.info("Extracted %d frames", len(frames))
            except asyncio.TimeoutError:
                logger.warning("Frame extraction timed out, skipping visual analysis")
                frames = []
            if frames:
                try:
                    descs = [await _vision(fr, "Describe this video frame briefly.") for fr in frames]
                    parts.append("[Visual] " + " | ".join(descs))
                except Exception as exc:
                    logger.warning("Vision on video frame failed: %s", exc)
            logger.info("Extracting audio...")
            if await _ffmpeg(["-i", video, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio]):
                logger.info("Transcribing audio...")
                try:
                    t = await groq_whisper(audio)
                    if t:
                        parts.append("[Speech] " + t)
                except Exception as exc:
                    logger.warning("Whisper on video failed: %s", exc)
            logger.info("Video analysis done: %s", parts)
            if parts:
                return "\n".join(parts)
            dur = getattr(m.video, "duration", None)
            return f"[Video {dur}s — no analysis]" if dur else "[Video — no analysis]"
        except Exception as exc:
            logger.error("Video analysis failed: %s", exc)
            return None
        finally:
            _unlink(video, audio, *frames)

    if m.document and (m.document.mime_type or "").startswith("image/"):
        ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(m.document.mime_type, ".jpg")
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as f:
            path = f.name
        try:
            await bot.download(m.document.file_id, destination=path)
            return await _vision(path, "Describe this image briefly.")
        except Exception as exc:
            logger.error("Document image analysis failed: %s", exc)
            return None
        finally:
            _unlink(path)

    return None


async def analyze(message: Message, bot: Bot) -> Optional[str]:
    """Public wrapper used by bot.py.

    The handler code expects media_handler.analyze(), so keep this stable even
    if the implementation is refactored internally.
    """
    return await _analyze_impl(message, bot)
