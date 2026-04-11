"""Packager — 将教程输出打包为 mkdocs 站点"""
import argparse
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from src.config import OUTPUT_DIR

logger = logging.getLogger(__name__)


def package(book_slug: str, site_name: str | None = None) -> Path:
    """
    将 output/{slug}/tutorials/ 打包为 mkdocs 项目。

    创建 output/{slug}/docs/ 目录和 output/{slug}/mkdocs.yml。

    Args:
        book_slug: 书籍短名
        site_name: 站点显示名称（默认使用 book_slug）

    Returns:
        mkdocs.yml 文件路径
    """
    if site_name is None:
        site_name = book_slug

    tutorials_dir = OUTPUT_DIR / book_slug / "tutorials"
    if not tutorials_dir.exists():
        raise FileNotFoundError(f"Tutorials directory not found: {tutorials_dir}")

    book_output = OUTPUT_DIR / book_slug
    docs_dir = book_output / "docs"
    chapters_dir = docs_dir / "chapters"

    # 清理并重建 docs/ 目录
    if docs_dir.exists():
        shutil.rmtree(docs_dir)
    chapters_dir.mkdir(parents=True, exist_ok=True)

    # 复制教程文件
    chapters = _copy_tutorials(tutorials_dir, chapters_dir)

    if not chapters:
        raise FileNotFoundError(f"No tutorial files found in {tutorials_dir}")

    # 生成 index.md
    _generate_index(site_name, chapters, docs_dir, book_slug)

    # 生成 mkdocs.yml
    config_path = _generate_mkdocs_config(site_name, chapters, book_output)

    logger.info("Packaged %d chapters -> %s", len(chapters), docs_dir)
    return config_path


def _copy_tutorials(
    tutorials_dir: Path,
    docs_chapters_dir: Path,
) -> list[tuple[int, str, Path]]:
    """
    复制教程 markdown 文件到 docs/chapters/。

    Returns:
        [(chapter_idx, title, dest_path), ...] 排序后的章节列表
    """
    chapters: list[tuple[int, str, Path]] = []

    for src_path in sorted(tutorials_dir.glob("ch*.md")):
        try:
            chapter_idx = int(src_path.stem[2:])
        except ValueError:
            continue

        dest_path = docs_chapters_dir / src_path.name
        shutil.copy2(src_path, dest_path)

        title = _extract_title(dest_path)
        chapters.append((chapter_idx, title, dest_path))
        logger.info("Copied Ch.%d: %s", chapter_idx, title)

    chapters.sort(key=lambda x: x[0])
    return chapters


def _extract_title(md_path: Path) -> str:
    """从 markdown 文件第一行提取 H1 标题。"""
    import re

    try:
        first_line = md_path.read_text(encoding="utf-8").split("\n", 1)[0]
        if first_line.startswith("# "):
            title = first_line[2:].strip()
        else:
            title = first_line.strip()
        # 去掉 "第 N 章 " 前缀（标题本身已含章节号，避免重复）
        title = re.sub(r"^第\s*\d+\s*章\s*", "", title)
        return title
    except (OSError, IndexError):
        return md_path.stem


def _generate_index(
    site_name: str,
    chapters: list[tuple[int, str, Path]],
    docs_dir: Path,
    book_slug: str,
) -> Path:
    """生成 docs/index.md 书籍概览页。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = [
        f"# {site_name}\n",
        f"> 基于 {book_slug} 自动生成的学习教程\n",
        f"生成日期：{now}\n",
        "## 章节目录\n",
    ]

    for chapter_idx, title, _ in chapters:
        lines.append(f"- [第 {chapter_idx} 章 {title}](chapters/ch{chapter_idx:02d}.md)\n")

    lines.append("\n---\n")
    lines.append("\n由 [Book-to-Tutorial Pipeline](https://github.com) 自动生成。\n")

    index_path = docs_dir / "index.md"
    index_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Generated index: %s", index_path)
    return index_path


def _generate_mkdocs_config(
    site_name: str,
    chapters: list[tuple[int, str, Path]],
    output_dir: Path,
) -> Path:
    """生成 mkdocs.yml 配置文件。"""
    nav_entries: list[str] = []
    for chapter_idx, title, _ in chapters:
        display = f"第 {chapter_idx} 章 {title}"
        if len(display) > 50:
            display = f"第 {chapter_idx} 章"
        nav_entries.append(f'      - "{display}": chapters/ch{chapter_idx:02d}.md')

    nav_block = "\n".join(nav_entries)

    config = f"""\
site_name: "{site_name}"
docs_dir: docs
site_dir: site
theme:
  name: material
  language: zh
  palette:
    primary: indigo
  features:
    - navigation.top
    - navigation.footer
    - search.suggest
    - search.highlight
    - content.code.copy
markdown_extensions:
  - pymdownx.highlight:
      anchor_linenums: true
  - pymdownx.superfences
  - pymdownx.details
  - admonition
  - toc:
      permalink: true
  - attr_list
nav:
  - 首页: index.md
  - 章节:
{nav_block}
"""

    config_path = output_dir / "mkdocs.yml"
    config_path.write_text(config, encoding="utf-8")
    logger.info("Generated mkdocs config: %s", config_path)
    return config_path


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Package tutorials as mkdocs site")
    parser.add_argument("book_slug", help="Book identifier (e.g., CSAPP)")
    parser.add_argument("--site-name", default=None, help="Site display name")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    config_path = package(args.book_slug, site_name=args.site_name)
    print(f"\nGenerated mkdocs config: {config_path}")
    print(f"Run: cd {config_path.parent} && mkdocs serve")


if __name__ == "__main__":
    main()
