"""HTML parsing helpers (BeautifulSoup). Owner: Member 1 (fetching) / Member 2 (errors, edge cases)."""
from typing import Dict, List
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

# page type -> words that suggest a link points to that page (matched on link text and URL)
PAGE_KEYWORDS: Dict[str, List[str]] = {
    "terms":    ["terms of service", "terms and conditions", "terms & conditions", "terms-of-service", "/terms", "tos"],
    "refund":   ["refund", "return policy", "returns", "exchange"],
    "shipping": ["shipping", "delivery"],
    "contact":  ["contact", "contact-us", "about us", "support"],
    "checkout": ["checkout", "/cart", "basket"],
}


def normalize_url(url: str) -> str:
    """Add https:// when missing and strip whitespace and fragments."""
    url = (url or "").strip()
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    return url.split("#")[0]


def get_domain(url: str) -> str:
    host = urlparse(url).netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def is_valid_url(url: str) -> bool:
    p = urlparse(url)
    return p.scheme in ("http", "https") and "." in p.netloc


def find_page_links(html: str, base_url: str, max_per_type: int = 1) -> Dict[str, List[str]]:
    """Return {page_type: [absolute urls]} for links on the page, same domain only."""
    soup = BeautifulSoup(html, "lxml")
    base_domain = get_domain(base_url)
    found: Dict[str, List[str]] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = urljoin(base_url, href).split("#")[0]
        if get_domain(absolute) != base_domain:
            continue
        label = (a.get_text(" ", strip=True) + " " + href).lower()
        for ptype, words in PAGE_KEYWORDS.items():
            if any(w in label for w in words):
                lst = found.setdefault(ptype, [])
                if absolute not in lst and len(lst) < max_per_type:
                    lst.append(absolute)
                break
    return found


def visible_text(html: str) -> str:
    """Cleaned visible text (no scripts, styles, nav). Member 5 owns improvements."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return " ".join(text.split())
