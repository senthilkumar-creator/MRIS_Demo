"""Bounded, polite async HTTP scraping with errors returned as SiteData.

Fetches static HTML and follows relevant same-host merchant pages. Existing
risk-detection and LLM modules continue to consume the original Page/SiteData.
"""
from __future__ import annotations

import asyncio
import os
import time
from urllib.parse import urljoin

import httpx

from ..config import get_config
from ..schema import FetchStatus, Page, SiteData
from .dynamic_handler import fetch_dynamic_page
from .parser import find_page_links, get_domain, is_valid_url, normalize_url, visible_text
from .policy import (CrawlPolicy, RobotsDeniedError, RobotsUnavailableError,
                     UnsafeTargetError, display_url, validate_target)

MIN_USEFUL_HTML = 500
RETRYABLE_CODES = {408, 425, 429, 500, 502, 503, 504}
MAX_REDIRECTS = 5


class PageTooLarge(ValueError):
    pass


async def _request_once(client: httpx.AsyncClient, url: str, policy: CrawlPolicy) -> httpx.Response:
    max_bytes = int(get_config()["fetch"].get("max_response_bytes", 1_000_000))
    await validate_target(url)
    if not await policy.permitted(client, url):
        raise RobotsDeniedError(f"robots.txt explicitly disallows fetching {display_url(url)}")
    slot = await policy.acquire_turn(url)
    try:
        async with client.stream("GET", url, follow_redirects=False) as response:
            if int(response.headers.get("content-length", "0") or "0") > max_bytes:
                raise PageTooLarge(f"Response exceeded the {max_bytes:,}-byte safety limit")
            chunks: list[bytes] = []
            size = 0
            async for part in response.aiter_bytes():
                size += len(part)
                if size > max_bytes:
                    raise PageTooLarge(f"Response exceeded the {max_bytes:,}-byte safety limit")
                chunks.append(part)
            # HTTPX's aiter_bytes() has ALREADY decompressed gzip/deflate/br.
            # Reconstructing a Response with the original Content-Encoding header
            # makes .text attempt a second decompression (zlib error -3).
            # Remove transport-only headers to match the decoded payload. Also
            # drop Content-Length: it described the wire, not decoded, length.
            # The byte limit above is enforced on *decoded* bytes, preventing
            # compressed pages from expanding beyond our in-memory budget.
            decoded_headers = response.headers.copy()
            for header in ("content-encoding", "content-length", "transfer-encoding"):
                if header in decoded_headers:
                    del decoded_headers[header]
            return httpx.Response(
                response.status_code,
                headers=decoded_headers,
                content=b"".join(chunks),
                request=response.request,
            )
    finally:
        slot.release()


async def _get(client: httpx.AsyncClient, url: str, retries: int, policy: CrawlPolicy | None = None) -> httpx.Response:
    policy = policy or CrawlPolicy()
    last_error: Exception | None = None
    for attempt in range(max(0, retries) + 1):
        current = url
        try:
            for _ in range(MAX_REDIRECTS + 1):
                response = await _request_once(client, current, policy)
                if response.status_code in (301, 302, 303, 307, 308) and response.headers.get("location"):
                    current = urljoin(current, response.headers["location"])
                    continue
                break
            else:
                raise httpx.TooManyRedirects("Redirect limit exceeded")
            if response.status_code in RETRYABLE_CODES and attempt < retries:
                # Respect a short Retry-After when supplied; long delays are bounded.
                try:
                    retry_after = min(2.0, max(0.0, float(response.headers.get("retry-after", "0"))))
                except ValueError:
                    retry_after = 0.0
                await asyncio.sleep(max(retry_after, min(2.0, 0.25 * (2 ** attempt))))
                continue
            return response
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            if attempt >= retries:
                raise
            await asyncio.sleep(min(2.0, 0.25 * (2 ** attempt)))
    raise last_error or RuntimeError("Request failed")


def _status_from_exception(e: Exception) -> FetchStatus:
    if isinstance(e, UnsafeTargetError):
        return FetchStatus.INVALID_URL
    if isinstance(e, RobotsDeniedError):
        return FetchStatus.BLOCKED
    if isinstance(e, RobotsUnavailableError):
        return FetchStatus.ROBOTS_UNAVAILABLE
    if isinstance(e, httpx.TimeoutException):
        return FetchStatus.TIMEOUT
    msg = str(e).lower()
    if "ssl" in msg or "certificate" in msg:
        return FetchStatus.SSL_ERROR
    if isinstance(e, httpx.ConnectError) and ("dns" in msg or "resolve" in msg or "name" in msg):
        return FetchStatus.DNS_ERROR
    return FetchStatus.ERROR


