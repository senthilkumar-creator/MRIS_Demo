"""Async fetching of a merchant site. Owner: Member 1 (core), Member 2 (errors / status).

fetch_site() never raises: every failure becomes a FetchStatus on the returned SiteData.
"""
import asyncio
import time
from typing import Optional
import httpx

from ..config import get_config
from ..schema import FetchStatus, Page, SiteData
from .parser import find_page_links, get_domain, is_valid_url, normalize_url

MIN_USEFUL_HTML = 500   # characters; below this we treat the page as "limited content"


async def _get(client: httpx.AsyncClient, url: str, retries: int) -> httpx.Response:
    last: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            return await client.get(url)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last = e
            await asyncio.sleep(0.3 * (attempt + 1))
    raise last  # type: ignore[misc]


def _status_from_exception(e: Exception) -> FetchStatus:
    msg = str(e).lower()
    if isinstance(e, httpx.TimeoutException):
        return FetchStatus.TIMEOUT
    if "ssl" in msg or "certificate" in msg:
        return FetchStatus.SSL_ERROR
    if "name or service not known" in msg or "nodename" in msg or "getaddrinfo" in msg or "resolve" in msg:
        return FetchStatus.DNS_ERROR
    return FetchStatus.ERROR


def _status_from_code(code: int) -> FetchStatus:
    if code in (401, 403, 429, 503):
        return FetchStatus.BLOCKED
    if code == 404:
        return FetchStatus.NOT_FOUND
    return FetchStatus.ERROR


async def fetch_site(client: httpx.AsyncClient, site_id: int, raw_url: str) -> SiteData:
    cfg = get_config()["fetch"]
    start = time.perf_counter()
    url = normalize_url(raw_url)
    site = SiteData(site_id=site_id, url=raw_url, domain=get_domain(url))
    if not url or not is_valid_url(url):
        site.status, site.error = FetchStatus.INVALID_URL, "URL is not valid"
        return site
    try:
        home = await _get(client, url, cfg["retries"])
    except Exception as e:                       # noqa: BLE001  (we want every failure recorded)
        site.status, site.error = _status_from_exception(e), type(e).__name__
        site.elapsed_seconds = time.perf_counter() - start
        return site
    if home.status_code >= 400:
        site.status, site.error = _status_from_code(home.status_code), f"HTTP {home.status_code}"
        site.elapsed_seconds = time.perf_counter() - start
        return site

    site.pages.append(Page(page_type="home", url=str(home.url), html=home.text))
    if len(home.text) < MIN_USEFUL_HTML:
        site.status = FetchStatus.LIMITED_CONTENT   # probably built with JavaScript

    # follow links to policy / contact / checkout pages
    links = find_page_links(home.text, str(home.url))
    wanted = [(t, u[0]) for t, u in links.items()][: cfg["max_pages_per_site"] - 1]
    results = await asyncio.gather(*[_get(client, u, 0) for _, u in wanted], return_exceptions=True)
    for (ptype, purl), res in zip(wanted, results):
        if isinstance(res, httpx.Response) and res.status_code < 400:
            site.pages.append(Page(page_type=ptype, url=str(res.url), html=res.text))
    site.elapsed_seconds = time.perf_counter() - start
    return site


def make_client() -> httpx.AsyncClient:
    cfg = get_config()["fetch"]
    return httpx.AsyncClient(
        timeout=cfg["timeout_seconds"],
        follow_redirects=True,
        headers={"User-Agent": cfg["user_agent"]},
        limits=httpx.Limits(max_connections=cfg["max_concurrent_sites"] * 3),
    )
