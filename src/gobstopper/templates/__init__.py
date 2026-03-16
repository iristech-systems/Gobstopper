"""
Template engine components for Gobstopper framework

Features:
- Jinja2 template engine (traditional file-based templates)
- DSL (gobstopper.html) — primary, zero-overhead rendering approach
"""

from .engine import TemplateEngine, TemplateRenderError

__all__ = [
    "TemplateEngine",
    "TemplateRenderError",
]
