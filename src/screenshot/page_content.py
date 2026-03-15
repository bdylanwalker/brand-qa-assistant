"""Single-session page content extractor.

get_page_content(url) → {screenshot_b64: str, text: str}

Performs one page load (efficient) and returns both the visual screenshot
(base64 PNG) and clean body text for the agent to use in its analysis.
"""

import base64
import logging

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

MAX_HEIGHT_PX = 6000
VIEWPORT_WIDTH = 1440

# Truncate text to avoid overwhelming the context window
MAX_TEXT_CHARS = 15_000


async def get_page_content(url: str) -> dict:
    """Load *url* once and return screenshot + text in a single Playwright session.

    Returns:
        dict with:
            screenshot_b64 (str): base64-encoded PNG
            text (str): clean visible body text (up to MAX_TEXT_CHARS chars)
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
            context = await browser.new_context(
                viewport={"width": VIEWPORT_WIDTH, "height": 900},
                device_scale_factor=1,
            )
            page = await context.new_page()

            logger.info("Loading %s", url)
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await page.wait_for_load_state("domcontentloaded")

            # Measure height, apply cap
            full_height: int = await page.evaluate("document.body.scrollHeight")
            capture_height = min(full_height, MAX_HEIGHT_PX)

            if full_height > MAX_HEIGHT_PX:
                logger.warning(
                    "Page height %dpx exceeds cap %dpx; clipping screenshot.",
                    full_height,
                    MAX_HEIGHT_PX,
                )

            await page.set_viewport_size({"width": VIEWPORT_WIDTH, "height": capture_height})

            # Capture screenshot
            png_bytes: bytes = await page.screenshot(
                full_page=(full_height <= MAX_HEIGHT_PX),
                clip=None if full_height <= MAX_HEIGHT_PX else {
                    "x": 0,
                    "y": 0,
                    "width": VIEWPORT_WIDTH,
                    "height": capture_height,
                },
            )

            # Extract clean body text (strips HTML tags, scripts, styles)
            text: str = await page.inner_text("body")
            if len(text) > MAX_TEXT_CHARS:
                logger.warning(
                    "Body text truncated from %d to %d chars.", len(text), MAX_TEXT_CHARS
                )
                text = text[:MAX_TEXT_CHARS]

            screenshot_b64 = base64.b64encode(png_bytes).decode("ascii")

            logger.info(
                "Page content extracted — screenshot: %d b64 chars, text: %d chars",
                len(screenshot_b64),
                len(text),
            )

            return {"screenshot_b64": screenshot_b64, "text": text}
        finally:
            await browser.close()
