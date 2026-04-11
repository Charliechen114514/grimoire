"""Section splitter — 自适应层级分节：根据目标尺寸自动选择 L2/L3/L4 切割深度"""
import logging
import re
from dataclasses import dataclass

from src.config import VERBOSE_MIN_SECTION_CHARS, VERBOSE_TARGET_MAX_CHARS

logger = logging.getLogger(__name__)


@dataclass
class Section:
    """单个小节的结构。"""

    title: str  # 标题文本
    text: str  # 该节原始文本
    page_start: int
    page_end: int
    depth: int  # 来源 TOC 层级 (2=L2, 3=L3, ...)


# 匹配 "Chapter N" 的模式
_CHAPTER_PATTERN = re.compile(r"Chapter\s+(\d+)", re.IGNORECASE)


def _normalize(text: str) -> str:
    """归一化标题文本：折叠空白、去除换行、转小写，用于模糊匹配。"""
    return re.sub(r"\s+", " ", text.replace("\n", " ")).strip().lower()


def _find_title_in_text(title: str, text: str) -> int:
    """
    在章节文本中定位标题的字符偏移量。

    策略：
    1. 精确匹配：将标题作为独立行查找（含 PDF 页眉格式）
    2. 归一化匹配：两边都归一化后查找
    3. 前缀匹配：查找归一化标题的前 20 字符

    Returns:
        字符偏移量，未找到返回 -1
    """
    # 策略 1：精确匹配（独立行）
    escaped = re.escape(title)
    for m in re.finditer(rf"^({escaped})\s*$", text, re.MULTILINE):
        return m.start()
    # 也尝试匹配标题 + 页码的行（PDF 页眉格式）
    for m in re.finditer(rf"^({escaped})\s+\d+\s*$", text, re.MULTILINE):
        return m.start()

    # 策略 2：归一化匹配
    norm_title = _normalize(title)
    lines = text.split("\n")
    offset = 0
    for line in lines:
        if _normalize(line).startswith(norm_title):
            return offset
        offset += len(line) + 1

    # 策略 3：前缀匹配（取前 20 字符）
    prefix = norm_title[: min(20, len(norm_title))]
    if len(prefix) >= 10:
        offset = 0
        for line in lines:
            if _normalize(line).startswith(prefix):
                return offset
            offset += len(line) + 1

    return -1


def _collect_toc_subtree(
    toc: list[tuple[int, str, int]],
    chapter_idx: int,
) -> list[tuple[int, str, int]]:
    """
    从 TOC 中提取指定章节的完整子树（L1 之后、下一个 L1 之前的所有条目）。

    Returns:
        [(level, title, page), ...] 列表
    """
    ch_start_idx = None
    for i, (level, title, _page) in enumerate(toc):
        if level == 1 and _CHAPTER_PATTERN.search(title):
            m = _CHAPTER_PATTERN.search(title)
            if m and int(m.group(1)) == chapter_idx:
                ch_start_idx = i
                break

    if ch_start_idx is None:
        logger.warning("Chapter %d not found in TOC", chapter_idx)
        return []

    subtree: list[tuple[int, str, int]] = []
    for i in range(ch_start_idx + 1, len(toc)):
        level, title, page = toc[i]
        if level == 1:
            break
        subtree.append((level, title, page))

    return subtree


def _split_text_by_titles(
    text: str,
    titles: list[tuple[str, int]],  # [(title, page), ...]
    default_depth: int = 2,
) -> list[Section]:
    """
    根据标题列表将文本切片为 Section 列表。

    Args:
        text: 待切分的文本
        titles: [(title, page), ...] 已排序的标题列表
        default_depth: 这些标题的 TOC 层级

    Returns:
        Section 列表
    """
    # 定位每个标题在文本中的偏移
    boundaries: list[tuple[str, int]] = []
    for title, _page in titles:
        offset = _find_title_in_text(title, text)
        if offset >= 0:
            boundaries.append((title, offset))
        else:
            logger.warning("Title '%s' not found in text, skipping", title[:60])

    if not boundaries:
        return [Section(
            title="(untitled)",
            text=text,
            page_start=0,
            page_end=0,
            depth=default_depth,
        )]

    # 排序并去重
    boundaries.sort(key=lambda x: x[1])
    deduped: list[tuple[str, int]] = [boundaries[0]]
    for title, offset in boundaries[1:]:
        if offset != deduped[-1][1]:
            deduped.append((title, offset))

    # 切片
    sections: list[Section] = []
    for i, (title, start) in enumerate(deduped):
        end = deduped[i + 1][1] if i + 1 < len(deduped) else len(text)
        chunk = text[start:end].strip()
        sections.append(Section(
            title=title,
            text=chunk,
            page_start=titles[0][1] if titles else 0,
            page_end=0,
            depth=default_depth,
        ))

    return sections


