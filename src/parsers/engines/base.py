"""Web 解析引擎抽象基类。

所有 Web 引擎（Wolai、Notion、静态 HTML、Playwright 等）都继承 BaseWebEngine，
只需实现 parse() 方法：输入 URL → 输出 ChaptersRaw。
"""

from abc import ABC, abstractmethod
from urllib.parse import urlparse

from src.schema import ChaptersRaw


class BaseWebEngine(ABC):
    """Web 解析引擎基类。

    子类必须设置：
        NAME:   引擎名称，用于 CLI --engine 参数
        DOMAINS: 能自动处理的域名列表（如 ["wolai.com"]）

    子类必须实现：
        parse(source, book_slug) -> ChaptersRaw

    可选覆盖：
        can_handle(url) -> bool  默认按 DOMAINS 匹配
    """

    NAME: str = ""
    DOMAINS: list[str] = []

    def __init__(self, **kwargs):
        """接收任意配置参数，子类按需使用。"""
        self.config = kwargs

    @abstractmethod
    def parse(self, source: str, book_slug: str) -> ChaptersRaw:
        """解析 URL 内容，返回标准 ChaptersRaw 格式。"""

    @classmethod
    def can_handle(cls, url: str) -> bool:
        """判断此引擎能否处理给定的 URL（默认按域名匹配）。"""
        netloc = urlparse(url).netloc.lower()
        return any(domain in netloc for domain in cls.DOMAINS)
