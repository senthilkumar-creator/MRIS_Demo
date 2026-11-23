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

from .batch import process_chunks
from .config import get_config
from .decision.engine import decide
from .llm.analyze import analyze_site
from .processing.clean import clean_site, free_raw_html
from .rules.domain_age import lookup_domain_age
from .rules.engine import run_rules
from .schema import AssessResponse, FetchStatus, LLMResult, SiteResult
from .scraper.fetcher import fetch_site, make_client
from .scraper.policy import CrawlPolicy


async def assess_one(web: httpx.AsyncClient, llm_client: httpx.AsyncClient,
                     site_id: int, url: str, policy: CrawlPolicy | None = None,
                     fetch_sem: asyncio.Semaphore | None = None,
                     llm_sem: asyncio.Semaphore | None = None,
                     domain_age_sem: asyncio.Semaphore | None = None) -> SiteResult:
    """Fetch and LLM stages have separate limits so slow inference cannot occupy fetch slots."""
    if fetch_sem is None:
        site = await fetch_site(web, site_id, url, policy)
    else:
        async with fetch_sem:
            site = await fetch_site(web, site_id, url, policy)
    if site.pages:
        if domain_age_sem is None:
            site.domain_age_days = await lookup_domain_age(web, site.domain)
        else:
            async with domain_age_sem:
                site.domain_age_days = await lookup_domain_age(web, site.domain)
        clean_site(site)
    rules = run_rules(site)
    free_raw_html(site)  # release HTML before entering slower LLM queue
    if site.status == FetchStatus.OK:
        if llm_sem is None:
            llm = await analyze_site(llm_client, site, rules)
        else:
            async with llm_sem:
                llm = await analyze_site(llm_client, site, rules)
    else:
        llm = LLMResult(valid=False, error="skipped")
    return decide(site, rules, llm)


async def assess_urls(urls: List[str]) -> AssessResponse:
    cfg = get_config()
    start = time.perf_counter()
    policy = CrawlPolicy()  # robots and per-host pacing shared across entire batch
    fetch_sem = asyncio.Semaphore(max(1, int(cfg["fetch"]["max_concurrent_sites"])))
    llm_sem = asyncio.Semaphore(max(1, int(cfg["llm"].get("max_concurrent_calls", 6))))
    domain_age_sem = asyncio.Semaphore(max(1, int(cfg["fetch"].get("max_concurrent_domain_age", 8))))
    async with make_client() as web, httpx.AsyncClient() as llm_client:
        async def worker(i: int, url: str) -> SiteResult:
            return await assess_one(web, llm_client, i, url, policy, fetch_sem, llm_sem, domain_age_sem)
        results = await process_chunks(urls, worker, int(cfg["batch"]["chunk_size"]))
    return AssessResponse(count=len(results), elapsed_seconds=round(time.perf_counter() - start, 3), results=results)


def results_to_dataframe(results: List[SiteResult]):
    """One row per site for the CSV output (same fields as the JSON, flattened)."""
    import pandas as pd
    rows = []
    for r in results:
        rows.append({
            "url": r.url,
            "routing_decision": r.routing_decision.value,
            "requires_human_review": r.requires_human_review,
            "mcc": r.industry_classification.mcc,
            "naics": r.industry_classification.naics,
            "industry_description": r.industry_classification.description,
            "industry_confidence": r.industry_classification.confidence_score,
            "product_match": r.product_industry_match.is_match,
            "product_match_confidence": r.product_industry_match.confidence_score,
            "has_working_checkout": r.has_working_checkout,
            "detected_gateways": ";".join(r.detected_gateways),
            **{f"flag_{k}": v for k, v in r.risk_flags.model_dump().items()},
            "domain_age_days": r.business_info.domain_age_days,
            "location": r.business_info.location,
            "review_reasons": " | ".join(r.review_reasons),
            "llm_validation_notes": r.llm_validation_notes,
            "fetch_status": r.fetch_status.value,
        })
    return pd.DataFrame(rows)
