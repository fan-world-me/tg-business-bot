"""Lightweight text extraction for URLs, documents, archives, and code files."""
from __future__ import annotations

import html
import logging
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from docx import Document
from openpyxl import load_workbook
from pptx import Presentation
from pypdf import PdfReader

from ai import GeminiRateLimitError, gemini_youtube_video
from config import (
    MAX_ARCHIVE_FILES,
    MAX_ARCHIVE_MB,
    MAX_DOC_MB,
    MAX_TEXT_CHARS,
    MAX_URL_MB,
)

logger = logging.getLogger(__name__)

URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
YOUTUBE_RE = re.compile(
    r"^https?://(?:(?:www\.|m\.)?youtube\.com/watch\?(?:[^#\s]*&)?v=[^&\s#]+"
    r"|youtu\.be/[^?\s#]+"
    r"|(?:www\.)?youtube\.com/shorts/[^?\s#]+"
    r"|(?:www\.)?youtube\.com/live/[^?\s#]+)",
    re.IGNORECASE,
)
GITHUB_BLOB_RE = re.compile(
    r"https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)",
    re.IGNORECASE,
)
GITHUB_REPO_RE = re.compile(
    r"https://github\.com/([^/\s?#]+)/([^/\s?#]+)/?(?:[?#].*)?$",
    re.IGNORECASE,
)
NEWS_KEYWORDS_RE = re.compile(
    r"\b(сталось|загинул|вибух|атака|новини|breaking|explosion|attack|killed|"
    r"arrested|заарештував|повідомляє|повідомляють|джерела|источники|виявилось|"
    r"выяснилось|за даними|по данным|офіційно|официально|стало відомо|стало известно|"
    r"оголошено|объявлено|розслідування|расследование|підтвердили|подтвердили)\b",
    re.IGNORECASE,
)
CODE_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".c", ".h",
    ".cpp", ".hpp", ".cs", ".php", ".rb", ".swift", ".sh", ".bash", ".ps1", ".sql",
    ".json", ".jsonl", ".ndjson", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".md",
    ".txt", ".log", ".html", ".htm", ".css", ".scss", ".xml", ".dockerfile",
    ".gitignore",
    # additional languages
    ".dart", ".lua", ".r", ".jl", ".ex", ".exs", ".zig", ".m", ".mm",
    ".vue", ".svelte", ".astro", ".elm", ".clj", ".cljs", ".erl", ".hrl",
    ".hs", ".ml", ".mli", ".fs", ".fsx", ".v", ".vhd", ".vhdl",
    ".tf", ".hcl", ".nix", ".proto", ".graphql", ".gql",
}
DOC_EXTS = {".pdf", ".docx", ".pptx", ".xlsx", ".zip"}
TEXT_MIME_PREFIXES = ("text/",)
STRUCTURED_MIME = {
    "application/json",
    "application/xml",
    "text/csv",
    "application/csv",
    "application/yaml",
}


