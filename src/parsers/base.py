"""数据源解析器基类 — 所有 Parser 实现此接口。"""

from abc import ABC, abstractmethod

from src.schema import ChaptersRaw


class BaseParser(ABC):
    """所有数据源解析器的抽象基类。

    子类实现 parse() 方法，将特定来源的内容转换为 ChaptersRaw 标准格式。
    下游 pipeline (batch/review/package) 对数据源完全无感知。
    """

    @abstractmethod
    def parse(self, source: str, book_slug: str) -> ChaptersRaw:
        """
        从数据源提取内容，转换为标准化格式。

        Args:
            source: 数据源标识（文件路径、URL 等）
            book_slug: 项目标识符（如 "CSAPP"）

        Returns:
            ChaptersRaw — 包含章节文本和元数据的标准格式
        """
        ...
