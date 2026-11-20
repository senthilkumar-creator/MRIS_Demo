"""Scraper-only API contracts (kept separate from the team's assessment schema)."""
from __future__ import annotations

import asyncio
import time
from urllib.parse import urljoin, urlsplit

import httpx

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from ..batch import process_chunks
from ..config import get_config
from ..processing.clean import clean_site
from ..schema import FetchStatus, Page
from .fetcher import _get, fetch_site, make_client
from .parser import normalize_url
from .policy import CrawlPolicy


class ScrapeRequest(BaseModel):
    urls: list[str] = Field(..., min_length=1, max_length=250)
    include_html: bool = False
    max_text_chars: int = Field(default=12000, ge=100, le=50000)
    max_html_chars: int = Field(default=20000, ge=100, le=250000)
    include_inline_scripts: bool = True
    fetch_external_scripts: bool = False  # opt in; same-origin only


class ScriptInfo(BaseModel):
    src: str | None = None
    type: str = "text/javascript"
    inline: bool = False
    content: str = ""
    truncated: bool = False
    fetched: bool = False


class ScrapedPage(BaseModel):
    page_type: str
    url: str
    title: str = ""
    text: str = ""
    text_truncated: bool = False
    html: str | None = None
    html_truncated: bool = False
    script_count: int = 0
    scripts: list[ScriptInfo] = Field(default_factory=list)


class ScrapedSite(BaseModel):
    url: str
    domain: str
    fetch_status: FetchStatus
    error: str | None = None
    elapsed_seconds: float
    pages_found: int
    pages: list[ScrapedPage] = Field(default_factory=list)


class ScrapeResponse(BaseModel):
    count: int
    successful: int
    limited: int
    failed: int
    total_pages: int
    elapsed_seconds: float
    results: list[ScrapedSite]


def summarize_page(page: Page, options: ScrapeRequest) -> ScrapedPage:
    soup = BeautifulSoup(page.html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    scripts: list[ScriptInfo] = []
    tags = soup.find_all("script")
    # Cap UI/JSON size without changing the underlying HTML held in memory.
    for tag in tags[:75]:
        raw = tag.string if tag.string is not None else tag.get_text()
        raw = str(raw or "")
        is_inline = not tag.has_attr("src")
        scripts.append(ScriptInfo(
            src=urljoin(page.url, str(tag["src"])) if not is_inline else None,
            type=str(tag.get("type", "text/javascript")),
            inline=is_inline,
            content=raw[:2500] if is_inline and options.include_inline_scripts else "",
            truncated=is_inline and options.include_inline_scripts and len(raw) > 2500,
        ))
    return ScrapedPage(
        page_type=page.page_type, url=page.url, title=title,
        text=page.text[:options.max_text_chars], text_truncated=len(page.text) > options.max_text_chars,
        html=page.html[:options.max_html_chars] if options.include_html else None,
        html_truncated=options.include_html and len(page.html) > options.max_html_chars,
        script_count=len(tags), scripts=scripts,
    )


async def _fetch_script_bodies(web: httpx.AsyncClient, policy: CrawlPolicy,
                               pages: list[ScrapedPage]) -> None:
    """Opt-in: collect at most 3 same-origin external JS files per site.

    This feature does not execute JavaScript or download third-party scripts.
    """
    fetched_urls: set[str] = set()
    budget = 3
    for page in pages:
        parent = urlsplit(page.url)
        for script in page.scripts:
            if not script.src or budget <= 0 or script.src in fetched_urls:
                continue
            source = urlsplit(script.src)
            if (source.scheme, source.netloc.lower()) != (parent.scheme, parent.netloc.lower()):
                continue
            fetched_urls.add(script.src)
            budget -= 1
            try:
                response = await _get(web, script.src, 0, policy)
                mime = response.headers.get("content-type", "text/javascript").split(";", 1)[0].strip().lower()
                if response.status_code != 200 or mime not in {"text/javascript", "application/javascript", "application/x-javascript", "text/plain"}:
                    continue
                body = response.text
                script.content = body[:10000]
                script.truncated = len(body) > 10000
                script.fetched = True
            except Exception:
                pass  # failed optional resources never invalidate successful HTML


def _dedupe(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in urls:
        value = str(raw or "").strip()
        if not value:
            continue
        normalized = normalize_url(value)
        if normalized not in seen:
            seen.add(normalized)
            out.append(value)
    return out


async def scrape_urls(options: ScrapeRequest) -> ScrapeResponse:
    cfg = get_config()
    urls = _dedupe(options.urls)
    started = time.perf_counter()
    policy = CrawlPolicy()
    sem = asyncio.Semaphore(max(1, int(cfg["fetch"]["max_concurrent_sites"])))

    async with make_client() as web:
        async def worker(index: int, url: str) -> ScrapedSite:
            async with sem:
                site = await fetch_site(web, index, url, policy)
                clean_site(site)
                pages = [summarize_page(page, options) for page in site.pages]
                if options.fetch_external_scripts:
                    await _fetch_script_bodies(web, policy, pages)
            return ScrapedSite(url=url, domain=site.domain, fetch_status=site.status,
                               error=site.error, elapsed_seconds=site.elapsed_seconds,
                               pages_found=len(pages), pages=pages)

        results = await process_chunks(urls, worker, int(cfg["batch"]["chunk_size"]))
    successful = sum(r.fetch_status == FetchStatus.OK for r in results)
    limited = sum(r.fetch_status == FetchStatus.LIMITED_CONTENT for r in results)
    return ScrapeResponse(count=len(results), successful=successful, limited=limited,
                          failed=len(results) - successful - limited,
                          total_pages=sum(r.pages_found for r in results),
                          elapsed_seconds=round(time.perf_counter() - started, 3), results=results)
