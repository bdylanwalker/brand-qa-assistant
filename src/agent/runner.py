"""Brand review orchestration.

run_brand_review(url) → dict
  Creates a thread, posts the review request, runs the agent (with automatic
  tool-call handling), extracts the JSON result from the final message.
"""

import json
import logging
import re

from azure.ai.agents.models import MessageRole  # type: ignore
from tenacity import retry, stop_after_attempt, wait_exponential

from src.agent.client import get_client
from src.agent.tools import dispatch_tool_call
from src.config import settings

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


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
    thread = client.agents.threads.create()
    logger.info("Created thread %s for URL: %s", thread.id, url)

    client.agents.messages.create(
        thread_id=thread.id,
        role=MessageRole.USER,
        content=f"Please review this URL for brand compliance: {url}",
    )

    # create_and_process handles the requires_action (tool call) loop automatically
    # when enable_auto_function_calls is configured on the client.
    # If the SDK version doesn't support auto function calls, we handle the loop manually.
    try:
        run = client.agents.runs.create_and_process(
            thread_id=thread.id,
            agent_id=settings.agent_id,
        )
    except AttributeError:
        # Older SDK: manual tool-call loop
        run = _run_with_manual_tool_loop(client, thread.id)

    logger.info("Run %s completed with status: %s", run.id, run.status)

    if run.status != "completed":
        raise RuntimeError(f"Agent run ended with status {run.status!r}. Check Azure logs.")

    # Extract the last assistant message
    messages = client.agents.messages.list(thread_id=thread.id)
    assistant_messages = [m for m in messages if m.role == MessageRole.ASSISTANT]
    if not assistant_messages:
        raise RuntimeError("No assistant message found in thread after run.")

    last_message = assistant_messages[-1]
    raw_text = _extract_text(last_message)
    logger.debug("Raw agent output: %s", raw_text[:500])

    return _parse_json(raw_text, url)


def _run_with_manual_tool_loop(client, thread_id: str):
    """Fallback: manual requires_action loop for older SDK versions."""
    from azure.ai.agents.models import ToolOutput  # type: ignore
    import json as _json

    run = client.agents.runs.create(thread_id=thread_id, agent_id=settings.agent_id)

    while run.status in ("queued", "in_progress", "requires_action"):
        if run.status == "requires_action":
            tool_outputs = []
            for tc in run.required_action.submit_tool_outputs.tool_calls:
                args = _json.loads(tc.function.arguments)
                output = dispatch_tool_call(tc.function.name, args)
                tool_outputs.append(ToolOutput(tool_call_id=tc.id, output=output))
            run = client.agents.runs.submit_tool_outputs_and_poll(
                thread_id=thread_id,
                run_id=run.id,
                tool_outputs=tool_outputs,
            )
        else:
            import time
            time.sleep(1)
            run = client.agents.runs.get(thread_id=thread_id, run_id=run.id)

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
