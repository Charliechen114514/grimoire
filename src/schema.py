"""Pipeline 中间格式定义 — parse 与 batch 之间的数据契约。"""

from pydantic import BaseModel


class TocEntry(BaseModel):
    """目录条目，表示章节层级结构。"""

    level: int
    title: str


class SourceMeta(BaseModel):
    """chapters_raw.json 中 metadata 字段的结构定义。"""

    source_type: str  # "pdf" | "web" | ...
    source_uri: str  # 原始文件路径或 URL
    book_slug: str
    total_chapters: int
    parse_timestamp: str
    toc: list[TocEntry] | None = None  # 可选，verbose 模式分节使用


class ChaptersRaw(BaseModel):
    """parse 阶段的标准输出格式，batch 阶段的标准输入格式。

    chapters: {"1": "章节文本", "2": "章节文本", ...}
    metadata: 来源描述信息
    """

    chapters: dict[str, str]
    metadata: SourceMeta

    def to_json_dict(self) -> dict:
        """转换为 chapters_raw.json 的磁盘格式（chapters 展平到顶层）。"""
        payload: dict = {}
        for key in sorted(self.chapters.keys(), key=lambda k: int(k)):
            payload[key] = self.chapters[key]
        payload["metadata"] = self.metadata.model_dump()
        return payload

    @classmethod
    def from_json_dict(cls, data: dict) -> "ChaptersRaw":
        """从 chapters_raw.json 的磁盘格式加载。"""
        chapters = {k: v for k, v in data.items() if k != "metadata"}
        meta_raw = data["metadata"]

        # 兼容旧格式：source_pdf → source_uri
        if "source_uri" not in meta_raw and "source_pdf" in meta_raw:
            meta_raw["source_uri"] = meta_raw.pop("source_pdf")
        if "source_type" not in meta_raw:
            meta_raw["source_type"] = "pdf"

        # 兼容旧 TOC 格式：{level, title, page} → TocEntry
        toc_raw = meta_raw.get("toc")
        if toc_raw:
            cleaned = []
            for entry in toc_raw:
                cleaned.append({
                    "level": entry["level"],
                    "title": entry["title"],
                })
            meta_raw["toc"] = cleaned

        return cls(chapters=chapters, metadata=SourceMeta(**meta_raw))
