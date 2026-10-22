"""Entry point kept at backend/main.py so `uvicorn main:app` (used by start_app.bat) works."""
from app.main import app  # noqa: F401
