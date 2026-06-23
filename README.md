# tg-business-bot

Telegram business-bot with AI auto-replies, persistent mute list, Cloudflare D1 conversation logs, and media storage in R2.

## Features

- **Multi-AI fallback chain**: Groq (Llama 3.3) → NVIDIA (Llama 3.1) for text; Groq vision → NVIDIA multimodal for images
- **YouTube analysis** via Gemini API; falls back to oEmbed title on `429`
- **Voice / audio transcription** via Groq Whisper
- **Video / GIF / video note** analysis via NVIDIA multimodal
- **Document reading**: PDF, DOCX, PPTX, XLSX
- **Archive inspection**: ZIP — lists all files, extracts text/code within size budget
- **Code & text files**: Python, JS/TS, Go, Rust, C/C++, Java, Kotlin, Dart, Swift, PHP, Ruby, C#, Lua, Zig, R, Julia, Elixir, Haskell, Elm, Vue, Svelte, HTML, CSS, SCSS, SQL, YAML, TOML, INI, Markdown, XML, GraphQL, Terraform, Nix, and more
- **URL content analysis**: web pages, direct file links
- **Cloudflare D1**: conversation history, forwarded messages, muted users (persists across deploys)
- **Cloudflare R2**: forwarded media, owner's own uploaded files
- **Owner commands**: `/on` `/off` `/status` `/muted` `/mute <id>` `/unmute <id>` `/test` `/end_test`
- **Inline mute button** in every auto-reply notification
- **Mute list persisted to D1** — survives restarts and redeploys
- **Test mode**: owner chats with the bot as if they were a user, without a second account
- **Owner file saving**: any file or text the owner sends outside test mode is saved to R2/D1

## Setup

```bash
cp .env.example .env
# fill in all values

pip install -r requirements.txt
python src/main.py
```

## Required environment variables

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token |
| `OWNER_ID` | Your Telegram user ID |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID |
| `CLOUDFLARE_AI_GATEWAY_ID` | AI Gateway ID |
| `CLOUDFLARE_AI_GATEWAY_TOKEN` | AI Gateway auth token |
| `CLOUDFLARE_D1_DATABASE_ID` | D1 database UUID |
| `CLOUDFLARE_D1_API_TOKEN` | D1 API token |
| `GROQ_API_KEY` | Groq API key |
| `GEMINI_API_KEY` | Google Gemini API key (YouTube analysis) |
| `NVIDIA_API_KEY` | NVIDIA API key (video/multimodal) |

Optional: `GEMINI_VIDEO_MODEL` (default `gemini-2.0-flash`), `NVIDIA_VIDEO_MODEL`, `MAX_TOKENS`, `MAX_FILE_MB`, `MAX_VIDEO_MB`, `MAX_DOC_MB`, `VIDEO_ANALYSIS_CONCURRENCY`.

## NVIDIA Probe

```bash
python scripts/nvidia_probe.py
python scripts/nvidia_probe.py --base64
```

## Runtime Limits

- `MAX_FILE_MB` — photos, audio, stickers
- `MAX_VIDEO_MB` — video, video_note, animation
- `MAX_DOC_MB` — documents, archives, code files
- `MAX_URL_MB` — fetched web pages
- `MAX_ARCHIVE_MB` / `MAX_ARCHIVE_FILES` — ZIP extraction budget (listing always works)
- `MAX_TEXT_CHARS` — chars sent to LLM
- `VIDEO_ANALYSIS_CONCURRENCY=1` — serializes video analysis to avoid RAM spikes

## Deploy (Heroku)

```bash
heroku create tg-business-bot
heroku config:set BOT_TOKEN=... OWNER_ID=... # all vars from .env
git push heroku master
```

## Deploy (Fly.io)

```bash
fly launch --name tg-business-bot --no-deploy
fly secrets import < .env
fly deploy
```

## License

GPL-3.0 — see [LICENSE](LICENSE)
