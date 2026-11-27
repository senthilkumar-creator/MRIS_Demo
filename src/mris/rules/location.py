
"""Extract declared business locations from merchant websites."""

import json
import re
from typing import Optional

from bs4 import BeautifulSoup

from ..schema import SiteData


CA_PROV = "AB|BC|MB|NB|NL|NS|NT|NU|ON|PE|QC|SK|YT"

US_STATES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|"
    "LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|"
    "OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"
)

CITY = r"[A-Z][a-z.'\-]+(?: [A-Z][a-z.'\-]+){0,2}"
CA_POSTAL = r"[A-Z]\d[A-Z]\s?\d[A-Z]\d"
US_ZIP = r"\d{5}(?:-\d{4})?"

STREET = (
    r"\d+\s+[A-Za-z0-9.'\- ]{1,60}?\s+"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|"
    r"Boulevard|Blvd|Lane|Ln|Way|Court|Ct)\.?"
)

CA_RE = re.compile(
    rf"(?:(?P<street>{STREET})\s*,?\s+)?"
    rf"(?P<city>{CITY}),?\s+(?P<region>{CA_PROV})\b"
    rf"(?:\s+(?P<postal>{CA_POSTAL}))?"
)

US_RE = re.compile(
    rf"(?:(?P<street>{STREET})\s*,?\s+)?"
    rf"(?P<city>{CITY}),\s+(?P<region>{US_STATES})"
    rf"\s+(?P<postal>{US_ZIP})\b"
)


def format_address(address: dict) -> Optional[str]:
    """Format structured address fields."""

    city = address.get("addressLocality")
    street = address.get("streetAddress")

    if not city and not street:
        return None

    country = address.get("addressCountry", "")

    if isinstance(country, dict):
        country = country.get("name", "")

    country = {
        "CA": "Canada",
        "US": "USA",
        "United States": "USA",
        "GB": "United Kingdom",
    }.get(str(country), country)

    parts = [
        street,
        city,
        address.get("addressRegion"),
        address.get("postalCode"),
        country,
    ]

    return ", ".join(
        str(part).strip() for part in parts if part
    )


def find_structured_address(data) -> Optional[str]:
    """Search JSON-LD data for a postal address."""

    if isinstance(data, dict):
        address_type = data.get("@type") or ""

        if "PostalAddress" in address_type:
            result = format_address(data)

            if result:
                return result

        address = data.get("address")

        if isinstance(address, dict):
            result = format_address(address)

            if result:
                return result

        for value in data.values():
            result = find_structured_address(value)

            if result:
                return result

    elif isinstance(data, list):
        for item in data:
            result = find_structured_address(item)

            if result:
                return result

    return None


def detect_location(site: SiteData) -> Optional[str]:
    """Detect declared addresses, prioritizing contact pages."""

    priority = {"contact": 0, "home": 1}

    pages = sorted(
        site.pages,
        key=lambda page: priority.get(page.page_type, 2),
    )

    for page in pages:
        soup = BeautifulSoup(
            page.html or "", "html.parser"
        )

        # Check structured address information.
        for script in soup.find_all(
            "script", type="application/ld+json"
        ):
            try:
                data = json.loads(script.get_text())
                result = find_structured_address(data)

                if result:
                    return result

            except (ValueError, TypeError):
                continue

        # Remove scripts and styles from HTML.
        for tag in soup(["script", "style"]):
            tag.decompose()

        # Use cleaned text or extract visible HTML text.
        text = page.text or soup.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()

        # Check Canadian and US addresses.
        for pattern, country in [
            (US_RE, "USA"),
            (CA_RE, "Canada"),
        ]:
            match = pattern.search(text)

            if match:
                parts = [
                    match.group("street"),
                    match.group("city"),
                    match.group("region"),
                    match.group("postal"),
                    country,
                ]

                return ", ".join(
                    part.strip() for part in parts if part
                )

    return None
