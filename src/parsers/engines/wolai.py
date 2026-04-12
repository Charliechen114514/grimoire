"""Wolai 引擎 — 通过 Wolai 公开 API 直接获取章节内容。

无需 Playwright，纯 HTTP API 调用，速度极快。
"""

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from src.log import logger
from src.schema import ChaptersRaw, SourceMeta, TocEntry

from .base import BaseWebEngine


class WolaiEngine(BaseWebEngine):
    NAME = "wolai"
    DOMAINS = ["wolai.com"]

    API_BASE = "https://api.wolai.com/v1"
    API_HEADERS = {"Referer": "https://www.wolai.com/"}

    def parse(self, source: str, book_slug: str) -> ChaptersRaw:
        logger.info("Parsing Wolai via API: {} [slug={}]", source, book_slug)

        page_id = urlparse(source).path.strip("/")
        if not page_id:
            raise ValueError(f"Cannot extract Wolai page ID from {source}")

        with httpx.Client(follow_redirects=True, timeout=30) as client:
            sub_pages = self._get_sub_pages(client, page_id)
            if not sub_pages:
                logger.warning("No sub-pages found, extracting single page content")
                sub_pages = [{"id": page_id, "title": "Full Document"}]

            logger.info("Found {} Wolai sub-pages", len(sub_pages))

            chapters: dict[str, str] = {}
            toc_entries: list[TocEntry] = []

            for idx, page_info in enumerate(sub_pages, 1):
                title = page_info["title"]
                logger.info(
                    "Fetching Wolai chapter {}/{}: {}",
                    idx, len(sub_pages), title,
                )
                text = self._fetch_page_text(client, page_info["id"])
                chapters[str(idx)] = text
                toc_entries.append(TocEntry(level=1, title=title))

        return ChaptersRaw(
            chapters=chapters,
            metadata=SourceMeta(
                source_type="web",
                source_uri=source,
                book_slug=book_slug,
                total_chapters=len(chapters),
                parse_timestamp=datetime.now(timezone.utc).isoformat(),
                toc=toc_entries,
            ),
        )

    def _get_sub_pages(self, client: httpx.Client, page_id: str) -> list[dict]:
        resp = client.post(
            f"{self.API_BASE}/pages/getSharedSubPages",
            json={"pageId": page_id},
            headers=self.API_HEADERS,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 1000:
            raise ValueError(f"Wolai API error: {data.get('message', 'unknown')}")

        pages = []
        for item in data.get("data", []):
            attrs = item.get("attributes", {})
            title_list = attrs.get("title", [])
            title = title_list[0][0] if title_list and title_list[0] else "Untitled"
            pages.append({"id": item["id"], "title": title})

        return pages

    def _fetch_page_text(self, client: httpx.Client, page_id: str) -> str:
        resp = client.post(
            f"{self.API_BASE}/pages/getPageChunks",
            json={
                "pageId": page_id,
                "limit": 100,
                "position": {"stack": []},
                "chunkNumber": 0,
            },
            headers=self.API_HEADERS,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 1000:
            logger.warning(
                "Wolai getPageChunks error for {}: {}", page_id, data.get("message")
            )
            return ""

        blocks = data.get("data", {}).get("block", {})
        return self._blocks_to_text(blocks)

    @staticmethod
    def _blocks_to_text(blocks: dict) -> str:
        type_to_heading = {
            "header": "## ",
            "midHeader": "### ",
            "tinyHeader": "#### ",
        }
        type_to_prefix = {
            "bullList": "- ",
            "quote": "> ",
        }

        sorted_blocks = sorted(
            blocks.values(),
            key=lambda b: b.get("value", {}).get("created_time", 0),
        )

        lines: list[str] = []
        for bdata in sorted_blocks:
            val = bdata.get("value", {})
            if not val:
                continue

            btype = val.get("type", "")
            attrs = val.get("attributes", {})
            title_list = attrs.get("title", [])

            text_parts: list[str] = []
            for part in title_list:
                if isinstance(part, list) and len(part) > 0:
                    text_parts.append(str(part[0]))
                elif isinstance(part, str):
                    text_parts.append(part)
            text = "".join(text_parts).strip()

            # 处理图片 block：source 为 URL 列表，title 为 caption
            if btype == "image":
                source_list = attrs.get("source", [])
                img_url = source_list[0] if source_list else ""
                if img_url:
                    logger.info("Found image: {} (caption: {})", img_url, text[:60])
                    lines.append(f"\n![{text}]({img_url})\n")
                continue

            if not text or btype == "page":
                continue

            if btype in type_to_heading:
                lines.append(f"\n{type_to_heading[btype]}{text}\n")
            elif btype in type_to_prefix:
                lines.append(f"{type_to_prefix[btype]}{text}")
            elif btype == "code":
                lines.append(f"\n```\n{text}\n```\n")
            elif btype == "numberList":
                lines.append(f"- {text}")
            else:
                lines.append(f"\n{text}\n")

        result = "\n".join(lines)
        return re.sub(r"\n{3,}", "\n\n", result).strip()