def _status_from_code(code: int) -> FetchStatus:
    if code in (401, 403, 429, 503):
        return FetchStatus.BLOCKED
    if code in (404, 410):
        return FetchStatus.NOT_FOUND
    return FetchStatus.ERROR


def _has_useful_content(html: str) -> bool:
    if len(html) >= MIN_USEFUL_HTML:
        return True
    # Small but genuine pages should not always be mistaken for JS shells.
    text = visible_text(html)
    return len(text) >= 100 and not any(s in text.lower() for s in ("enable javascript", "loading...", "just a moment"))


async def fetch_site(client: httpx.AsyncClient, site_id: int, raw_url: str,
                     policy: CrawlPolicy | None = None) -> SiteData:
    """Never raise for a merchant error; preserve original Page/SiteData API."""
    cfg = get_config()["fetch"]
    start = time.perf_counter()
    url = normalize_url(raw_url)
    site = SiteData(site_id=site_id, url=raw_url, domain=get_domain(url))
    if not url or not is_valid_url(url):
        site.status, site.error = FetchStatus.INVALID_URL, "Invalid HTTP/HTTPS URL"
        return site
    policy = policy or CrawlPolicy()
    try:
        home = await _get(client, url, int(cfg["retries"]), policy)
        if not 200 <= home.status_code < 300:
            site.status, site.error = _status_from_code(home.status_code), f"HTTP {home.status_code}"
            return site
        media_type = home.headers.get("content-type", "text/html").lower().split(";")[0]
        if media_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
            site.status, site.error = FetchStatus.ERROR, f"Unsupported content type: {media_type}"
            return site
        html = home.text
        page_url = str(home.url)
        if not _has_useful_content(html) and os.getenv("MRIS_ENABLE_DYNAMIC_FALLBACK", str(cfg.get("enable_dynamic_fallback", False))).lower() in {"1", "true", "yes", "on"}:
            # Optional browser rendering for JS shells (requires Playwright Chromium).
            # Kept as an isolated fallback; scraping does not fail when unavailable.
            try:
                dynamic = await fetch_dynamic_page(page_url)
                if dynamic.get("status") == "ok" and dynamic.get("html"):
                    html = dynamic["html"]
                    page_url = dynamic["url"]
            except Exception as exc:
                site.error = f"Dynamic fallback unavailable: {type(exc).__name__}"
        if not _has_useful_content(html):
            site.status = FetchStatus.LIMITED_CONTENT
        site.pages.append(Page(page_type="home", url=page_url, html=html))
        page_limit = max(1, int(cfg.get("max_pages_per_site", 6)))
        links = await asyncio.to_thread(find_page_links, html, page_url)
        seen = {normalize_url(page_url)}
        wanted: list[tuple[str, str]] = []
        for kind, choices in links.items():
            for target in choices:
                key = normalize_url(target)
                if key not in seen:
                    seen.add(key)
                    wanted.append((kind, target))
                if len(wanted) >= page_limit - 1:
                    break
            if len(wanted) >= page_limit - 1:
                break

        async def follow(kind: str, target: str) -> Page | None:
            try:
                result = await _get(client, target, 0, policy)
                if result.status_code < 400 and result.headers.get("content-type", "text/html").lower().split(";")[0] in {"text/html", "application/xhtml+xml", "text/plain"}:
                    # Keep all discovered pages on the final homepage's host.
                    from urllib.parse import urlsplit
                    if (urlsplit(str(result.url)).hostname or "").lower() == (urlsplit(page_url).hostname or "").lower():
                        return Page(page_type=kind, url=str(result.url), html=result.text)
            except (httpx.HTTPError, PageTooLarge, UnsafeTargetError, RobotsDeniedError, RobotsUnavailableError):
                pass  # optional linked pages do not invalidate a readable homepage
            return None

        pages = await asyncio.gather(*(follow(kind, target) for kind, target in wanted))
        site.pages.extend(page for page in pages if page is not None)
    except Exception as exc:
        site.status, site.error = _status_from_exception(exc), str(exc)[:300] or type(exc).__name__
    finally:
        site.elapsed_seconds = round(time.perf_counter() - start, 4)
    return site


def make_client() -> httpx.AsyncClient:
    cfg = get_config()["fetch"]
    limit = max(1, int(cfg["max_concurrent_sites"]))
    return httpx.AsyncClient(
        timeout=httpx.Timeout(float(cfg["timeout_seconds"]), connect=min(5, float(cfg["timeout_seconds"]))),
        follow_redirects=False,
        headers={"User-Agent": cfg["user_agent"], "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8"},
        limits=httpx.Limits(max_connections=limit * 3, max_keepalive_connections=limit),
        # Opt-in for a user-configured enterprise proxy / custom CA.
        trust_env=os.getenv("MRIS_TRUST_ENV", "0").lower() in {"1", "true", "yes", "on"},
    )
