"""Pipeline 全局配置"""
from pathlib import Path

from dotenv import load_dotenv
import os

load_dotenv()

# ── 路径 ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BOOKS_DIR = PROJECT_ROOT / "books"
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
WRITING_STYLE_PATH = PROJECT_ROOT / "config" / "writing_style.md"

# ── API ──
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL: str | None = os.getenv("ANTHROPIC_BASE_URL") or None
MODEL_NAME: str = "claude-sonnet-4-6-20250514"
MAX_TOKENS: int = 8192
MAX_RETRIES: int = 3
MAX_CONCURRENT_CHAPTERS: int = int(os.getenv("MAX_CONCURRENT_CHAPTERS", "4"))

# ── Model aliases ──
MODEL_ALIASES: dict[str, str] = {
    "haiku":  os.getenv("ANTHROPIC_DEFAULT_HAIKU_MODEL",  "claude-haiku-4-5-20251001"),
    "sonnet": os.getenv("ANTHROPIC_DEFAULT_SONNET_MODEL", "claude-sonnet-4-6-20250514"),
    "opus":   os.getenv("ANTHROPIC_DEFAULT_OPUS_MODEL",   "claude-opus-4-6-20250514"),
}
DEFAULT_MODEL_TIER: str = os.getenv("GRIMOIRE_MODEL", "sonnet")


def resolve_model(model_override: str | None = None) -> str:
    """
    解析模型名称。优先级：CLI --model > GRIMOIRE_MODEL env > 默认 sonnet。
    支持 alias (haiku/sonnet/opus) 或直接传模型名。
    """
    tier = model_override or DEFAULT_MODEL_TIER
    return MODEL_ALIASES.get(tier, tier)

# ── Token 预算 ──
GLOSSARY_MAX_TOKENS: int = 3000

# ── Verbose mode ──
VERBOSE_MAX_TOKENS: int = 16384        # 每节输出上限
VERBOSE_MIN_SECTION_CHARS: int = 3000  # 短于此时合并到下一节
VERBOSE_TARGET_MAX_CHARS: int = 30000  # 超过此值时向下展开子标题
DEFAULT_VERBOSE_MODE: bool = os.getenv("VERBOSE_MODE", "").lower() in ("1", "true", "yes")


def book_data_dir(book_slug: str) -> Path:
    """返回指定书籍的数据目录，如 data/CSAPP/"""
    d = DATA_DIR / book_slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def book_output_dir(book_slug: str) -> Path:
    """返回指定书籍的输出目录，如 output/CSAPP/tutorials/"""
    d = OUTPUT_DIR / book_slug / "tutorials"
    d.mkdir(parents=True, exist_ok=True)
    return d
