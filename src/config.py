import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
BOT_TOKEN: str = os.environ["BOT_TOKEN"]
OWNER_ID: int = int(os.environ["OWNER_ID"])
OWNER_USERNAME: str = os.getenv("OWNER_USERNAME", "me")
OWNER_NAME: str = os.getenv("OWNER_NAME", OWNER_USERNAME)
OWNER_EMAIL: str = os.getenv("OWNER_EMAIL", "")
OWNER_GITHUB: str = os.getenv("OWNER_GITHUB", "")
OWNER_WEBSITE: str = os.getenv("OWNER_WEBSITE", "")

# Payment
PAYMENT_UAH_CARD: str = os.getenv("PAYMENT_UAH_CARD", "")
PAYMENT_UAH_BANK: str = os.getenv("PAYMENT_UAH_BANK", "")
PAYMENT_USD_CARD: str = os.getenv("PAYMENT_USD_CARD", "")
PAYMENT_USD_BANK: str = os.getenv("PAYMENT_USD_BANK", "")
PAYMENT_USDT_ADDRESS: str = os.getenv("PAYMENT_USDT_ADDRESS", "")
PAYMENT_USDT_NETWORK: str = os.getenv("PAYMENT_USDT_NETWORK", "")

# Cloudflare
CF_ACCOUNT_ID: str = os.environ["CLOUDFLARE_ACCOUNT_ID"]
CF_GATEWAY_ID: str = os.environ["CLOUDFLARE_AI_GATEWAY_ID"]
CF_GATEWAY_TOKEN: str = os.environ["CLOUDFLARE_AI_GATEWAY_TOKEN"]

# Cloudflare D1
D1_DATABASE_ID: str = os.environ["CLOUDFLARE_D1_DATABASE_ID"]
D1_API_TOKEN: str = os.environ["CLOUDFLARE_D1_API_TOKEN"]

# AI keys
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
NVIDIA_API_BASE_URL: str = os.getenv(
    "NVIDIA_API_BASE_URL",
    "https://integrate.api.nvidia.com/v1/chat/completions",
)
NVIDIA_VIDEO_MODEL: str = os.getenv(
    "NVIDIA_VIDEO_MODEL",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
)
GEMINI_VIDEO_MODEL: str = os.getenv("GEMINI_VIDEO_MODEL", "gemini-2.0-flash")

# Cloudflare R2
R2_ACCOUNT_ID: str = os.getenv("R2_ACCOUNT_ID", CF_ACCOUNT_ID)
R2_ACCESS_KEY_ID: str = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY: str = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME: str = os.getenv("R2_BUCKET_NAME", "")
R2_PUBLIC_URL: str = os.getenv("R2_PUBLIC_URL", "")

# Limits
MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "500"))
MAX_FILE_MB: int = int(os.getenv("MAX_FILE_MB", "20"))
MAX_VIDEO_MB: int = int(os.getenv("MAX_VIDEO_MB", "10"))
MAX_DOC_MB: int = int(os.getenv("MAX_DOC_MB", "15"))
MAX_URL_MB: int = int(os.getenv("MAX_URL_MB", "2"))
MAX_ARCHIVE_MB: int = int(os.getenv("MAX_ARCHIVE_MB", "8"))
MAX_ARCHIVE_FILES: int = int(os.getenv("MAX_ARCHIVE_FILES", "30"))
MAX_TEXT_CHARS: int = int(os.getenv("MAX_TEXT_CHARS", "12000"))
HISTORY_LIMIT: int = int(os.getenv("HISTORY_LIMIT", "20"))
