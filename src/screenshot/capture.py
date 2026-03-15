"""Low-level Playwright screenshot capture.

Exposes a single async function: capture_full_page(url) → bytes (PNG).

Container-safe flags: --no-sandbox, --disable-dev-shm-usage.
Screenshot height is capped at 6000px to prevent context window overflow
when passing the image to the AI agent.
"""

import logging
from playwright.async_api import async_playwright, BrowserContext

logger = logging.getLogger(__name__)

# Max height in pixels before we clip the screenshot to avoid huge base64 payloads
MAX_HEIGHT_PX = 6000

# Viewport width that matches a typical desktop monitor
VIEWPORT_WIDTH = 1440


async def capture_full_page(url: str) -> bytes:
    """Return a PNG screenshot of the full page at *url*.

    The page is rendered at 1440px width. If the full page height exceeds
    MAX_HEIGHT_PX, the screenshot is clipped to that height so the base64
    payload stays within practical limits for vision models.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox",
            ]
        )
        try:
            context: BrowserContext = await browser.new_context(
                viewport={"width": VIEWPORT_WIDTH, "height": 900},
                device_scale_factor=1,
            )
            page = await context.new_page()

            logger.info("Navigating to %s", url)
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await page.wait_for_load_state("domcontentloaded")

            # Measure full page height
            full_height: int = await page.evaluate("document.body.scrollHeight")
            capture_height = min(full_height, MAX_HEIGHT_PX)

            if full_height > MAX_HEIGHT_PX:
                logger.warning(
                    "Page height %dpx exceeds cap %dpx; clipping screenshot.",
                    full_height,
                    MAX_HEIGHT_PX,
                )

            # Resize viewport to capture height, then screenshot without full_page
            # (more reliable cross-platform than full_page=True at large heights)
            await page.set_viewport_size({"width": VIEWPORT_WIDTH, "height": capture_height})

            png_bytes: bytes = await page.screenshot(
                full_page=(full_height <= MAX_HEIGHT_PX),
                clip=None if full_height <= MAX_HEIGHT_PX else {
                    "x": 0,
                    "y": 0,
                    "width": VIEWPORT_WIDTH,
                    "height": capture_height,
                },
            )
            logger.info("Screenshot captured (%d bytes)", len(png_bytes))
            return png_bytes
        finally:
            await browser.close()
