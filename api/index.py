"""Vercel serverless function entrypoint for Utsav Planner."""

import sys
from pathlib import Path

# Ensure repository root is in Python module search path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.main import app  # noqa: E402

__all__ = ["app"]
