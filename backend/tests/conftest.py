"""Test isolation: a throwaway data directory and no external services.

These run before ``app.config`` is imported; ``load_dotenv`` never overrides
variables that are already set, so backend/.env cannot leak into tests.
"""
import os
import shutil
import tempfile

import pytest

_DATA = tempfile.mkdtemp(prefix="turbotranscribe-test-")
os.environ["DATA_DIR"] = _DATA
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["DIARIZATION"] = "false"
os.environ["KEEP_MEDIA"] = "true"


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_DATA, ignore_errors=True)


@pytest.fixture
def ffmpeg():
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
