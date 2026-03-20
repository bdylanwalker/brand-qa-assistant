"""Brand review orchestration.

run_brand_review(url) → dict
  Creates a thread, posts the review request, runs the agent (with automatic
  tool-call handling), extracts the JSON result from the final message.
"""

import asyncio
import concurrent.futures
import json
import logging
import re

from azure.ai.agents.models import FunctionTool, MessageRole, ToolSet  # type: ignore
from tenacity import retry, stop_after_attempt, wait_exponential

from src.agent.client import get_client
from src.config import settings

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _make_toolset() -> ToolSet:
    """Build a runtime ToolSet for create_and_process to dispatch capture_page_for_review.

    capture_page_for_review is async (Playwright). We're called from inside
    aiohttp's event loop, so asyncio.run() would fail in the current thread.
    Running it in a ThreadPoolExecutor gives it a fresh thread with no event
    loop, where asyncio.run() works correctly.
    """
    from src.agent.tools import capture_page_for_review as _async_capture

    def capture_page_for_review(url: str) -> str:  # name must match tool name on agent
        def _run_in_thread():
            return asyncio.run(_async_capture(url=url))

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(_run_in_thread).result()
        return json.dumps(result)

    toolset = ToolSet()
    toolset.add(FunctionTool(functions={capture_page_for_review}))
    return toolset


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=30),
    reraise=True,
)
async def run_brand_review(url: str) -> dict:
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

    # Create a fresh thread per review
    thread = client.threads.create()
    logger.info("Created thread %s for URL: %s", thread.id, url)

    client.messages.create(
        thread_id=thread.id,
        role=MessageRole.USER,
        content=f"Please review this URL for brand compliance: {url}",
    )

    # create_and_process handles the requires_action (tool call) loop automatically.
    # We pass a toolset so the SDK can dispatch capture_page_for_review.
    # Falls back to a manual async loop if the SDK version predates create_and_process.
    try:
        run = client.runs.create_and_process(
            thread_id=thread.id,
            agent_id=settings.agent_id,
            toolset=_make_toolset(),
        )
    except AttributeError:
        # Older SDK: manual tool-call loop
        run = await _run_with_manual_tool_loop(client, thread.id)

    logger.info("Run %s completed with status: %s", run.id, run.status)

    if run.status != "completed":
        last_error = getattr(run, "last_error", None)
        raise RuntimeError(
            f"Agent run ended with status {run.status!r}. "
            f"last_error: {last_error}"
        )

    # Extract the last agent message
    # azure-ai-agents 1.x uses MessageRole.AGENT (renamed from ASSISTANT)
    messages = client.messages.list(thread_id=thread.id)
    agent_messages = [m for m in messages if m.role == MessageRole.AGENT]
    if not agent_messages:
        raise RuntimeError("No agent message found in thread after run.")

    last_message = agent_messages[-1]
    raw_text = _extract_text(last_message)
    logger.debug("Raw agent output: %s", raw_text[:500])

    return _parse_json(raw_text, url)


async def _run_with_manual_tool_loop(client, thread_id: str):
    """Fallback: manual requires_action loop for older SDK versions."""
    from azure.ai.agents.models import ToolOutput  # type: ignore
    from src.agent.tools import capture_page_for_review as _async_capture
    import json as _json

    run = client.runs.create(thread_id=thread_id, agent_id=settings.agent_id)

    while run.status in ("queued", "in_progress", "requires_action"):
        if run.status == "requires_action":
            tool_outputs = []
            for tc in run.required_action.submit_tool_outputs.tool_calls:
                args = _json.loads(tc.function.arguments)
                if tc.function.name == "capture_page_for_review":
                    result = await _async_capture(**args)
                    output = _json.dumps(result)
                else:
                    output = _json.dumps({"error": f"Unknown tool: {tc.function.name}"})
                tool_outputs.append(ToolOutput(tool_call_id=tc.id, output=output))
            run = client.runs.submit_tool_outputs_and_poll(
                thread_id=thread_id,
                run_id=run.id,
                tool_outputs=tool_outputs,
            )
        else:
            await asyncio.sleep(1)
            run = client.runs.get(thread_id=thread_id, run_id=run.id)

    return run


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
