"""Show what the scraper actually received for ONE site and why the Terms / contact rules answered as they did.

Usage:  python scripts/debug_site.py 2dehands.be
Prints the evidence (with surrounding text) and saves the fetched HTML to data/debug_<domain>.html so you can
open it in a text editor or browser and search it (Ctrl+F) to compare with what you see on the live site.
"""
import asyncio
import os
import sys

os.environ["MRIS_LLM_MODE"] = "mock"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mris.processing.clean import clean_site
from mris.rules.policy import contact_evidence, terms_evidence
from mris.scraper.fetcher import fetch_site, make_client


async def main(url: str) -> None:
    async with make_client() as web:
        site = await fetch_site(web, 0, url)
    clean_site(site)
    print(f"fetch status: {site.status.value}  error: {site.error}  pages fetched: {len(site.pages)}")
    for p in site.pages:
        print(f"  - {p.page_type:9} {p.url}  ({len(p.html)} chars of HTML)")
    print("\nTerms evidence  :", terms_evidence(site))
    print("Contact evidence:", contact_evidence(site))
    os.makedirs("data", exist_ok=True)
    for i, p in enumerate(site.pages):
        path = f"data/debug_{site.domain or 'site'}_{i}_{p.page_type}.html"
        with open(path, "w", encoding="utf-8") as f:
            f.write(p.html)
        print("saved", path)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1])) if len(sys.argv) > 1 else print(__doc__)
