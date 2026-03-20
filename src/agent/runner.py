
"""Brand review orchestration.

run_brand_review(url) → dict
  Creates a thread, posts the review request, runs the agent (with manual
  tool-call loop), extracts the JSON result from the final message.
"""

import asyncio
import json
import logging
import re

from azure.ai.agents.models import MessageRole, ToolOutput  # type: ignore
from tenacity import retry, stop_after_attempt, wait_exponential

from src.agent.client import get_client
from src.agent.tools import capture_page_for_review
from src.config import settings

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=30),
    reraise=True,
)
async def run_brand_review(url: str, is_pdf: bool = False) -> dict:
    """Run a full brand compliance review for the given URL.

    Returns a dict matching the schema in src/agent/prompts.py:
        {url, overall, score, findings[], summary}

    Raises on unrecoverable errors after 3 attempts.
    """
    if not settings.agent_id:
        raise RuntimeError(
            "AGENT_ID is not set. Run `python -m src.agent.client bootstrap` first."
        )

    client = get_client()

    thread = client.threads.create()
    logger.info("Created thread %s for URL: %s", thread.id, url)

    if is_pdf:
        content = (
            f"Please review this PDF URL for brand compliance: {url}\n\n"
            "Note: This is a PDF — use capture_page_for_review to extract text only. "
            "Visual review is unavailable for PDFs; note this in your findings."
        )
    else:
        content = f"Please review this URL for brand compliance: {url}"

    client.messages.create(
        thread_id=thread.id,
        role=MessageRole.USER,
        content=content,
    )

    run = await _run_tool_loop(client, thread.id)

    logger.info("Run %s completed with status: %s", run.id, run.status)

    if run.status != "completed":
        last_error = getattr(run, "last_error", None)
        raise RuntimeError(
            f"Agent run ended with status {run.status!r}. last_error: {last_error}"
        )

    # azure-ai-agents 1.x uses MessageRole.AGENT (renamed from ASSISTANT)
    messages = client.messages.list(thread_id=thread.id)
    agent_messages = [m for m in messages if m.role == MessageRole.AGENT]
    if not agent_messages:
        raise RuntimeError("No agent message found in thread after run.")

    raw_text = _extract_text(agent_messages[-1])
    logger.debug("Raw agent output: %s", raw_text[:500])

    return _parse_json(raw_text, url)


async def _run_tool_loop(client, thread_id: str):
    """Create a run and handle tool calls until the run reaches a terminal status."""
    run = client.runs.create(thread_id=thread_id, agent_id=settings.agent_id)

    while run.status in ("queued", "in_progress", "requires_action"):
        if run.status == "requires_action":
            tool_outputs = []
            for tc in run.required_action.submit_tool_outputs.tool_calls:
                output = await _dispatch(tc.function.name, tc.function.arguments)
                tool_outputs.append(ToolOutput(tool_call_id=tc.id, output=output))
            run = client.runs.submit_tool_outputs(
                thread_id,
                run.id,
                tool_outputs=tool_outputs,
            )
        else:
            await asyncio.sleep(2)
            run = client.runs.get(thread_id=thread_id, run_id=run.id)

    return run


async def _dispatch(tool_name: str, arguments_json: str) -> str:
    """Dispatch a tool call and return the output as a JSON string."""
    args = json.loads(arguments_json)
    logger.info("Dispatching tool: %s args: %s", tool_name, args)

    if tool_name == "capture_page_for_review":
        try:
            result = await capture_page_for_review(**args)
            # Exclude screenshot_b64: tool outputs are plain text; the model
            # can't interpret a base64 blob as an image, and it blows the
            # 1 MB API limit.
            return json.dumps({"text": result.get("text", "")})
        except Exception as exc:
            logger.error("Tool %s failed: %s", tool_name, exc, exc_info=True)
            return json.dumps({"error": str(exc), "text": ""})

    logger.warning("Unknown tool called: %s", tool_name)
    return json.dumps({"error": f"Unknown tool: {tool_name}"})


def _extract_text(message) -> str:
    """Pull plain text out of an agents message object."""
    parts = []
    for block in getattr(message, "content", []):
        if hasattr(block, "text"):
            parts.append(block.text.value if hasattr(block.text, "value") else str(block.text))
        elif isinstance(block, str):
            parts.append(block)
    return "\n".join(parts)


def _parse_json(raw: str, url: str) -> dict:
    """Extract and parse the JSON object from the agent's response."""
    match = _JSON_RE.search(raw)
    if not match:
        logger.warning("No JSON found in agent response; returning error dict. Raw: %s", raw[:300])
        return {
            "url": url,
            "overall": "fail",
            "score": 0,
            "findings": [],
            "summary": f"Agent returned an unstructured response. Raw output: {raw[:300]}",
        }

    try:
        return json.loads(match.group())
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse agent JSON: %s\nRaw: %s", exc, raw[:300])
        return {
            "url": url,
            "overall": "fail",
            "score": 0,
            "findings": [],
            "summary": f"Agent response could not be parsed as JSON: {exc}",
        }
