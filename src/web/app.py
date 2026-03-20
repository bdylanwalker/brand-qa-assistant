"""Web server entry point for the Brand QA Assistant.

Routes:
  GET /           → serves index.html
  POST /api/review → {"url": "..."} → brand review JSON
"""

import logging
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import web

from src.agent.runner import run_brand_review

# Only URLs on these domains (or their subdomains) may be reviewed.
_APPROVED_DOMAINS = {
    "mercycorps.org",
    "mercycorps.co.uk",
    "energy4impact.org",
    "mercycorpsagrifin.org",
    "mercycorpsventures.com",
    "mercycorps.org.co",
    "gazaskygeeks.com",
    "mercycorps.ge",
    "mercycorpsguatemala.com",
    "mercycorps.or.id",
    "mercycorps.org.lb",
}


def _is_approved_url(url: str) -> bool:
    try:
        hostname = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return any(
        hostname == domain or hostname.endswith("." + domain)
        for domain in _APPROVED_DOMAINS
    )


def _is_pdf_url(url: str) -> bool:
    try:
        return urlparse(url).path.lower().endswith(".pdf")
    except Exception:
        return False

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

    if not _is_approved_url(url):
        raise web.HTTPBadRequest(
            reason="Brand QA can only review content hosted on approved domains."
        )

    is_pdf = _is_pdf_url(url)
    logger.info("Brand review requested for: %s (pdf=%s)", url, is_pdf)
    try:
        result = await run_brand_review(url, is_pdf=is_pdf)
    except Exception as exc:
        logger.exception("Brand review failed for %s", url)
        raise web.HTTPInternalServerError(text=str(exc))

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
