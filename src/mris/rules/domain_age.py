"""Domain age via RDAP. Owner: Member 5.

RDAP replaced WHOIS for generic domains (.com, .net ...). Some country domains (e.g. .ca) may not
answer through rdap.org, so None (= unknown) is a normal result and must not crash the pipeline.
TODO (Member 5): test .ca domains, add a WHOIS fallback, cache per domain.
"""
from datetime import datetime, timezone
from typing import Optional
import httpx

RDAP_URL = "https://rdap.org/domain/{domain}"


def age_from_rdap_json(data: dict) -> Optional[int]:
    for ev in data.get("events", []):
        if ev.get("eventAction") == "registration" and ev.get("eventDate"):
            created = datetime.fromisoformat(ev["eventDate"].replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - created).days
    return None


async def lookup_domain_age(client: httpx.AsyncClient, domain: str) -> Optional[int]:
    if not domain:
        return None
    try:
        r = await client.get(RDAP_URL.format(domain=domain), timeout=5)
        if r.status_code == 200:
            return age_from_rdap_json(r.json())
    except Exception:          # noqa: BLE001 - unknown is acceptable
        pass
    return None
