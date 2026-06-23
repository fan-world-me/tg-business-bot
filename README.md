# tg-business-bot

Telegram business-bot with AI auto-replies, Cloudflare D1 logs, and media storage in R2.

## Features
- Groq for text, photo, voice, and sticker analysis
- NVIDIA multimodal models for GIF, video note, and video analysis
- URL, PDF, DOCX, PPTX, XLSX, ZIP, and code/text extraction with lightweight parsers
- Cloudflare D1 conversation logs
- Forwarded messages saved to D1 + media uploaded to R2
- `/on` `/off` `/status` `/muted` `/mute` `/unmute`
- Mute button in every notification
- Missed call auto-reply

## Setup

```bash
cp .env.example .env
# fill in all values

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python src/main.py
```

## NVIDIA Probe

Before deploying, verify the NVIDIA endpoint and model wiring:

```bash
python scripts/nvidia_probe.py
```

Optional base64 payload test:

```bash
python scripts/nvidia_probe.py --base64
```

The probe uses:

- `NVIDIA_API_BASE_URL=https://integrate.api.nvidia.com/v1/chat/completions`
- `NVIDIA_VIDEO_MODEL=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`

## Runtime Limits

- `MAX_FILE_MB` applies to non-video uploads
- `MAX_VIDEO_MB` caps `video`, `video_note`, and `animation`
- `MAX_DOC_MB` caps documents, archives, and code/text files
- `MAX_URL_MB` caps fetched web pages or direct file URLs
- `MAX_ARCHIVE_MB` and `MAX_ARCHIVE_FILES` limit ZIP inspection
- `MAX_TEXT_CHARS` caps extracted text sent into the LLM
- `VIDEO_ANALYSIS_CONCURRENCY=1` keeps video analysis serialized to avoid RAM spikes on small containers

## Deploy (Fly.io)

```bash
fly launch --name tg-business-bot --no-deploy
fly secrets import < .env
fly deploy
```

## License

GPL-3.0 - see [LICENSE](LICENSE)
