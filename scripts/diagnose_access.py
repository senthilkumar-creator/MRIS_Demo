r"""Diagnose crawler access without bypassing robots.txt or bot protections.

Windows (inside repository root):
    .\.venv\Scripts\python.exe scripts\diagnose_access.py https://example.com https://www.python.org

Only checks the supplied public websites. It uses the same fetcher and settings as
MRIS's API, and reports whether errors reflect robots policy or connectivity.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from mris.config import get_config  # noqa: E402
from mris.schema import FetchStatus  # noqa: E402
from mris.scraper.fetcher import fetch_site, make_client  # noqa: E402
from mris.scraper.policy import CrawlPolicy, display_url  # noqa: E402

DEFAULT_URLS = ['https://example.com', 'https://www.python.org', 'https://www.wikipedia.org']


async def diagnose(urls: list[str]) -> None:
    cfg = get_config()['fetch']
    print('MRIS Crawler Access Diagnostics')
    print('-' * 58)
    print('User-Agent:         ', cfg['user_agent'])
    print('Respect robots.txt: ', os.getenv('MRIS_RESPECT_ROBOTS', str(cfg.get('respect_robots', True))))
    print('Robots timeout:     ', cfg.get('robots_timeout_seconds', 6), 'seconds')
    trust_env = os.getenv('MRIS_TRUST_ENV', '0').lower() in {'1', 'yes', 'true', 'on'}
    print('Use proxy env vars: ', 'yes (MRIS_TRUST_ENV=1)' if trust_env else 'no (default)')
    proxy = any(os.getenv(name) for name in ('HTTPS_PROXY', 'HTTP_PROXY', 'ALL_PROXY'))
    if proxy and not trust_env:
        print('NOTE: Proxy environment variables are configured but not used by this scraper.')
    print('')
    statuses = Counter()
    policy = CrawlPolicy()
    async with make_client() as client:
        for i, url in enumerate(urls, start=1):
            site = await fetch_site(client, i, url, policy)
            statuses[site.status.value] += 1
            print(f'[{i}/{len(urls)}] {display_url(url)}')
            print(f'  Status: {site.status.value}  Pages: {len(site.pages)}  Duration: {site.elapsed_seconds}s')
            if site.error:
                print(f'  Reason: {site.error}')
            if site.pages:
                print('  Fetched: ' + display_url(site.pages[0].url))
            if site.status == FetchStatus.ROBOTS_UNAVAILABLE:
                print('  Action: Check DNS, firewall, proxy, TLS and robots.txt response; crawler did not proceed.')
            elif site.status == FetchStatus.BLOCKED:
                print('  Action: Access was denied; do not bypass site restrictions.')
            print('')
    print('Summary:', ', '.join(f'{count} {status}' for status, count in statuses.items()))
    if not statuses.get('ok') and not statuses.get('limited_content'):
        print('No URLs succeeded. If failures are ROBOTS_UNAVAILABLE, investigate connectivity first.')
        print('If failures are BLOCKED, the target sites may explicitly restrict automated access.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('urls', nargs='*', default=DEFAULT_URLS, help='Public website URLs to check (defaults to 3 examples)')
    args = parser.parse_args()
    asyncio.run(diagnose(args.urls))
