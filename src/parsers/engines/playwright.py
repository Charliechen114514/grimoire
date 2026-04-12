"""Playwright 引擎 — 通过浏览器渲染 SPA 页面。

适用于需要 JavaScript 渲染的现代 Web 应用。
使用 in-page Promise+setTimeout 模式等待渲染完成。
"""

import asyncio
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from src.log import logger
from src.schema import ChaptersRaw, SourceMeta, TocEntry

from .base import BaseWebEngine
from .static import _html_to_text

# 导航链接选择器（与 static 共用）
_DEFAULT_NAV_SELECTORS = [
    "nav a",
    ".sidebar a",
    ".toc a",
    ".nav a",
    "#toc a",
    ".menu a",
    "ul li a",
]

_CONTENT_SELECTORS = [
    "article",
    "main",
    ".content",
    ".post-content",
    ".entry-content",
    ".chapter-content",
    "#content",
    ".documentation",
    ".docs",
]


class PlaywrightEngine(BaseWebEngine):
    NAME = "playwright"
    DOMAINS = []  # 手动指定时使用

    def parse(self, source: str, book_slug: str) -> ChaptersRaw:
        try:
            from playwright.async_api import async_playwright  # noqa: F401
        except ModuleNotFoundError:
            raise RuntimeError(
                "Playwright is required for this engine. "
                "Install with: pip install '.[web]' && playwright install chromium"
            )

        logger.info("Parsing website (Playwright): {} [slug={}]", source, book_slug)
        return asyncio.run(self._async_parse(source, book_slug))

    async def _async_parse(self, source: str, book_slug: str) -> ChaptersRaw:
        from playwright.async_api import async_playwright

        content_selector = self.config.get("selector")
        nav_selector = self.config.get("nav_selector")
        url_pattern = self.config.get("url_pattern")

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True, args=["--no-sandbox"]
            )
            try:
                page = await browser.new_page(viewport={"width": 1280, "height": 800})
                await page.goto(source, wait_until="load", timeout=15000)
                logger.info("Page loaded, waiting for JS to render...")

                rendered = await page.evaluate("""() => new Promise(resolve => {
                    setTimeout(() => {
                        resolve({
                            html: document.documentElement.outerHTML,
                            text: document.body?.innerText || '',
                            title: document.title || '',
                        });
                    }, 8000);
                })""")

                html = rendered["html"]
                page_text = rendered["text"]

                logger.info(
                    "Rendered: {} chars HTML, {} chars text",
                    len(html), len(page_text),
                )

                soup = BeautifulSoup(html, "html.parser")

                chapter_urls = self._extract_links(soup, source, nav_selector, url_pattern)
                if chapter_urls:
                    logger.info("Found {} chapter links, fetching each...", len(chapter_urls))
                    chapters, toc = await self._fetch_chapters(page, chapter_urls, content_selector)
                else:
                    logger.info("Single-page content, extracting as one document")
                    chapters, toc = self._extract_single_page(soup, page_text, content_selector, source)

            finally:
                await browser.close()

        return ChaptersRaw(
            chapters=chapters,
            metadata=SourceMeta(
                source_type="web",
                source_uri=source,
                book_slug=book_slug,
                total_chapters=len(chapters),
                parse_timestamp=datetime.now(timezone.utc).isoformat(),
                toc=toc,
            ),
        )

    def _extract_links(
        self, soup: BeautifulSoup, base_url: str,
        nav_selector: str | None, url_pattern: str | None,
    ) -> list[str]:
        parsed_base = urlparse(base_url)
        base_domain = parsed_base.netloc

        if nav_selector:
            links = soup.select(nav_selector)
        else:
            links = []
            for sel in _DEFAULT_NAV_SELECTORS:
                found = soup.select(sel)
                if len(found) > len(links):
                    links = found

        candidates: list[str] = []
        seen: set[str] = set()

        for link in links:
            if not isinstance(link, Tag):
                continue
            href = link.get("href")
            if not href or not isinstance(href, str):
                continue

            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)

            if parsed.netloc != base_domain:
                continue
            if not parsed.path or parsed.path == "/":
                continue
            if href.startswith("#") or href.startswith("javascript:"):
                continue

            if full_url not in seen:
                seen.add(full_url)
                candidates.append(full_url)

        if url_pattern:
            pattern = re.compile(url_pattern)
            candidates = [u for u in candidates if pattern.search(u)]

        return candidates

    async def _fetch_chapters(
        self, page, chapter_urls: list[str], content_selector: str | None,
    ) -> tuple[dict[str, str], list[TocEntry]]:
        chapters: dict[str, str] = {}
        toc_entries: list[TocEntry] = []

        for idx, url in enumerate(chapter_urls, 1):
            logger.info("Rendering chapter {}/{}: {}", idx, len(chapter_urls), url)

            await page.goto(url, wait_until="load", timeout=15000)
            rendered = await page.evaluate("""() => new Promise(resolve => {
                setTimeout(() => {
                    resolve({
                        html: document.documentElement.outerHTML,
                        text: document.body?.innerText || '',
                        title: document.title || '',
                    });
                }, 5000);
            })""")

            soup = BeautifulSoup(rendered["html"], "html.parser")
            title, text = self._extract_page_content(soup, rendered["text"], content_selector, url)

            chapters[str(idx)] = text
            toc_entries.append(TocEntry(level=1, title=title or f"Chapter {idx}"))

        return chapters, toc_entries

    def _extract_single_page(
        self, soup: BeautifulSoup, page_text: str, content_selector: str | None,
        base_url: str = "",
    ) -> tuple[dict[str, str], list[TocEntry]]:
        title = ""
        h1 = soup.find("h1")
        if h1 and isinstance(h1, Tag):
            title = h1.get_text(strip=True)
        elif soup.title and soup.title.string:
            title = soup.title.string.strip()

        content = self._find_content(soup, content_selector)
        if content is not None:
            for tag in content.find_all(
                ["script", "style", "nav", "footer", "header", "aside"]
            ):
                tag.decompose()
            text = _html_to_text(content, base_url)
        else:
            text = page_text

        return {"1": text}, [TocEntry(level=1, title=title or "Full Document")]

    def _extract_page_content(
        self, soup: BeautifulSoup, page_text: str, content_selector: str | None,
        base_url: str = "",
    ) -> tuple[str, str]:
        title = ""
        h1 = soup.find("h1")
        if h1 and isinstance(h1, Tag):
            title = h1.get_text(strip=True)
        elif soup.title and soup.title.string:
            title = soup.title.string.strip()

        content = self._find_content(soup, content_selector)
        if content is not None:
            for tag in content.find_all(
                ["script", "style", "nav", "footer", "header", "aside"]
            ):
                tag.decompose()
            text = _html_to_text(content, base_url)
        else:
            text = page_text

        return title, text

    @staticmethod
    def _find_content(soup: BeautifulSoup, selector: str | None) -> Tag | None:
        if selector:
            return soup.select_one(selector)

        for sel in _CONTENT_SELECTORS:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 200:
                return el

        return None
