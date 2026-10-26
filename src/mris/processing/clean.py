"""ETL step: clean pages and fill Page.text. Owner: Member 5 (cleaning) / Member 2 (transform)."""
from ..schema import SiteData
from ..scraper.parser import visible_text


def clean_site(site: SiteData) -> SiteData:
    """Fill in cleaned visible text for each page."""
    for page in site.pages:
        page.text = visible_text(page.html) if page.html else ""
    return site


def free_raw_html(site: SiteData) -> SiteData:
    """Drop raw HTML after rules have run, so memory stays flat on large runs.
    NOTE: rules need the HTML (script/iframe signatures), so call this AFTER rule detection."""
    for page in site.pages:
        page.html = ""
    return site


def text_for_llm(site: SiteData, max_chars: int) -> str:
    """Join page texts with headers, home page first, and cut to the character budget."""
    parts, budget = [], max_chars
    for page in site.pages:
        if not page.text or budget <= 0:
            continue
        chunk = page.text[: max(500, budget // 2)] if page.page_type == "home" else page.text[: max(400, budget // 4)]
        parts.append(f"[{page.page_type.upper()} PAGE]\n{chunk}")
        budget -= len(chunk)
    return "\n\n".join(parts)[:max_chars]
