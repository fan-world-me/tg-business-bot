import asyncio
import base64
import logging
import os
import tempfile
from typing import Optional

from aiogram import Bot
from aiogram.types import Message

import content_handler as content_mod
from ai import groq_whisper, groq_vision, nvidia_multimodal
from config import MAX_FILE_MB, MAX_VIDEO_MB, MAX_DOC_MB, NVIDIA_VIDEO_MODEL

logger = logging.getLogger(__name__)

VIDEO_ANALYSIS_SEMAPHORE = asyncio.Semaphore(int(os.getenv("VIDEO_ANALYSIS_CONCURRENCY", "1")))


def _over_limit(size: int | None, limit_mb: int) -> bool:
    return bool(size and size > limit_mb * 1024 * 1024)


def _doc_kind(filename: str | None, mime_type: str | None) -> str | None:
    if filename:
        suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        if suffix in {"pdf", "docx", "pptx", "xlsx", "zip"}:
            return suffix
        if suffix in {
            "py", "js", "ts", "tsx", "jsx", "go", "rs", "java", "kt", "c", "h",
            "cpp", "hpp", "cs", "php", "rb", "swift", "sh", "bash", "ps1", "sql",
            "json", "yaml", "yml", "toml", "ini", "cfg", "md", "txt", "html", "css",
            "scss", "xml",
        } or filename.lower() == "dockerfile" or filename.lower().endswith(".dockerfile"):
            return "code"
    if mime_type:
        if mime_type == "application/pdf":
            return "pdf"
        if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            return "docx"
        if mime_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
            return "pptx"
        if mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            return "xlsx"
        if mime_type == "application/zip":
            return "zip"
        if mime_type.startswith("text/") or mime_type in {"application/json", "application/xml", "text/csv"}:
            return "code"
    return None


def _unlink(*paths: str) -> None:
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.unlink(p)
        except OSError:
            pass


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
        return await nvidia_multimodal(messages, model="microsoft/phi-3.5-vision-instruct")


async def _nvidia_video(video_path: str, prompt: str, use_audio: bool = True) -> str:
    with open(video_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{b64}"}},
        ],
    }]
    extra_body = {"mm_processor_kwargs": {"use_audio_in_video": use_audio}}
    return await nvidia_multimodal(messages, model=NVIDIA_VIDEO_MODEL, extra_body=extra_body)


async def _analyze_impl(message: Message, bot: Bot) -> Optional[str]:
    m = message

    if m.photo:
        if _over_limit(m.photo[-1].file_size, MAX_FILE_MB):
            return f"[Photo too large: {m.photo[-1].file_size / 1024 / 1024:.1f} MB]"
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
        if _over_limit(m.sticker.file_size, MAX_FILE_MB):
            return f"[Sticker too large: {m.sticker.file_size / 1024 / 1024:.1f} MB]"
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
        try:
            await bot.download(m.animation.file_id, destination=path)
            async with VIDEO_ANALYSIS_SEMAPHORE:
                return await _nvidia_video(path, "Describe this GIF/animation briefly.", use_audio=False)
        except Exception as exc:
            logger.error("GIF analysis failed: %s", exc)
            return None
        finally:
            _unlink(path)

    if m.voice:
        if _over_limit(m.voice.file_size, MAX_FILE_MB):
            return f"[Voice too large: {m.voice.file_size / 1024 / 1024:.1f} MB]"
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
        if _over_limit(m.video_note.file_size, MAX_VIDEO_MB):
            return f"[Video note too large: {m.video_note.file_size / 1024 / 1024:.1f} MB]"
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as f:
            video = f.name
        try:
            await bot.download(m.video_note.file_id, destination=video)
            async with VIDEO_ANALYSIS_SEMAPHORE:
                return await _nvidia_video(
                    video,
                    "Describe this Telegram video note briefly. Include any speech you can understand.",
                    use_audio=True,
                )
        except Exception as exc:
            logger.error("Video note analysis failed: %s", exc)
            return None
        finally:
            _unlink(video)

    if m.video or (m.document and (m.document.mime_type or "").startswith("video/")):
        obj = m.video or m.document
        logger.info("Video received: size=%s duration=%s", obj.file_size, getattr(obj, "duration", None))
        if (obj.file_size or 0) > MAX_VIDEO_MB * 1024 * 1024:
            return f"[Video too large: {obj.file_size / 1024 / 1024:.1f} MB]"
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as f:
            video = f.name
        try:
            logger.info("Downloading video...")
            await bot.download(obj.file_id, destination=video)
            actual_size = os.path.getsize(video)
            logger.info("Video downloaded: %d bytes (expected %d)", actual_size, obj.file_size)
            if actual_size == 0:
                return "[Video download failed - empty file]"
            async with VIDEO_ANALYSIS_SEMAPHORE:
                return await _nvidia_video(
                    video,
                    "Describe this video. Summarize the main action, objects, and any speech you can understand.",
                    use_audio=True,
                )
        except Exception as exc:
            logger.error("Video analysis failed: %s", exc)
            return None
        finally:
            _unlink(video)

    if m.document and (m.document.mime_type or "").startswith("image/"):
        if _over_limit(m.document.file_size, MAX_FILE_MB):
            return f"[Image document too large: {m.document.file_size / 1024 / 1024:.1f} MB]"
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

    if m.document:
        kind = _doc_kind(m.document.file_name, m.document.mime_type)
        if kind:
            if _over_limit(m.document.file_size, MAX_DOC_MB):
                return f"[Document too large: {m.document.file_size / 1024 / 1024:.1f} MB]"
            suffix = m.document.file_name.rsplit(".", 1)[-1].lower() if m.document.file_name and "." in m.document.file_name else kind
            if suffix == "dockerfile":
                suffix = "txt"
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{suffix if suffix not in {'pdf', 'docx', 'pptx', 'xlsx', 'zip'} else suffix}") as f:
                path = f.name
            try:
                await bot.download(m.document.file_id, destination=path)
                return await content_mod.analyze_file(path, m.document.file_name, m.document.mime_type)
            except Exception as exc:
                logger.error("Document analysis failed: %s", exc)
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
