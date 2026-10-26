"""Payment gateway and checkout detection. Owner: Member 3.

First working version: substring search of the page HTML against config/gateway_signatures.yaml.
TODO (Member 3): test on 20+ real sites, add iframe/form-action checks, reduce false positives.
"""
from typing import List, Tuple
from ..config import get_signatures
from ..schema import SiteData


def detect_gateways(site: SiteData) -> List[str]:
    sigs = get_signatures()["gateways"]
    html = " ".join(p.html.lower() for p in site.pages)
    return sorted(name for name, needles in sigs.items() if any(n in html for n in needles))


def detect_checkout(site: SiteData) -> bool:
    """True if the site looks able to take payments (cart or checkout elements)."""
    sig = get_signatures()["checkout_signals"]
    text = " ".join((p.text or p.html).lower() for p in site.pages)
    has_cart = any(w in text for w in sig["cart_words"])
    has_checkout = any(w in text for w in sig["checkout_words"]) or any(p.page_type == "checkout" for p in site.pages)
    has_payment_frame = "<iframe" in " ".join(p.html.lower() for p in site.pages) and "pay" in " ".join(p.html.lower() for p in site.pages)
    return has_cart or has_checkout or has_payment_frame


def restricted_keyword_hits(site: SiteData) -> List[str]:
    words = get_signatures()["restricted_keywords"]
    text = " ".join((p.text or p.html).lower() for p in site.pages)
    return sorted(w for w in words if w in text)
