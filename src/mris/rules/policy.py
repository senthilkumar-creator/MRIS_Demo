"""Terms of Service and contact-information detection. Owner: Member 4.

First working version: a ToS page was found (page type "terms") or the home page text mentions terms;
contact = email, phone or a contact page.
TODO (Member 4): handle footers, multi-language sites, "terms" inside images, address detection.
"""
import re
from ..schema import SiteData

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(\+?\d[\d\-\s().]{8,}\d)")


def has_terms(site: SiteData) -> bool:
    if any(p.page_type == "terms" for p in site.pages):
        return True
    text = " ".join((p.text or p.html).lower() for p in site.pages)
    return "terms of service" in text or "terms and conditions" in text or "terms & conditions" in text


def has_contact(site: SiteData) -> bool:
    if any(p.page_type == "contact" for p in site.pages):
        return True
    blob = " ".join(p.html for p in site.pages)
    return bool(EMAIL_RE.search(blob)) or bool(PHONE_RE.search(" ".join(p.text for p in site.pages)))


REFUND_RE = re.compile(r"\b(refund\w*|returns|return policy|returned items?|money[- ]back|exchange policy)\b", re.I)
DELIVERY_RE = re.compile(r"\b(ship|ships|shipping|shipped|deliver|delivers|delivery|delivered|arrive|arrives)\b", re.I)


def _all_text(site: SiteData) -> str:
    return " ".join((p.text or p.html).lower() for p in site.pages)


def refund_text_found(site: SiteData) -> bool:
    """True if the site mentions refunds / returns anywhere. False means the policy is missing (a certain
    answer, so no LLM is needed for this flag)."""
    return any(p.page_type == "refund" for p in site.pages) or bool(REFUND_RE.search(_all_text(site)))


def delivery_text_found(site: SiteData) -> bool:
    return any(p.page_type == "shipping" for p in site.pages) or bool(DELIVERY_RE.search(_all_text(site)))
