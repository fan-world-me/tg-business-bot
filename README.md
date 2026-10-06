[![Telegram](https://img.shields.io/badge/Telegram-@fan__world__me-2CA5E0?style=flat-square&logo=telegram)](https://t.me/fan_world_me)   [![Discord](https://img.shields.io/badge/Discord-fan__world__me-5865F2?style=flat-square&logo=discord)](https://discord.com/users/fan_world_me)   [![GitHub](https://img.shields.io/badge/GitHub-fan--world--me-181717?style=flat-square&logo=github)](https://github.com/fan-world-me)   [![Portfolio](https://img.shields.io/badge/Portfolio-fan--world--me.github.io-00e5ff?style=flat-square&logo=githubpages&logoColor=white)](https://fan-world-me.github.io/)

```
████████╗ ██████╗      ██████╗  ██████╗ ████████╗
╚══██╔══╝██╔════╝      ██╔══██╗██╔═══██╗╚══██╔══╝
   ██║   ██║  ███╗     ██████╔╝██║   ██║   ██║
   ██║   ██║   ██║     ██╔══██╗██║   ██║   ██║
   ██║   ╚██████╔╝     ██████╔╝╚██████╔╝   ██║
   ╚═╝    ╚═════╝      ╚═════╝  ╚═════╝    ╚═╝
  Telegram Business Bot — AI auto-replies with media, docs & cloud storage
```

Telegram Business Bot that replies on behalf of the account owner — handles text, images, video, audio, documents, code files, GitHub links, and web pages with multi-AI fallback. Conversation history, mute list, and forwarded messages are persisted to Cloudflare D1 + R2.

### 💭 More about this bot

- 🤖 **Multi-AI fallback** — Groq (primary) → NVIDIA (fallback) for text; Groq Vision for images; Gemini for YouTube; Groq Whisper for voice
- 📷 **Media analysis** — photos, stickers, video, GIFs, video notes, voice messages, audio
- 📄 **Document parsing** — PDF, DOCX, PPTX, XLSX, ZIP archives, 40+ code/text extensions
- 🔗 **URL content** — fetches web pages and direct file links for analysis
- 💻 **GitHub code reading** — blob file URLs → raw source; repo URLs → README + stats
- 📰 **News verification** — detects news-like messages, cross-references via DuckDuckGo
- 💬 **Forwarded messages** — analyzes forwarded content (text + media) in business chats
- 📦 **Conversation history** — per-chat context persisted to Cloudflare D1 (survives restarts)
- 🔇 **Mute list** — mute / unmute users; persisted to D1, survives redeploys
- 💳 **Payment details** — shares UAH/USD/USDT when user asks to pay the owner
- 🌍 **Auto-language** — replies in the language the user writes in

---

### ⚙️ Owner Commands

| Command | Description |
|---|---|
| `/on` | Enable auto-replies |
| `/off` | Disable auto-replies |
| `/status` | Show current bot state |
| `/muted` | List muted users with inline Unmute buttons |
| `/mute <id>` | Mute user by Telegram ID |
| `/unmute <id>` | Unmute user by Telegram ID |
| `/test` | Enter test mode — simulate user messages in bot's private chat |
| `/end_test` | Exit test mode |

Every auto-reply notification to the owner includes an inline **Mute** button for one-tap silencing.

---

### 🧰 Tech Stack

**Runtime & Framework**
![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![aiogram](https://img.shields.io/badge/aiogram-3.29-009DFF?style=flat-square)
![httpx](https://img.shields.io/badge/httpx-async-00b4d8?style=flat-square)

**AI Providers**
![Groq](https://img.shields.io/badge/Groq-text+vision+whisper-F55036?style=flat-square)
![NVIDIA](https://img.shields.io/badge/NVIDIA-video+multimodal-76B900?style=flat-square&logo=nvidia&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini-YouTube-4285F4?style=flat-square&logo=google&logoColor=white)

**Storage**
![Cloudflare D1](https://img.shields.io/badge/Cloudflare_D1-SQLite-F38020?style=flat-square&logo=cloudflare&logoColor=white)
![Cloudflare R2](https://img.shields.io/badge/Cloudflare_R2-media-F38020?style=flat-square&logo=cloudflare&logoColor=white)

**Parsing**
![pypdf](https://img.shields.io/badge/pypdf-PDF-red?style=flat-square)
![python-docx](https://img.shields.io/badge/python--docx-DOCX-2B579A?style=flat-square)
![BeautifulSoup4](https://img.shields.io/badge/BeautifulSoup4-HTML-59b200?style=flat-square)

---

### 🗂️ Project Structure

```
tgbot/
├── src/
│   ├── main.py              — entry point, bot startup
│   ├── bot.py               — all message handlers, owner commands, inline buttons
│   ├── ai.py                — Groq / NVIDIA / Gemini async calls, fallback chain
│   ├── content_handler.py   — URL fetch, GitHub reading, news detection
│   ├── media_handler.py     — photo, video, audio, document analysis pipelines
│   ├── db.py                — Cloudflare D1 helpers (conversations, mutes, forwards)
│   ├── r2.py                — Cloudflare R2 upload/download helpers
│   └── config.py            — all env vars with defaults
├── requirements.txt         — pinned dependencies
├── Procfile                 — Heroku entry point
├── Dockerfile               — Docker image (Fly.io)
├── .env.example             — environment variable template
└── LICENSE
```

---

### 🚀 How it works

```
[Incoming business message]
        │
        ├── is user muted? ──────────────────► ignore
        ├── is bot disabled? ────────────────► ignore
        │
        ▼
[content_handler: detect content type]
        │
        ├── text + URL ──────► fetch page / GitHub / news search
        ├── photo / sticker ─► Groq Vision
        ├── voice / audio ───► Groq Whisper → transcribe → text AI
        ├── video / GIF ─────► NVIDIA multimodal
        ├── document ────────► extract text (PDF/DOCX/PPTX/XLSX/ZIP/code)
        └── plain text ──────► text AI
                │
                ▼
        [ai.py: Groq → NVIDIA fallback chain]
                │
                ▼
        [save to D1 conversation history]
                │
                ▼
        [reply + notify owner with Mute button]
```

---

### 🔧 Setup

```bash
cp .env.example .env
# fill in all required values

pip install -r requirements.txt
python src/main.py
```

---

### 🌍 Environment Variables

**Required**

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token |
| `OWNER_ID` | Your Telegram user ID |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID |
| `CLOUDFLARE_D1_DATABASE_ID` | D1 database UUID |
| `CLOUDFLARE_D1_API_TOKEN` | D1 API token |
| `GROQ_API_KEY` | Groq (text + vision + Whisper) |
| `GEMINI_API_KEY` | Google Gemini (YouTube analysis) |
| `NVIDIA_API_KEY` | NVIDIA (video / multimodal) |

**Optional (owner profile & payments)**

| Variable | Default | Description |
|---|---|---|
| `OWNER_USERNAME` | `me` | Telegram username shown in replies |
| `OWNER_NAME` | same | Display name |
| `OWNER_EMAIL` | — | Shared when asked |
| `OWNER_GITHUB` | — | GitHub profile link |
| `OWNER_WEBSITE` | — | Website link |
| `PAYMENT_UAH_CARD` | — | UAH card number |
| `PAYMENT_UAH_BANK` | — | UAH bank name |
| `PAYMENT_USD_CARD` | — | USD card number |
| `PAYMENT_USDT_ADDRESS` | — | USDT wallet address |
| `PAYMENT_USDT_NETWORK` | — | USDT network (TRC20, etc.) |
| `GIFT_CARD_URL` | — | Gift card link shown as payment alternative |

**Limits & tuning**

| Variable | Default | Description |
|---|---|---|
| `MAX_TOKENS` | `500` | Max tokens per reply |
| `MAX_FILE_MB` | `20` | Photos, audio, stickers |
| `MAX_VIDEO_MB` | `10` | Video, video_note, animation |
| `MAX_DOC_MB` | `15` | Documents, archives, code |
| `MAX_ARCHIVE_MB` | `8` | ZIP extraction budget |
| `MAX_ARCHIVE_FILES` | `30` | Max files listed from ZIP |
| `MAX_TEXT_CHARS` | `12000` | Characters sent to LLM |
| `HISTORY_LIMIT` | `20` | Messages kept in conversation history |
| `VIDEO_ANALYSIS_CONCURRENCY` | `1` | Serializes video analysis (avoids RAM spikes) |

---

### ☁️ Deploy

**Heroku**
```bash
heroku create tg-business-bot
heroku config:set BOT_TOKEN=... OWNER_ID=...   # set all required vars
git push heroku master
```

**Fly.io**
```bash
fly launch --name tg-business-bot --no-deploy
fly secrets import < .env
fly deploy
```

---

### 📄 License

[GPL-3.0](LICENSE) © [fan-world-me](https://github.com/fan-world-me)

---

Made with 🩵 in Ukraine 🇺🇦

[![Telegram](https://img.shields.io/badge/Telegram-@fan__world__me-2CA5E0?style=flat-square&logo=telegram)](https://t.me/fan_world_me)   [![Discord](https://img.shields.io/badge/Discord-fan__world__me-5865F2?style=flat-square&logo=discord)](https://discord.com/users/fan_world_me)   [![Portfolio](https://img.shields.io/badge/Portfolio-fan--world--me.github.io-00e5ff?style=flat-square&logo=githubpages&logoColor=white)](https://fan-world-me.github.io/)
