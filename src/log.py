"""集中日志配置 — 基于 loguru

用法:
    from src.log import logger

所有模块统一使用此 logger 实例，无需各自初始化。
"""
import sys
from pathlib import Path

from loguru import logger

# 移除 loguru 默认 handler
logger.remove()

# ── 日志输出目录 ──
_LOG_DIR = Path(__file__).resolve().parent.parent / "data" / "logs"


def setup_logging(verbose: bool = False) -> None:
    """
    配置全局日志。

    Args:
        verbose: True 时控制台输出 DEBUG 级别，否则 INFO
    """
    level = "DEBUG" if verbose else "INFO"

    # 控制台：彩色、简洁
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # 文件：完整格式，按日轮转，保留 7 天
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(_LOG_DIR / "summon_{time:YYYY-MM-DD}.log"),
        level="DEBUG",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} - "
            "{message}"
        ),
        rotation="00:00",       # 每天轮转
        retention="7 days",     # 保留 7 天
        compression="zip",      # 旧日志压缩
        encoding="utf-8",
        enqueue=True,           # 异步写入，不阻塞主线程
    )
