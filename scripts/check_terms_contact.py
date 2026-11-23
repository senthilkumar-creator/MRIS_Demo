"""Fetch some real URLs, run the Terms/contact rules and write a sheet for checking the Terms of Service and contact flags by hand.

Usage (from the project folder, venv active):
    python scripts/check_terms_contact.py data/urls_sample.csv 30
Arguments: the CSV of URLs (header "url"), and how many to check (default 30; takes the first N).

Only the scraper and the Terms/contact rules run (no LLM). The evidence columns say WHY each answer was given.
Output: data/terms_contact_check.csv. Open it in Excel, visit each site, fill the two "my_" columns with
yes / no, then run:  python scripts/check_terms_contact.py --score data/terms_contact_check.csv
"""
import os
import sys

os.environ["MRIS_LLM_MODE"] = "mock"                       # must be set before mris is imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import asyncio
import pandas as pd
from mris.processing.clean import clean_site
from mris.rules.policy import contact_evidence, terms_evidence
from mris.scraper.fetcher import fetch_site, make_client

OUT = "data/terms_contact_check.csv"


async def _check(web, i: int, url: str, sem):
    async with sem:
        site = await fetch_site(web, i, url)
    clean_site(site)
    ok = site.status.value in ("ok", "limited_content")
    t, c = terms_evidence(site), contact_evidence(site)
    return {
        "url": url,
        "fetch_status": site.status.value,
        "pipeline_has_terms": ("yes" if t else "no") if ok else "n/a",
        "pipeline_has_contact": ("yes" if c else "no") if ok else "n/a",
        "terms_evidence": t or "", "contact_evidence": c or "",
        "my_has_terms": "", "my_has_contact": "", "notes": "",
    }


async def _run_all(urls):
    sem = asyncio.Semaphore(10)
    async with make_client() as web:
        return await asyncio.gather(*[_check(web, i, u, sem) for i, u in enumerate(urls)])


def run(csv_path: str, n: int) -> None:
    urls = pd.read_csv(csv_path)["url"].dropna().astype(str).tolist()[:n]
    rows = asyncio.run(_run_all(urls))
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"Wrote {OUT} ({len(rows)} sites). Fill in the my_ columns, then run --score.")


def score(path: str) -> None:
    df = pd.read_csv(path).fillna("")
    for name in ("terms", "contact"):
        d = df[df[f"my_has_{name}"].isin(["yes", "no"]) & df["fetch_status"].isin(["ok", "limited_content"])]
        pipe, mine = d[f"pipeline_has_{name}"], d[f"my_has_{name}"]
        wrong_present = d[(pipe == "yes") & (mine == "no")]       # pipeline said present, it is really absent
        wrong_absent = d[(pipe == "no") & (mine == "yes")]        # pipeline said absent, it is really present
        print(f"\n{name.upper()}: {len(d)} sites checked, {(pipe == mine).sum()} correct")
        print(f"  wrongly 'present' (risky: missed a problem): {len(wrong_present)}  {list(wrong_present['url'])}")
        print(f"  wrongly 'absent'  (extra human review):      {len(wrong_absent)}  {list(wrong_absent['url'])}")
    skipped = df[~df["fetch_status"].isin(["ok", "limited_content"])]
    if len(skipped):
        print(f"\nNot scored (page could not be fetched properly): {len(skipped)} sites")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--score":
        score(sys.argv[2])
    elif len(sys.argv) > 1:
        run(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 30)
    else:
        print(__doc__)
