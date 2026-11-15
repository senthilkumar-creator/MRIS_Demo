
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from mris.scraper.fetcher import fetch_site


async def main():
    test_file = Path("javascript_test.html").resolve()
    url = test_file.as_uri()

    # Simulate a website returning very little HTML
    short_html = "<html><body>Loading...</body></html>"

    async def fake_response(request):
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
            new_callable=AsyncMock
        ) as mock_dynamic:

            # Use the real Playwright handler
            from mris.scraper.dynamic_handler import fetch_dynamic_page
            async def local_dynamic_handler(_):
                return await fetch_dynamic_page(url)
            
            mock_dynamic.side_effect = local_dynamic_handler

            result = await fetch_site(
                client,
                1,
                "https://example.com"
            )

            print("Status:", result.status)
            print("Pages found:", len(result.pages))
            print("Error:", result.error)

            if result.pages:
                print("HTML length:", len(result.pages[0].html))

            print("Fallback called:", mock_dynamic.called)

            if result.pages:
                
                print(
                    "JavaScript content found:",
                    "Merchant sells electronics" in result.pages[0].html
                    )


if __name__ == "__main__":
    asyncio.run(main())
