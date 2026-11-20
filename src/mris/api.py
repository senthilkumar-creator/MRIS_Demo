"""MRIS API: existing /assess, separate /scrape, docs, and local browser UI."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .pipeline import assess_urls, results_to_dataframe
from .schema import AssessRequest, AssessResponse
from .scraper.parser import normalize_url
from .scraper.service import ScrapeRequest, ScrapeResponse, scrape_urls

app = FastAPI(title="MRIS - Merchant Risk Intelligence System", version="0.2.0",
              description="RiskLens AI — merchant scraper, crawler and risk assessment API")
DASHBOARD = Path(__file__).resolve().parent / "ui" / "dashboard"
app.mount("/assets", StaticFiles(directory=str(DASHBOARD)), name="dashboard-assets")


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/ui")


@app.get("/ui", include_in_schema=False)
def dashboard():
    return FileResponse(DASHBOARD / "index.html", media_type="text/html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _clean_urls(urls: list[str]) -> list[str]:
    seen, out = set(), []
    for u in urls:
        value = str(u or "").strip()
        key = normalize_url(value)
        if key and key not in seen:
            seen.add(key)
            out.append(value)
    return out


@app.post("/scrape", response_model=ScrapeResponse, tags=["Scraper"])
async def scrape(req: ScrapeRequest):
    """Fetch HTML/text and discover scripts/policy links without LLM assessment."""
    return await scrape_urls(req)


@app.post("/assess", response_model=AssessResponse, tags=["Assessment"])
async def assess(req: AssessRequest, format: Literal["json", "csv"] = Query("json")):
    """Existing team assessment contract; CSV output via ?format=csv."""
    response = await assess_urls(_clean_urls(req.urls))
    if format == "csv":
        return PlainTextResponse(results_to_dataframe(response.results).to_csv(index=False),
                                 media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=mris_assessment.csv"})
    return response
