"""Offline, deterministic crawler benchmark using a local mock merchant transport.

This measures architecture overhead and worker limits, not live-site speed.
Run:  python scripts/benchmark_scraper.py --sites 100
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mris.config import get_config
from mris.scraper.service import ScrapeRequest, scrape_urls

HTML = ('<html><head><title>Fixture merchant</title></head><body><h1>Welcome to our merchant store</h1>'
        + '<p>We have unique electronic goods for sale with returns and delivery available.</p>' * 24 + '</body></html>')


async def main(count: int, concurrent: int) -> None:
    os.environ.update(MRIS_ALLOW_PRIVATE_NETWORKS='1', MRIS_SKIP_DNS_CHECK='1', MRIS_RESPECT_ROBOTS='0')
    cfg = get_config()
    old = cfg['fetch']['max_concurrent_sites']
    cfg['fetch']['max_concurrent_sites'] = concurrent
    active, peak = 0, 0

    async def handler(request: httpx.Request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)  # mock a 20ms network response
        active -= 1
        return httpx.Response(200, text=HTML)

    def client():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    urls = [f'https://merchant-{n}.example.com/' for n in range(count)]
    try:
        start = time.perf_counter()
        with patch('mris.scraper.service.make_client', client):
            data = (await scrape_urls(ScrapeRequest(urls=urls))).count if count <= 250 else await benchmark_large(urls)
        elapsed = time.perf_counter() - start
        print(f'OFFLINE MOCK BENCHMARK: {data} sites, {elapsed:.3f}s, max in-flight requests {peak}, configured workers {concurrent}')
        print('NOTE: This is NOT the 100-real-websites/60-second acceptance benchmark, and excludes RDAP/LLM latency.')
    finally:
        cfg['fetch']['max_concurrent_sites'] = old


async def benchmark_large(urls: list[str]) -> int:
    for start in range(0, len(urls), 250):
        response = await scrape_urls(ScrapeRequest(urls=urls[start:start + 250]))
        if response.failed:
            raise RuntimeError(f'{response.failed} failed in batch')
    return len(urls)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--sites', type=int, default=100)
    p.add_argument('--workers', type=int, default=30)
    args = p.parse_args()
    asyncio.run(main(args.sites, args.workers))
