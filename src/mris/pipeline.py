"""Batch pipeline: URLs in -> list of SiteResult out. Owner: Member 1 (concurrency) with all members.

Per site:  fetch -> domain age -> clean -> rules -> LLM -> decision.
Sites run concurrently (limited by fetch.max_concurrent_sites) in chunks (batch.chunk_size) so memory
stays flat on the 10,000-site run.
TODO (Member 1): measure time per stage; try different concurrency; cache repeated domains.
"""
import asyncio
import time
from typing import List

import httpx

from .config import get_config
from .decision.engine import decide
from .llm.analyze import analyze_site
from .processing.clean import clean_site, free_raw_html
from .rules.domain_age import lookup_domain_age
from .rules.engine import run_rules
from .schema import AssessResponse, FetchStatus, LLMResult, SiteResult
from .scraper.fetcher import fetch_site, make_client


async def assess_one(web: httpx.AsyncClient, llm_client: httpx.AsyncClient, site_id: int, url: str) -> SiteResult:
    site = await fetch_site(web, site_id, url)
    if site.pages:
        site.domain_age_days = await lookup_domain_age(web, site.domain)
        clean_site(site)
    rules = run_rules(site)
    free_raw_html(site)                       # raw HTML no longer needed after the rules ran
    llm = await analyze_site(llm_client, site) if site.status == FetchStatus.OK else LLMResult(valid=False, error="skipped")
    return decide(site, rules, llm)


async def assess_urls(urls: List[str]) -> AssessResponse:
    cfg = get_config()
    start = time.perf_counter()
    sem = asyncio.Semaphore(cfg["fetch"]["max_concurrent_sites"])
    results: List[SiteResult] = []
    chunk = cfg["batch"]["chunk_size"]

    async with make_client() as web, httpx.AsyncClient() as llm_client:
        async def guarded(i: int, url: str) -> SiteResult:
            async with sem:
                return await assess_one(web, llm_client, i, url)

        for lo in range(0, len(urls), chunk):
            part = urls[lo: lo + chunk]
            results.extend(await asyncio.gather(*[guarded(lo + i, u) for i, u in enumerate(part)]))
    return AssessResponse(count=len(results), elapsed_seconds=round(time.perf_counter() - start, 3), results=results)


def results_to_dataframe(results: List[SiteResult]):
    """One row per site for the CSV output."""
    import pandas as pd
    rows = []
    for r in results:
        rows.append({
            "url": r.url, "decision": r.decision.value, "mcc": r.mcc, "naics": r.naics, "industry": r.industry,
            **{f"flag_{k}": v for k, v in r.flags.items()},
            "fetch_status": r.fetch_status.value, "reasons": " | ".join(r.reasons), "seconds": r.elapsed_seconds,
        })
    return pd.DataFrame(rows)
