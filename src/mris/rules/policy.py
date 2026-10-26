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
