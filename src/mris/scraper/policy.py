"""Safe, polite HTTP crawling policy.

robots.txt distinction:
* explicit Disallow -> RobotsDeniedError (BLOCKED)
* cannot establish robots policy -> RobotsUnavailableError (ROBOTS_UNAVAILABLE)

We fail closed when robots.txt is unreachable, but report that as an access
problem rather than pretending that the site explicitly denied crawling.

Security note: DNS validation is defense in depth, not a replacement for an
outbound firewall; DNS can change between the validation and the connection.
"""
from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
from collections import defaultdict
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from ..config import get_config
from .parser import is_valid_url


class UnsafeTargetError(ValueError):
    """URL is unsafe or prohibited by the crawling policy."""


class RobotsDeniedError(PermissionError):
    """The site's readable robots.txt explicitly disallows this URL."""


class RobotsUnavailableError(PermissionError):
    """The crawler could not establish robots.txt permission; no fetch occurred."""


def display_url(url: str) -> str:
    """Display URLs without query strings or fragments (possibly containing tokens)."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path or '/', '', ''))


def _enabled(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {'1', 'yes', 'true', 'on'}


def _address_is_global(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return True


async def validate_target(url: str) -> None:
    """Reject local/private addresses and recheck each redirect destination."""
    if not is_valid_url(url):
        raise UnsafeTargetError('URL must be a valid HTTP or HTTPS address without credentials')
    parts = urlsplit(url)
    host = (parts.hostname or '').rstrip('.').lower()
    allow_private = _enabled('MRIS_ALLOW_PRIVATE_NETWORKS', get_config()['fetch'].get('allow_private_networks', False))
    if allow_private:
        return  # Only for isolated local development or integration testing.
    if host in {'localhost', 'localhost.localdomain'} or host.endswith(('.localhost', '.local', '.internal')):
        raise UnsafeTargetError('Local or internal network URLs are disabled')
    if not _address_is_global(host):
        raise UnsafeTargetError('Private, loopback or reserved IP addresses are disabled')
    if not _enabled('MRIS_SKIP_DNS_CHECK', False):
        try:
            loop = asyncio.get_running_loop()
            records = await asyncio.wait_for(
                loop.getaddrinfo(host, parts.port or (443 if parts.scheme == 'https' else 80), type=socket.SOCK_STREAM),
                timeout=3,
            )
        except (socket.gaierror, asyncio.TimeoutError) as exc:
            raise httpx.ConnectError(f'DNS lookup failed for {host}: {type(exc).__name__}') from exc
        if not records or any(not _address_is_global(record[4][0]) for record in records):
            raise UnsafeTargetError('DNS resolves to a non-public IP address')


class CrawlPolicy:
    """One per batch; shared cached robots rules and per-host pacing."""

    def __init__(self) -> None:
        cfg = get_config()['fetch']
        self.user_agent = cfg['user_agent']
        self.respect_robots = _enabled('MRIS_RESPECT_ROBOTS', cfg.get('respect_robots', True))
        self.per_host_limit = max(1, int(cfg.get('max_concurrent_per_host', 2)))
        self.min_interval = max(0.0, float(cfg.get('min_host_interval_seconds', 0.2)))
        self.robots_timeout = max(1.0, float(cfg.get('robots_timeout_seconds', 6)))
        self._host_semaphores: dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(self.per_host_limit))
        self._host_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._next_at: dict[str, float] = {}
        self._robots_tasks: dict[str, asyncio.Task[RobotFileParser | bool | RobotsUnavailableError]] = {}

    async def permitted(self, client: httpx.AsyncClient, url: str) -> bool:
        if not self.respect_robots:
            return True
        parts = urlsplit(url)
        origin = f'{parts.scheme}://{parts.netloc}'
        if origin not in self._robots_tasks:
            self._robots_tasks[origin] = asyncio.create_task(self._load_robots(client, origin))
        policy = await self._robots_tasks[origin]
        if isinstance(policy, RobotsUnavailableError):
            raise policy
        if isinstance(policy, bool):
            return policy
        return policy.can_fetch(self.user_agent, url)

    async def _load_robots(self, client: httpx.AsyncClient, origin: str) -> RobotFileParser | bool | RobotsUnavailableError:
        """Retrieve robots with redirects checked and a 256 KB response cap.

        Missing robots (404/410) means no rules. Access/server failures mean
        policy is unknown: do not crawl and surface a diagnostic error.
        """
        current = origin + '/robots.txt'
        try:
            for _ in range(4):
                await validate_target(current)
                async with client.stream('GET', current, timeout=self.robots_timeout, follow_redirects=False) as response:
                    status = response.status_code
                    if status in (301, 302, 303, 307, 308):
                        dest = response.headers.get('location')
                        if not dest:
                            return RobotsUnavailableError(f'robots.txt redirect missing Location for {display_url(current)}')
                        current = urljoin(current, dest)
                        continue
                    if status in (204, 404, 410):
                        return True
                    if status != 200:
                        return RobotsUnavailableError(f'robots.txt returned HTTP {status} at {display_url(current)}; permission unknown')
                    length = response.headers.get('content-length', '').strip()
                    if length.isdigit() and int(length) > 256_000:
                        return RobotsUnavailableError(f'robots.txt exceeds 256 KB at {display_url(current)}')
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 256_000:
                            return RobotsUnavailableError(f'robots.txt exceeds 256 KB at {display_url(current)}')
                        chunks.append(chunk)
                    body = b''.join(chunks)
                    if b'<html' in body[:512].lower() or b'<!doctype html' in body[:512].lower():
                        return RobotsUnavailableError(f'robots.txt returned an HTML page at {display_url(current)}; permission unknown')
                    parser = RobotFileParser()
                    parser.set_url(origin + '/robots.txt')
                    parser.parse(body.decode('utf-8-sig', errors='replace').splitlines())
                    return parser
            return RobotsUnavailableError(f'robots.txt exceeded redirect limit at {display_url(current)}')
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            return RobotsUnavailableError(f'robots.txt network failure for {display_url(current)}: {type(exc).__name__}')
        except UnsafeTargetError as exc:
            return RobotsUnavailableError(f'robots.txt redirected to unsafe target from {origin}: {exc}')

    async def acquire_turn(self, url: str) -> asyncio.Semaphore:
        """Acquire one host slot; reserve paced request start without global lock."""
        hostname = urlsplit(url).netloc.lower()
        semaphore = self._host_semaphores[hostname]
        await semaphore.acquire()
        try:
            async with self._host_locks[hostname]:
                loop = asyncio.get_running_loop()
                now = loop.time()
                delay = max(0.0, self._next_at.get(hostname, now) - now)
                if delay:
                    await asyncio.sleep(delay)
                self._next_at[hostname] = loop.time() + self.min_interval
            return semaphore
        except BaseException:
            semaphore.release()
            raise
