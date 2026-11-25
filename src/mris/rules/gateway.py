"""Payment gateway and checkout detection. Owner: Member 3.

First working version: substring search of the page HTML against config/gateway_signatures.yaml.
TODO (Member 3): test on 20+ real sites, add iframe/form-action checks, reduce false positives.
"""
from typing import List, Tuple
from ..config import get_signatures
from ..schema import SiteData

from bs4 import BeautifulSoup

# def detect_gateways(site: SiteData) -> List[str]:
#     sigs = get_signatures()["gateways"]
#     html = " ".join(p.html.lower() for p in site.pages)
#     return sorted(name for name, needles in sigs.items() if any(n in html for n in needles))

def detect_gateways(site: SiteData) -> List[str]:
    """Find configured payment signatures in HTML integration elements."""
    signatures = get_signatures()["gateways"]
    evidence = []

    for page in site.pages:
        soup = BeautifulSoup(page.html, "html.parser")

        # Scripts, embedded frames, and forms can point to an integration.
        for element in soup.select("script[src], iframe[src], form[action]"):
            attribute = "action" if element.name == "form" else "src"
            evidence.append(element[attribute].lower())

        # Embedded widgets can also use provider-specific HTML markers.
        for element in soup.select("[data-stripe], [class], [id]"):
            if element.has_attr("data-stripe"):
                evidence.append("data-stripe")
            evidence.extend(marker.lower() for marker in element.get("class", []))
            if element.has_attr("id"):
                evidence.append(element["id"].lower())

    return sorted(
        provider
        for provider, patterns in signatures.items()
        if any(pattern in value for pattern in patterns for value in evidence)
    )


# def detect_checkout(site: SiteData) -> bool:
#     """True if the site looks able to take payments (cart or checkout elements)."""
#     sig = get_signatures()["checkout_signals"]
#     text = " ".join((p.text or p.html).lower() for p in site.pages)
#     has_cart = any(w in text for w in sig["cart_words"])
#     has_checkout = any(w in text for w in sig["checkout_words"]) or any(p.page_type == "checkout" for p in site.pages)
#     has_payment_frame = "<iframe" in " ".join(p.html.lower() for p in site.pages) and "pay" in " ".join(p.html.lower() for p in site.pages)
#     return has_cart or has_checkout or has_payment_frame

def detect_checkout(site: SiteData) -> bool:
    """Detect checkout pages and usable cart or checkout controls."""
    signals = get_signatures()["checkout_signals"]
    checkout_labels = set(signals["cart_words"] + signals["checkout_words"])

    for page in site.pages:
        if page.page_type == "checkout":
            return True

        soup = BeautifulSoup(page.html, "html.parser")

        # Check labels on links, buttons, and submit inputs.
        for control in soup.select("a[href], button, input[type=submit]"):
            if control.has_attr("disabled") or control.get("aria-disabled") == "true":
                continue

            if control.name == "input":
                label = control.get("value", "")
            else:
                label = control.get_text(" ")

            normalized_label = " ".join(label.lower().split())
            if normalized_label in checkout_labels:
                return True

    return False


def restricted_keyword_hits(site: SiteData) -> List[str]:
    words = get_signatures()["restricted_keywords"]
    text = " ".join((p.text or p.html).lower() for p in site.pages)
    return sorted(w for w in words if w in text)
