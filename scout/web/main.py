"""uvicorn entry point: `uv run uvicorn scout.web.main:app`."""

from scout.config import get_settings
from scout.db.base import make_engine, make_session_factory
from scout.web.app import create_app

_settings = get_settings()
app = create_app(_settings, make_session_factory(make_engine(_settings.database_url)))
