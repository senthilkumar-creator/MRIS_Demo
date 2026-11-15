
"""Load website content that needs JavaScript."""

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


async def fetch_dynamic_page(url: str, timeout: int = 15000):
    """Open a website in Chromium and return its rendered HTML."""

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)

            try:
                page = await browser.new_page()

                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=timeout
                )

                # Give JavaScript a short time to update the page.
                await page.wait_for_timeout(1500)

                html = await page.content()

                return {
                    "status": "ok" if response is None or response.ok else "http_error",
                    "error": None if response is None or response.ok else f"HTTP {response.status}",
                    "url": page.url,
                    "html": html,
                    "status_code": response.status if response else None
                    }

            finally:
                await browser.close()

    except PlaywrightTimeoutError:
        return {
            "status": "timeout",
            "url": url,
            "html": "",
            "status_code": None,
            "error": "Website took too long to load"
        }

    except Exception as error:
        return {
            "status": "error",
            "url": url,
            "html": "",
            "status_code": None,
            "error": str(error)
        }
