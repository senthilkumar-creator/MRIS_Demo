"""OPTIONAL JavaScript rendering of thin pages using an isolated Chromium browser.

Disabled by default in config. This is a fallback, not a way to bypass access controls.
"""
from __future__ import annotations

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from .policy import validate_target


async def fetch_dynamic_page(url: str, timeout: int = 15000):
    """Render a public webpage; gracefully report missing browser installations."""
    try:
        await validate_target(url)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(service_workers="block", accept_downloads=False)
                page = await context.new_page()

                async def guard(route):
                    # Browser redirects and subresource requests must not access
                    # localhost, cloud metadata or non-public network endpoints.
                    try:
                        await validate_target(route.request.url)
                    except Exception:
                        await route.abort()
                    else:
                        await route.continue_()

                await page.route("**/*", guard)
                response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                await page.wait_for_timeout(900)
                html = await page.content()
                return {
                    "status": "ok" if response is None or response.ok else "http_error",
                    "error": None if response is None or response.ok else f"HTTP {response.status}",
                    "url": page.url,
                    "html": html,
                    "status_code": response.status if response else None,
                }
            finally:
                await browser.close()
    except PlaywrightTimeoutError:
        return {"status": "timeout", "url": url, "html": "", "status_code": None, "error": "Browser rendering timed out"}
    except Exception as error:
        return {"status": "error", "url": url, "html": "", "status_code": None,
                "error": f"Browser rendering unavailable: {type(error).__name__}"}