def _find_sub_entries(
    subtree: list[tuple[int, str, int]],
    parent_title: str,
    parent_depth: int,
) -> list[tuple[str, int]]:
    """
    在子树中找到指定父标题的直接子条目（parent_depth + 1 层级）。

    Args:
        subtree: 完整的章节 TOC 子树
        parent_title: 父标题文本
        parent_depth: 父标题的层级

    Returns:
        [(title, page), ...] 子条目列表
    """
    child_level = parent_depth + 1
    norm_parent = _normalize(parent_title)

    # 找到父条目的位置
    parent_idx = None
    for i, (level, title, page) in enumerate(subtree):
        if level == parent_depth and _normalize(title).startswith(norm_parent[:20]):
            parent_idx = i
            break

    if parent_idx is None:
        return []

    # 收集直接子条目
    children: list[tuple[str, int]] = []
    for i in range(parent_idx + 1, len(subtree)):
        level, title, page = subtree[i]
        if level <= parent_depth:
            break
        if level == child_level:
            children.append((title.strip(), page))

    return children


def split_chapter_into_sections(
    chapter_text: str,
    chapter_idx: int,
    toc: list[tuple[int, str, int]] | None,
) -> list[Section]:
    """
    自适应分节：根据 TOC 层级和目标尺寸自动选择切割深度。

    策略：
    1. 先用 L2 条目切分
    2. 对超过 VERBOSE_TARGET_MAX_CHARS 的节，展开到 L3 子标题
    3. 合并过短的节
    4. 返回扁平化的 Section 列表

    Args:
        chapter_text: 章节原文
        chapter_idx: 章节编号（1-indexed）
        toc: pymupdf 原始 TOC [(level, title, page), ...]

    Returns:
        Section 列表。TOC 缺失或无条目时返回单节（整章）。
    """
    if not toc:
        logger.info("No TOC, chapter %d as single section", chapter_idx)
        return [Section(
            title=f"Chapter {chapter_idx}",
            text=chapter_text,
            page_start=0,
            page_end=0,
            depth=0,
        )]

    subtree = _collect_toc_subtree(toc, chapter_idx)
    if not subtree:
        logger.info("No TOC subtree for chapter %d", chapter_idx)
        return [Section(
            title=f"Chapter {chapter_idx}",
            text=chapter_text,
            page_start=0,
            page_end=0,
            depth=0,
        )]

    # ── 第一轮：用 L2 切分 ──
    l2_entries = [(title, page) for level, title, page in subtree if level == 2]
    if not l2_entries:
        logger.info("No L2 entries for chapter %d", chapter_idx)
        return [Section(
            title=f"Chapter {chapter_idx}",
            text=chapter_text,
            page_start=0,
            page_end=0,
            depth=0,
        )]

    l2_sections = _split_text_by_titles(chapter_text, l2_entries, default_depth=2)

    # ── 第二轮：对超大节展开子标题 ──
    final_sections: list[Section] = []
    for sec in l2_sections:
        if len(sec.text) > VERBOSE_TARGET_MAX_CHARS:
            # 尝试用 L3 子标题进一步切分
            l3_entries = _find_sub_entries(subtree, sec.title, sec.depth)
            if l3_entries:
                logger.info(
                    "Expanding large section '%s' (%d chars) into %d L3 subsections",
                    sec.title[:50], len(sec.text), len(l3_entries),
                )
                l3_sections = _split_text_by_titles(sec.text, l3_entries, default_depth=3)
                if l3_sections:
                    final_sections.extend(l3_sections)
                    continue
            # 无 L3 子条目或全部未找到，保留原节
            logger.warning(
                "Large section '%s' (%d chars) has no usable L3 entries, keeping as-is",
                sec.title[:50], len(sec.text),
            )
            final_sections.append(sec)
        else:
            final_sections.append(sec)

    # ── 第三轮：合并过短的节 ──
    merged: list[Section] = []
    for sec in final_sections:
        if merged and len(sec.text) < VERBOSE_MIN_SECTION_CHARS:
            prev = merged[-1]
            merged[-1] = Section(
                title=prev.title,
                text=prev.text + "\n\n" + sec.text,
                page_start=prev.page_start,
                page_end=sec.page_end,
                depth=prev.depth,
            )
            logger.debug(
                "Merged short section '%s' (%d chars) into '%s'",
                sec.title[:40], len(sec.text), prev.title[:40],
            )
        else:
            merged.append(sec)

    for sec in merged:
        logger.info(
            "Section '%s' [L%d]: %d chars",
            sec.title[:60], sec.depth, len(sec.text),
        )

    return merged
