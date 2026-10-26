"""FastAPI service. Owner: Member 1 (endpoint) / Member 2 (output formats).

Run:   uvicorn mris.api:app --reload --app-dir src
Docs:  http://localhost:8000/docs
"""
from typing import Literal
from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse

from .pipeline import assess_urls, results_to_dataframe
from .schema import AssessRequest, AssessResponse
from .scraper.parser import normalize_url

app = FastAPI(title="MRIS - Merchant Risk Intelligence System", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _clean_urls(urls):
    seen, out = set(), []
    for u in urls:
        n = normalize_url(u)
        key = n.lower().rstrip("/")
        if key and key not in seen:
            seen.add(key)
            out.append(u.strip())
    return out


@app.post("/assess", response_model=AssessResponse)
async def assess(req: AssessRequest, format: Literal["json", "csv"] = Query("json")):
    """Assess a list of merchant URLs. Use ?format=csv for a CSV download."""
    response = await assess_urls(_clean_urls(req.urls))
    if format == "csv":
        csv_text = results_to_dataframe(response.results).to_csv(index=False)
        return PlainTextResponse(csv_text, media_type="text/csv")
    return response
