"""
Vercel serverless entry — exposes the FastAPI app from backend/main.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

os.environ.setdefault("VERCEL", "1")

from main import app  # noqa: E402