def _limit_text(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    text = re.sub(r"\s+\n", "\n", text).strip()
    return text[:limit]


def _suffix_from_name(name: str | None) -> str:
    if not name:
        return ""
    low = name.lower()
    if low.endswith(".dockerfile"):
        return ".dockerfile"
    return Path(low).suffix


def _is_probably_text(data: bytes) -> bool:
    if not data:
        return True
    sample = data[:4096]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _decode_bytes(data: bytes) -> str:
    for enc in ("utf-8", "utf-16", "cp1251", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _text_from_pdf(path: str) -> str:
    reader = PdfReader(path)
    pages = []
    for i, page in enumerate(reader.pages):
        if i >= 20:
            break
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(pages)


def _text_from_docx(path: str) -> str:
    doc = Document(path)
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            vals = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if vals:
                parts.append(" | ".join(vals))
    return "\n".join(parts)


def _text_from_pptx(path: str) -> str:
    prs = Presentation(path)
    parts = []
    for idx, slide in enumerate(prs.slides):
        if idx >= 30:
            break
        slide_bits = []
        for shape in slide.shapes:
            text = getattr(shape, "text", "").strip()
            if text:
                slide_bits.append(text)
        if slide_bits:
            parts.append(f"Slide {idx + 1}:\n" + "\n".join(slide_bits))
    return "\n\n".join(parts)


def _text_from_xlsx(path: str) -> str:
    parts = []
    with load_workbook(path, read_only=True, data_only=True) as wb:
        for ws in wb.worksheets[:5]:
            rows = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= 80:
                    break
                vals = [str(v) for v in row if v is not None and str(v).strip()]
                if vals:
                    rows.append(" | ".join(vals))
            if rows:
                parts.append(f"Sheet {ws.title}:\n" + "\n".join(rows))
    return "\n\n".join(parts)


def _text_from_blend(path: str) -> str:
    """Extract basic metadata from a Blender .blend file.

    Compression:
      uncompressed  — magic starts with BLENDER  (Blender 1.x–2.x, or manually saved)
      gzip          — magic 1f 8b                (Blender 2.5–3.x default)
      zstd          — magic 28 b5 2f fd          (Blender 4.0+ default)

    Header layout:
      Old (<=3.x): BLENDER + ptr(1) + endian(1) + ver(3)        e.g. BLENDER-v410
      New (4.0+):  BLENDER + fmtver(2) + ptr(1) + pad(2) + endian(1) + ver(4)
                                                                  e.g. BLENDER17-01v0500

    File-format-version → Blender release mapping (new format only):
      See: https://wiki.blender.org/wiki/Source/Architecture/blendfile_format
    """
    import gzip

    ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
    GZIP_MAGIC = b"\x1f\x8b"
    BLEND_MAGIC = b"BLENDER"

    # file-format-version (2-digit str) → human release label
    FMT_VER_MAP: dict[str, str] = {
        "01": "1.x",
        "02": "2.x",
        "03": "2.5x",
        "04": "2.6x",
        "05": "2.7x",
        "06": "2.79",
        "07": "2.80–2.83",
        "08": "2.90–2.93",
        "09": "3.0–3.1",
        "10": "3.2–3.3",
        "11": "3.4",
        "12": "3.5",
        "13": "3.6",
        "14": "3.6 LTS / 4.0 beta",
        "15": "4.0",
        "16": "4.1",
        "17": "4.1 / 4.2",
        "18": "4.2 LTS",
        "19": "4.3",
        "20": "4.4",
        "21": "5.0+",
    }

    with open(path, "rb") as f:
        raw_start = f.read(4)

    compressed_by: str | None = None

    if raw_start[:4] == ZSTD_MAGIC:
        compressed_by = "zstd"
        try:
            import zstandard as _zstd
        except ImportError:
            return "[.blend file uses zstd compression (Blender 4.0+) — zstandard library not installed]"
        try:
            with open(path, "rb") as f:
                header = _zstd.ZstdDecompressor().decompress(f.read(), max_output_size=128)
        except Exception as exc:
            return f"[.blend: zstd decompression failed: {exc}]"

    elif raw_start[:2] == GZIP_MAGIC:
        compressed_by = "gzip"
        try:
            with gzip.open(path, "rb") as gz:
                header = gz.read(128)
        except Exception as exc:
            return f"[.blend: gzip decompression failed: {exc}]"

    else:
        with open(path, "rb") as f:
            header = f.read(128)

    if not header.startswith(BLEND_MAGIC):
        logger.warning("blend: unexpected header hex=%s", header[:12].hex())
        return "[Not a valid .blend file]"

    rest = header[7:]  # everything after "BLENDER"

    # New format (Blender 4.0+): next 2 bytes are ASCII digits ("16", "17", …)
    if len(rest) >= 8 and rest[:2].isdigit():
        fmt_ver   = rest[0:2].decode("ascii")              # e.g. "17"
        ptr_char  = rest[2:3]                              # '-' 64-bit | '_' 32-bit
        # rest[3:5] is padding ("01" etc.), skip
        endian_ch = rest[5:6]                              # 'v' LE | 'V' BE
        # rest[6:10] is 4-char version string, not used — we prefer fmt_ver map
        release   = FMT_VER_MAP.get(fmt_ver, f"4.x+ (file format {fmt_ver})")
        version_str = f"Blender {release}"

    # Old format (Blender ≤ 3.x): ptr + endian + 3-digit ver
    else:
        ptr_char  = rest[0:1]
        endian_ch = rest[1:2]
        ver_raw   = rest[2:5].decode("ascii", errors="replace").strip()
        try:
            v = int(ver_raw)
            version_str = f"Blender {v // 100}.{(v % 100) // 10}.{v % 10}"
        except ValueError:
            version_str = f"Blender (ver bytes: {ver_raw!r})"

    ptr_size    = 8 if ptr_char == b"-" else 4
    endian_label = "little-endian" if endian_ch == b"v" else "big-endian"
    comp_note   = f", {compressed_by} compressed" if compressed_by else ""

    return (
        f"Blender file info:\n"
        f"- Version: {version_str}\n"
        f"- Architecture: {ptr_size * 8}-bit ({endian_label}{comp_note})\n"
        f"(Geometry, materials, and scene data require Blender to open)"
    )



def _safe_zip_names(zf: zipfile.ZipFile) -> list[str]:
    """Return all file names (up to MAX_ARCHIVE_FILES), regardless of uncompressed size."""
    names: list[str] = []
    for info in zf.infolist():
        if len(names) >= MAX_ARCHIVE_FILES:
            break
        if info.is_dir():
            continue
        names.append(info.filename)
    return names


def _extractable_zip_names(zf: zipfile.ZipFile) -> list[str]:
    """Return names of files safe to extract (within uncompressed size budget)."""
    names: list[str] = []
    total_uncompressed = 0
    for info in zf.infolist():
        if len(names) >= MAX_ARCHIVE_FILES:
            break
        if info.is_dir():
            continue
        total_uncompressed += info.file_size
        if total_uncompressed > MAX_ARCHIVE_MB * 1024 * 1024:
            break
        names.append(info.filename)
    return names


def _text_from_zip(path: str) -> str:
    parts = []
    with zipfile.ZipFile(path) as zf:
        all_names = _safe_zip_names(zf)
        extract_names = _extractable_zip_names(zf)
        for name in extract_names:
            if len(parts) >= 10:
                break
            suffix = _suffix_from_name(name)
            try:
                with zf.open(name) as f:
                    raw = f.read(MAX_TEXT_CHARS)
            except Exception:
                continue
            if suffix in CODE_EXTS or _is_probably_text(raw):
                text = _limit_text(_decode_bytes(raw))
                if text:
                    parts.append(f"{name}:\n{text}")
    if parts:
        return "ZIP archive text preview:\n\n" + "\n\n---\n\n".join(parts)
    return "ZIP archive with files:\n" + "\n".join(f"- {name}" for name in all_names)


def _text_from_plain(path: str) -> str:
    with open(path, "rb") as f:
        raw = f.read(MAX_TEXT_CHARS * 2)
    return _limit_text(_decode_bytes(raw))


def _text_from_html(html_bytes: bytes) -> str:
    soup = BeautifulSoup(html_bytes, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    text = soup.get_text("\n", strip=True)
    text = html.unescape(text)
    if title and title not in text[:500]:
        text = f"{title}\n\n{text}"
    return _limit_text(text)


def _is_youtube_url(url: str) -> bool:
    return bool(YOUTUBE_RE.match(url))


async def _download_url(url: str) -> tuple[str, str | None, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (CodexBot/1.0)",
        "Accept": "*/*",
    }
    max_bytes = MAX_URL_MB * 1024 * 1024
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "").split(";", 1)[0].strip().lower() or None
            suffix = _suffix_from_name(urlparse(url).path)
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".bin") as f:
                written = 0
                async for chunk in resp.aiter_bytes():
                    written += len(chunk)
                    if written > max_bytes:
                        raise ValueError(f"URL content exceeds {MAX_URL_MB} MB")
                    f.write(chunk)
                return f.name, content_type, suffix


def _is_code_or_text_name(name: str | None) -> bool:
    suffix = _suffix_from_name(name)
    return suffix in CODE_EXTS or suffix in {".csv", ".log", ".json", ".jsonl", ".ndjson", ".xml", ".yaml", ".yml"}


def _doc_kind(filename: str | None, mime_type: str | None) -> str | None:
    suffix = _suffix_from_name(filename)
    if suffix in {".pdf", ".docx", ".pptx", ".xlsx", ".zip"}:
        return suffix.lstrip(".")
    if suffix == ".blend":
        return "blend"
    if mime_type:
        if mime_type == "application/pdf":
            return "pdf"
        if mime_type in {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}:
            return "docx"
        if mime_type in {"application/vnd.openxmlformats-officedocument.presentationml.presentation"}:
            return "pptx"
        if mime_type in {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}:
            return "xlsx"
        if mime_type == "application/zip":
            return "zip"
        if mime_type.startswith(TEXT_MIME_PREFIXES) or mime_type in STRUCTURED_MIME:
            return "text"
    if suffix in CODE_EXTS:
        return "code"
    if suffix in {".txt", ".log", ".json", ".jsonl", ".ndjson", ".xml", ".csv"}:
        return "text"
    return None


def _file_kind(path: str, filename: str | None, mime_type: str | None) -> str | None:
    kind = _doc_kind(filename, mime_type)
    if kind:
        return kind
    if mime_type and mime_type.startswith(TEXT_MIME_PREFIXES):
        return "text"
    if _is_code_or_text_name(filename):
        return "code"
    with open(path, "rb") as f:
        if _is_probably_text(f.read(4096)):
            return "text"
    return None


def _analyze_local_file(path: str, filename: str | None, mime_type: str | None) -> str | None:
    kind = _file_kind(path, filename, mime_type)
    try:
        if kind == "pdf":
            return _limit_text(_text_from_pdf(path))
        if kind == "docx":
            return _limit_text(_text_from_docx(path))
        if kind == "pptx":
            return _limit_text(_text_from_pptx(path))
        if kind == "xlsx":
            return _limit_text(_text_from_xlsx(path))
        if kind == "zip":
            return _limit_text(_text_from_zip(path), MAX_TEXT_CHARS * 2)
        if kind == "blend":
            return _text_from_blend(path)
        if kind in {"text", "code"}:
            return _limit_text(_text_from_plain(path))
    except Exception as exc:
        logger.error("Local content extraction failed: %s", exc)
        return None
    return None


def looks_like_news(text: str) -> bool:
    """Return True if the text seems to be a news claim worth web-searching."""
    return len(text) >= 30 and bool(NEWS_KEYWORDS_RE.search(text))


async def web_search(query: str, max_results: int = 3) -> Optional[str]:
    """Search the web via DuckDuckGo Lite and return brief snippets."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(
                "https://lite.duckduckgo.com/lite/",
                params={"q": query},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/124.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            r.raise_for_status()
            soup = BeautifulSoup(r.content, "html.parser")
            snippets = []
            for el in soup.select(".result-snippet")[:max_results]:
                t = el.get_text(" ", strip=True)
                if t:
                    snippets.append(t[:300])
            return "\n\n".join(snippets) if snippets else None
    except Exception as exc:
        logger.error("Web search failed: %s", exc)
        return None


async def _analyze_github_url(url: str) -> Optional[str]:
    """Fetch code/README from a GitHub URL and return its text content."""
    blob_match = GITHUB_BLOB_RE.match(url)
    if blob_match:
        owner, repo, branch, filepath = blob_match.groups()
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filepath}"
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                r = await client.get(raw_url)
                r.raise_for_status()
                text = _decode_bytes(r.content)
                return _limit_text(f"GitHub file {filepath}:\n\n{text}")
        except Exception as exc:
            logger.error("GitHub blob fetch failed: %s", exc)
            return None

    repo_match = GITHUB_REPO_RE.match(url)
    if repo_match:
        owner, repo = repo_match.groups()
        parts = []
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                api_url = f"https://api.github.com/repos/{owner}/{repo}"
                r = await client.get(api_url, headers={"Accept": "application/vnd.github+json"})
                if r.status_code == 200:
                    data = r.json()
                    desc = data.get("description") or ""
                    lang = data.get("language") or ""
                    stars = data.get("stargazers_count", 0)
                    parts.append(f"Repo: {owner}/{repo}")
                    if desc:
                        parts.append(f"Description: {desc}")
                    if lang:
                        parts.append(f"Language: {lang}")
                    parts.append(f"Stars: {stars}")

                readme_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
                rr = await client.get(readme_url, headers={"Accept": "application/vnd.github.raw+json"})
                if rr.status_code == 200:
                    readme_text = _limit_text(rr.text, limit=3000)
                    parts.append(f"\nREADME:\n{readme_text}")
        except Exception as exc:
            logger.error("GitHub repo fetch failed: %s", exc)
        return "\n".join(parts) if parts else None

    return None


async def _youtube_oembed(url: str) -> Optional[str]:
    """Fetch YouTube title + description via oEmbed as a fallback (no API key needed)."""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            r = await client.get(
                "https://www.youtube.com/oembed",
                params={"url": url, "format": "json"},
            )
            r.raise_for_status()
            data = r.json()
            title = data.get("title", "")
            author = data.get("author_name", "")
            parts = []
            if title:
                parts.append(f"Title: {title}")
            if author:
                parts.append(f"Channel: {author}")
            return "\n".join(parts) if parts else None
    except Exception as exc:
        logger.warning("YouTube oEmbed fallback failed: %s", exc)
        return None


async def analyze_url(url: str) -> Optional[str]:
    url = url.strip()
    if not URL_RE.match(url):
        return None
    if _is_youtube_url(url):
        try:
            return await gemini_youtube_video(
                url,
                "Summarize this public YouTube video in 2-3 short sentences. Mention the main topic and any important moments. Do not provide reasoning.",
            )
        except GeminiRateLimitError:
            logger.warning("Gemini 429 — falling back to oEmbed for %s", url)
            return await _youtube_oembed(url)
        except Exception as exc:
            logger.error("YouTube Gemini analysis failed: %s — trying oEmbed", exc)
            return await _youtube_oembed(url)
    if GITHUB_BLOB_RE.match(url) or GITHUB_REPO_RE.match(url):
        result = await _analyze_github_url(url)
        if result:
            return result
    path = None
    try:
        path, content_type, suffix = await _download_url(url)
        text = _analyze_local_file(path, url, content_type)
        if text:
            return text
        if content_type and content_type.startswith("text/html"):
            return _limit_text(_text_from_html(Path(path).read_bytes()))
        if content_type and content_type.startswith(TEXT_MIME_PREFIXES):
            return _limit_text(_text_from_plain(path))
        if suffix in CODE_EXTS:
            return _limit_text(_text_from_plain(path))
        return f"Downloaded URL content type: {content_type or 'unknown'}"
    except Exception as exc:
        logger.error("URL analysis failed: %s", exc)
        return None
    finally:
        if path and os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                pass


async def analyze_file(path: str, filename: str | None = None, mime_type: str | None = None) -> Optional[str]:
    return _analyze_local_file(path, filename, mime_type)
