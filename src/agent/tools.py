"""Agent tool definitions.

The agent has one custom tool: `capture_page_for_review`.
Azure AI Agents handles `file_search` natively as a built-in tool.
"""

import asyncio
import logging

from src.screenshot.page_content import get_page_content

logger = logging.getLogger(__name__)

# JSON Schema definition consumed by the Agents SDK FunctionTool
CAPTURE_PAGE_TOOL_DEFINITION = {
    "name": "capture_page_for_review",
    "description": (
        "Loads the given URL in a headless browser, captures a full-page screenshot, "
        "and extracts the visible body text. Returns both for brand compliance analysis. "
        "Always call this first before any other analysis."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The fully-qualified URL to review (must start with http:// or https://).",
            }
        },
        "required": ["url"],
    },
}


async def capture_page_for_review(url: str) -> dict:
    """Execute the page capture tool call.

    Returns:
        dict with keys:
            screenshot_b64 (str): base64-encoded PNG of the full page
            text (str): clean visible body text
    """
    logger.info("Capturing page for review: %s", url)
    result = await get_page_content(url)
    logger.info(
        "Capture complete — screenshot size: %d chars (b64), text length: %d chars",
        len(result["screenshot_b64"]),
        len(result["text"]),
    )
    return result

