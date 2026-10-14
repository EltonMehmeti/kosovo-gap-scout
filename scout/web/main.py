"""uvicorn entry point: `uv run uvicorn scout.web.main:app`."""

import os
import threading
import time

import httpx

from scout.config import get_settings
from scout.db.base import make_engine, make_session_factory
from scout.web.app import create_app

_settings = get_settings()
app = create_app(_settings, make_session_factory(make_engine(_settings.database_url)))


def _keep_awake(url: str) -> None:
    while True:
        time.sleep(600)
        try:
            httpx.get(url, timeout=30)
        except httpx.HTTPError:
            pass


# Render's free plan sleeps after 15 idle minutes; RENDER_EXTERNAL_URL is set only on Render.
if _external_url := os.environ.get("RENDER_EXTERNAL_URL"):
    threading.Thread(target=_keep_awake, args=(f"{_external_url}/healthz",), daemon=True).start()
