"""Static 引擎 — httpx + BeautifulSoup 静态 HTML 解析。

适用于传统服务端渲染的教程网站。
"""

import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from src.log import logger
from src.schema import ChaptersRaw, SourceMeta, TocEntry

from .base import BaseWebEngine

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


class StaticEngine(BaseWebEngine):
    NAME = "static"
    DOMAINS = []  # 默认回退引擎，不绑定域名

    def parse(self, source: str, book_slug: str) -> ChaptersRaw:
        logger.info("Parsing website (static): {} [slug={}]", source, book_slug)

        content_selector = self.config.get("selector")
        nav_selector = self.config.get("nav_selector")
        url_pattern = self.config.get("url_pattern")

        with httpx.Client(follow_redirects=True, timeout=30) as client:
            chapter_urls = self._discover_chapters(
                client, source, nav_selector, url_pattern
            )
            if not chapter_urls:
                # SPA 检测提示
                try:
                    resp_check = client.get(source)
                    if _is_spa_hint(resp_check.text):
                        logger.warning(
                            "页面看起来是 SPA 应用，静态 HTML 无导航链接。"
                            "尝试 --engine playwright 启用 JS 渲染。"
                        )
                except Exception:
                    pass
                raise ValueError(f"No chapter links found at {source}")

            logger.info("Discovered {} chapter URLs", len(chapter_urls))

            chapters: dict[str, str] = {}
            toc_entries: list[TocEntry] = []

            for idx, url in enumerate(chapter_urls, 1):
                logger.info("Fetching chapter {}/{}: {}", idx, len(chapter_urls), url)
                title, text = self._extract_page(client, url, content_selector)
                chapters[str(idx)] = text
                toc_entries.append(TocEntry(level=1, title=title or f"Chapter {idx}"))

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

    def _discover_chapters(
        self,
        client: httpx.Client,
        base_url: str,
        nav_selector: str | None,
        url_pattern: str | None,
    ) -> list[str]:
        resp = client.get(base_url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

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

        if len(candidates) < 2 and not url_pattern:
            candidates = self._guess_chapter_urls(client, base_url)

        return candidates

    def _guess_chapter_urls(
        self, client: httpx.Client, base_url: str
    ) -> list[str]:
        patterns = [
            "/chapter-{n}",
            "/ch{n:02d}",
            "/{n:02d}",
            "/chapter{n}",
            "/part-{n}",
        ]

        for pattern in patterns:
            guessed: list[str] = []
            for n in range(1, 50):
                url = base_url.rstrip("/") + pattern.format(n=n)
                try:
                    resp = client.head(url, follow_redirects=True)
                    if resp.status_code == 200:
                        guessed.append(url)
                except httpx.HTTPError:
                    break

            if len(guessed) >= 2:
                logger.info(
                    "Guessed {} chapter URLs using pattern '{}'",
                    len(guessed), pattern,
                )
                return guessed

        return []

    def _extract_page(
        self, client: httpx.Client, url: str, content_selector: str | None
    ) -> tuple[str, str]:
        resp = client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        title = ""
        h1 = soup.find("h1")
        if h1 and isinstance(h1, Tag):
            title = h1.get_text(strip=True)

        content = self._find_content(soup, content_selector)
        if content is None:
            logger.warning("No content area found at {}, using <body>", url)
            content = soup.body or soup

        for tag in content.find_all(
            ["script", "style", "nav", "footer", "header", "aside"]
        ):
            tag.decompose()

        text = _html_to_text(content, url)
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


def _html_to_text(element: Tag, base_url: str = "") -> str:
    lines: list[str] = []

    for tag in element.descendants:
        if not isinstance(tag, Tag):
            continue

        if tag.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag.name[1])
            text = tag.get_text(strip=True)
            if text:
                lines.append(f"\n{'#' * level} {text}\n")
        elif tag.name == "p":
            text = tag.get_text(strip=True)
            if text:
                lines.append(f"\n{text}\n")
        elif tag.name == "li":
            text = tag.get_text(strip=True)
            if text:
                lines.append(f"- {text}")
        elif tag.name == "pre":
            code = tag.get_text()
            lines.append(f"\n```\n{code}\n```\n")
        elif tag.name == "code" and tag.parent and tag.parent.name != "pre":
            text = tag.get_text(strip=True)
            if text:
                lines.append(f"`{text}`")
        elif tag.name == "img":
            src = tag.get("src", "")
            if not src:
                continue
            if base_url:
                src = urljoin(base_url, src)
            alt = tag.get("alt", "")
            logger.info("Found image: {} (alt: {})", src, alt[:60])
            lines.append(f"\n![{alt}]({src})\n")

    result = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", result).strip()


def _is_spa_hint(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("body")
    if body is None:
        return False
    text = body.get_text(strip=True)
    root_div = soup.find("div", id="root") or soup.find("div", id="app")
    if root_div and len(text) < 200:
        return True
    scripts = body.find_all("script")
    if len(scripts) > 3 and len(text) < 100:
        return True
    return False
