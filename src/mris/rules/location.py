"""Declared business location (first version). Owner: Member 2.

Looks for "City, PROVINCE" (Canada) or "City, ST 12345" (US) in the contact page first, then the home page.
TODO (Member 2): postal codes, country names, schema.org address markup, non-English addresses.
"""
import re
from typing import Optional
from ..schema import SiteData

CA_PROV = "AB|BC|MB|NB|NL|NS|NT|NU|ON|PE|QC|SK|YT"
CITY = r"[A-Z][a-z.'\-]+(?: [A-Z][a-z.'\-]+)?"       # one or two capitalised words
CA_RE = re.compile(rf"({CITY}),?\s+({CA_PROV})\b")
US_RE = re.compile(rf"({CITY}),\s+([A-Z]{{2}})\s+\d{{5}}\b")


def detect_location(site: SiteData) -> Optional[str]:
    order = sorted(site.pages, key=lambda p: 0 if p.page_type == "contact" else 1)
    for page in order:
        text = page.text or page.html
        m = CA_RE.search(text)
        if m:
            return f"{m.group(1).strip()}, {m.group(2)}, Canada"
        m = US_RE.search(text)
        if m:
            return f"{m.group(1).strip()}, {m.group(2)}, USA"
    return None
