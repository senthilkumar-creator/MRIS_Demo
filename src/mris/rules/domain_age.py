"""Find how old a domain is, in days."""

from datetime import datetime, timezone
from typing import Optional

import httpx


# Service used to request domain registration information.
RDAP_URL = "https://rdap.org/domain/{domain}"


def age_from_rdap_json(data: dict) -> Optional[int]:
    """Find the registration date and calculate the domain age."""

    # RDAP stores important domain dates in a list called "events".
    events = data.get("events", [])

    for event in events:

        # We only need the registration event.
        if event.get("eventAction") != "registration":
            continue

        registration_date = event.get("eventDate")

        # Skip this event if its date is missing.
        if not registration_date:
            continue

        try:
            # "Z" means UTC. Replace it so Python can read the date.
            registration_date = registration_date.replace("Z", "+00:00")

            # Convert the date text into a Python datetime.
            created = datetime.fromisoformat(registration_date)

            # Without a timezone, we cannot compare the dates safely.
            if created.tzinfo is None:
                continue

            today = datetime.now(timezone.utc)

            # A registration date should not be in the future.
            if created > today:
                continue

            # Subtract the dates and return the number of days.
            age_in_days = (today - created).days

            return age_in_days

        except (ValueError, TypeError, OverflowError):
            # If the date is invalid, check the next event.
            continue

    # None means the domain age is unknown.
    return None


async def lookup_domain_age(
    client: httpx.AsyncClient,
    domain: str,
) -> Optional[int]:
    """Request domain information and return its age."""

    # Remove extra spaces and use lowercase letters.
    domain = domain.strip().lower()

    if not domain:
        return None

    try:
        url = RDAP_URL.format(domain=domain)

        # Request the information.
        # Follow redirects if the service sends us to another address.
        response = await client.get(
            url,
            timeout=5,
            follow_redirects=True,
        )

        # Status 200 means the request succeeded.
        if response.status_code == 200:
            domain_data = response.json()

            return age_from_rdap_json(domain_data)

        return None

    except (httpx.HTTPError, ValueError):
        # Return unknown if the request fails or the response is invalid.
        return None