"""Web server entry point for the Brand QA Assistant.

Routes:
  GET /           → serves index.html
  POST /api/review → {"url": "..."} → brand review JSON
"""

import logging
from pathlib import Path

from aiohttp import web

from src.agent.runner import run_brand_review

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


async def index(request: web.Request) -> web.Response:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return web.Response(text=html, content_type="text/html")


async def review(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(reason="Request body must be JSON")

    url = (body.get("url") or "").strip()
    if not url:
        raise web.HTTPBadRequest(reason="'url' field is required")

    logger.info("Brand review requested for: %s", url)
    try:
        result = await run_brand_review(url)
    except Exception as exc:
        logger.exception("Brand review failed for %s", url)
        raise web.HTTPInternalServerError(reason=str(exc))

    return web.json_response(result)


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_post("/api/review", review)
    return app


def main() -> None:
    app = build_app()
    web.run_app(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
