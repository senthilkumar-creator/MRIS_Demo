"""URL hygiene, merchant-page link discovery and HTML extraction."""
from __future__ import annotations

from typing import Dict, List
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

PAGE_KEYWORDS: Dict[str, List[str]] = {
    "terms": ["terms of service", "terms and conditions", "terms & conditions", "terms-of-service", "/terms", "tos"],
    "refund": ["refund", "return policy", "returns", "exchange"],
    "shipping": ["shipping", "delivery"],
    "contact": ["contact", "contact-us", "about us", "support"],
    "checkout": ["checkout", "/cart", "basket"],
}


def normalize_url(url: str) -> str:
    """Use HTTPS when omitted, remove fragments; keep paths and query strings."""
    value = (url or "").strip()
    if not value:
        return ""
    if "://" not in value and not value.startswith(("//", "mailto:", "javascript:", "data:", "file:")):
        value = "https://" + value
    try:
        parts = urlsplit(value)
        return urlunsplit((parts.scheme.lower(), parts.netloc, parts.path, parts.query, ""))
    except ValueError:
        return ""


def get_domain(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""
    return host.removeprefix("www.")


def is_valid_url(url: str) -> bool:
    try:
        p = urlsplit(url)
        host = p.hostname or ""
        port = p.port  # reject malformed ports
        return bool(
            p.scheme in ("http", "https")
            and host
            and ("." in host or host == "localhost")
            and not p.username and not p.password
            and not any(x.isspace() for x in url)
            and (port is None or 0 < port <= 65535)
        )
    except ValueError:
        return False


def find_page_links(html: str, base_url: str, max_per_type: int = 1) -> Dict[str, List[str]]:
    """Discover only same-host public policy, contact and checkout links."""
    soup = BeautifulSoup(html, "lxml")
    base_host = (urlsplit(base_url).hostname or "").lower()
    found: Dict[str, List[str]] = {}
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        if not href or href.lower().startswith(("mailto:", "tel:", "javascript:", "data:", "#")):
            continue
        absolute = normalize_url(urljoin(base_url, href))
        if not is_valid_url(absolute) or (urlsplit(absolute).hostname or "").lower() != base_host:
            continue
        label = (anchor.get_text(" ", strip=True) + " " + href).lower()
        for kind, words in PAGE_KEYWORDS.items():
            if any(word in label for word in words):
                pages = found.setdefault(kind, [])
                if absolute not in pages and len(pages) < max_per_type:
                    pages.append(absolute)
                break
    return found


def visible_text(html: str) -> str:
    """Remove scripts, navigation and non-visible content while preserving copy."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "template", "head"]):
        tag.decompose()
    for tag in soup.select('[hidden], [aria-hidden="true"], [style*="display:none"], [style*="display: none"]'):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())
