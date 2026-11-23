import asyncio
import httpx

from mris.rules.domain_age import lookup_domain_age

from datetime import datetime, timedelta, timezone

from mris.rules.domain_age import age_from_rdap_json


def test_domain_age_is_100_days():
    """A domain registered 100 days ago should return 100."""

    registration_date = datetime.now(timezone.utc) - timedelta(days=100)

    data = {
        "events": [
            {
                "eventAction": "registration",
                "eventDate": registration_date.isoformat(),
            }
        ]
    }

    assert age_from_rdap_json(data) == 100


def test_missing_registration_date():
    """Without registration information, the age is unknown."""

    data = {"events": []}

    assert age_from_rdap_json(data) is None


def test_invalid_registration_date():
    """An invalid date should return unknown without crashing."""

    data = {
        "events": [
            {
                "eventAction": "registration",
                "eventDate": "invalid-date",
            }
        ]
    }

    assert age_from_rdap_json(data) is None


def test_future_registration_date():
    """A future registration date should return unknown."""

    future_date = datetime.now(timezone.utc) + timedelta(days=10)

    data = {
        "events": [
            {
                "eventAction": "registration",
                "eventDate": future_date.isoformat(),
            }
        ]
    }

    assert age_from_rdap_json(data) is None


def test_date_without_timezone():
    """A date without timezone information should return unknown."""

    data = {
        "events": [
            {
                "eventAction": "registration",
                "eventDate": "2024-01-01T00:00:00",
            }
        ]
    }

    assert age_from_rdap_json(data) is None
def test_successful_domain_lookup():
    """Check that an RDAP response gives the correct domain age."""

    registration_date = datetime.now(timezone.utc) - timedelta(days=100)

    # This creates a pretend RDAP response.
    def fake_response(request):
        return httpx.Response(
            200,
            json={
                "events": [
                    {
                        "eventAction": "registration",
                        "eventDate": registration_date.isoformat(),
                    }
                ]
            },
        )

    async def run_lookup():
        transport = httpx.MockTransport(fake_response)

        async with httpx.AsyncClient(transport=transport) as client:
            return await lookup_domain_age(client, "example.com")

    result = asyncio.run(run_lookup())

    assert result == 100


def test_domain_lookup_timeout():
    """A timeout should return unknown instead of crashing."""

    # This pretends that the RDAP service did not respond in time.
    def fake_timeout(request):
        raise httpx.ReadTimeout("Request timed out", request=request)

    async def run_lookup():
        transport = httpx.MockTransport(fake_timeout)

        async with httpx.AsyncClient(transport=transport) as client:
            return await lookup_domain_age(client, "example.com")

    result = asyncio.run(run_lookup())

    assert result is None