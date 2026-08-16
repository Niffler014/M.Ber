"""JARVIS Interfaces Package (UI & Gateway Integrations).

Contains adapters for LINE Webhook, CLI, and future Web UIs.
"""

from app.interfaces.line_gateway import app as line_app

__all__ = ["line_app"]
