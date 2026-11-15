
import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from mris.scraper.fetcher import fetch_site
from mris.schema import FetchStatus


def test_dynamic_error():
    async def run_test():
        url = "https://example.com"
        short_html = "<html><body>Loading...</body></html>"

        def fake_response(request):
            return httpx.Response(
                200,
                text=short_html,
                request=request
            )

        transport = httpx.MockTransport(fake_response)

        async with httpx.AsyncClient(
            transport=transport,
            follow_redirects=True
        ) as client:

            with patch(
                "mris.scraper.fetcher.fetch_dynamic_page",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Browser crashed")
            ) as mock_dynamic:

                result = await fetch_site(client, 1, url)

                assert result is not None
                assert len(result.pages) == 1
                assert result.status == FetchStatus.LIMITED_CONTENT
                mock_dynamic.assert_awaited_once_with(url)

                print("Error handling test passed!")

    asyncio.run(run_test())
