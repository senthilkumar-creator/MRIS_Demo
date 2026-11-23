
import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from mris.scraper.fetcher import fetch_site
from mris.schema import FetchStatus


def test_dynamic_fallback():
    # A website that initially returns very little HTML
    url = "https://example.com"
    short_html = "<html><body>Loading...</body></html>"
    dynamic_html = (
        "<html><body><h1>Merchant website</h1>"
        + "<p>Products and services available.</p>" * 30
        + "</body></html>"
    )

    async def run_test():
        async def fake_response(request):
            return httpx.Response(
                200,
                text=short_html,
                request=request,
            )

        transport = httpx.MockTransport(fake_response)

        async with httpx.AsyncClient(
            transport=transport
        ) as client:
            with patch(
                "mris.scraper.fetcher.fetch_dynamic_page",
                new_callable=AsyncMock,
            ) as mock_dynamic:
                mock_dynamic.return_value = {
                    "status": "ok",
                    "error": None,
                    "url": url,
                    "html": dynamic_html,
                    "status_code": 200,
                }

                result = await fetch_site(client, 1, url)

                assert len(result.pages) >= 1
                assert result.pages[0].html == dynamic_html
                mock_dynamic.assert_awaited_once_with(url)

    asyncio.run(run_test())



def test_dynamic_fallback_timeout():
    url = "https://example.com"
    short_html = "<html><body>Loading...</body></html>"

    async def run_test():
        async def fake_response(request):
            return httpx.Response(
                200,
                text=short_html,
                request=request,
            )

        transport = httpx.MockTransport(fake_response)

        async with httpx.AsyncClient(
            transport=transport
        ) as client:
            with patch(
                "mris.scraper.fetcher.fetch_dynamic_page",
                new_callable=AsyncMock,
            ) as mock_dynamic:
                mock_dynamic.return_value = {
                    "status": "timeout",
                    "error": "Playwright timeout",
                    "url": url,
                    "html": "",
                    "status_code": None,
                }

                result = await fetch_site(client, 1, url)

                assert len(result.pages) == 1
                assert result.pages[0].html == short_html
                assert result.status == FetchStatus.LIMITED_CONTENT
                mock_dynamic.assert_awaited_once_with(url)

    asyncio.run(run_test())
