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

# ── Token 预算 ──
GLOSSARY_MAX_TOKENS: int = 3000


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
