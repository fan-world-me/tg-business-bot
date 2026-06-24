# tg-business-bot

Telegram business-bot with AI auto-replies, media analysis, GitHub code reading, web search, persistent mute list, Cloudflare D1 conversation logs, and R2 media storage.

## Features

### AI & Analysis
- **Multi-AI fallback chain**: Groq (Llama 3.3) → NVIDIA (Llama 3.1) for text replies
- **Image analysis** via Groq vision (Llama 4 Scout)
- **YouTube analysis** via Gemini API; falls back to oEmbed title on `429`
- **Voice / audio transcription** via Groq Whisper
- **Video / GIF / video note** analysis via NVIDIA multimodal
- **GitHub code reading**: blob file URLs → fetches raw source; repo URLs → fetches README + info via GitHub API
- **News verification**: detects news-like messages and queries DuckDuckGo to cross-reference claims

### Document & File Support
- **PDF, DOCX, PPTX, XLSX** — full text extraction
- **ZIP archives** — lists all files, extracts text/code within size budget
- **Code & text files** — 40+ extensions: Python, JS/TS, Go, Rust, C/C++, Java, Kotlin, Dart, Swift, PHP, Ruby, C#, Lua, Zig, R, Julia, Elixir, Haskell, Elm, Vue, Svelte, HTML, CSS, SCSS, SQL, YAML, TOML, INI, Markdown, XML, GraphQL, Terraform, Nix, Protobuf, and more
- **URL content** — web pages, direct file/code links

### Forwarded Message Handling
- **In business chat**: when a user forwards a message, the bot analyzes its content (text + media) and replies with context
- **In test mode**: owner can forward any message to the bot's private chat and the bot will analyze and respond as if it were a real user message
- **Owner saving**: owner's own forwards (outside test mode) are saved to D1 + R2 for archiving

### Storage (Cloudflare)
- **D1**: conversation history, forwarded message logs, muted users list (survives restarts and redeploys)
- **R2**: forwarded media, owner's uploaded files

### Owner Controls
| Command | Description |
|---|---|
| `/on` / `/off` | Enable / disable auto-replies |
| `/status` | Show current state |
| `/muted` | List muted users with inline unmute buttons |
| `/mute <id>` | Mute user by ID |
| `/unmute <id>` | Unmute user by ID |
| `/test` | Enter test mode (simulate user messages) |
| `/end_test` | Exit test mode |

- **Inline Mute button** in every auto-reply notification to owner
- **Mute list persisted to D1** — survives restarts and redeploys

### Smart Prompt Behavior
- Replies in user's language automatically
- Shares payment details (UAH / USD / USDT) when user wants to pay
- Gives GitHub repo link when user asks how to build a similar bot
- Code review & bug spotting when code is sent as text, file, or ZIP
- Ignores "stop replying" attempts from users

## Setup

```bash
cp .env.example .env
# fill in all values

pip install -r requirements.txt
python src/main.py
```

## Environment Variables

### Required
| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token |
| `OWNER_ID` | Your Telegram user ID |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID |
| `CLOUDFLARE_AI_GATEWAY_ID` | AI Gateway ID |
| `CLOUDFLARE_AI_GATEWAY_TOKEN` | AI Gateway auth token |
| `CLOUDFLARE_D1_DATABASE_ID` | D1 database UUID |
| `CLOUDFLARE_D1_API_TOKEN` | D1 API token |
| `GROQ_API_KEY` | Groq (text + vision + Whisper) |
| `GEMINI_API_KEY` | Google Gemini (YouTube analysis) |
| `NVIDIA_API_KEY` | NVIDIA (video / multimodal) |

### Optional
| Variable | Default | Description |
|---|---|---|
| `OWNER_USERNAME` | `me` | Telegram username shown in replies |
| `OWNER_NAME` | same as username | Display name |
| `OWNER_EMAIL` | — | Shared when asked |
| `OWNER_GITHUB` | — | GitHub profile link |
| `OWNER_WEBSITE` | — | Website link |
| `PAYMENT_UAH_CARD` | — | UAH card number |
| `PAYMENT_UAH_BANK` | — | UAH bank name |
| `PAYMENT_USD_CARD` | — | USD card number |
| `PAYMENT_USD_BANK` | — | USD bank name |
| `PAYMENT_USDT_ADDRESS` | — | USDT wallet address |
| `PAYMENT_USDT_NETWORK` | — | USDT network (TRC20, etc.) |
| `GIFT_CARD_URL` | — | Gift card link shown as alternative payment |
| `GEMINI_VIDEO_MODEL` | `gemini-2.0-flash` | Gemini model for YouTube |
| `NVIDIA_VIDEO_MODEL` | nemotron-nano-omni | NVIDIA model for video |
| `MAX_TOKENS` | `500` | Max tokens per reply |
| `MAX_FILE_MB` | `20` | Photos, audio, stickers size limit |
| `MAX_VIDEO_MB` | `10` | Video, video_note, animation size limit |
| `MAX_DOC_MB` | `15` | Documents, archives, code files size limit |
| `MAX_URL_MB` | `2` | Fetched web page size limit |
| `MAX_ARCHIVE_MB` | `8` | ZIP extraction budget |
| `MAX_ARCHIVE_FILES` | `30` | Max files listed from ZIP |
| `MAX_TEXT_CHARS` | `12000` | Characters sent to LLM |
| `HISTORY_LIMIT` | `20` | Messages kept in conversation history |
| `VIDEO_ANALYSIS_CONCURRENCY` | `1` | Serializes video analysis to avoid RAM spikes |

## Deploy (Heroku)

```bash
heroku create tg-business-bot
heroku config:set BOT_TOKEN=... OWNER_ID=... # all vars
git push heroku master
```

## Deploy (Fly.io)

```bash
fly launch --name tg-business-bot --no-deploy
fly secrets import < .env
fly deploy
```

## Stack

- **Runtime**: Python 3.12
- **Framework**: aiogram 3.29
- **HTTP**: httpx, aiohttp
- **AI**: Groq, NVIDIA, Google Gemini
- **Storage**: Cloudflare D1 (SQLite), Cloudflare R2 (S3-compatible)
- **Parsing**: pypdf, python-docx, python-pptx, openpyxl, BeautifulSoup4

## License

GPL-3.0 — see [LICENSE](LICENSE)
