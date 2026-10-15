"""Shared pytest fixtures for mcp-calendar tests."""
import sys
from pathlib import Path

# src-layout: ensure src/ is importable in tests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
