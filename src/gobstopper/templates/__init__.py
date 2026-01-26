"""
Template engine components for Gobstopper framework

Features:
- Jinja2 template engine (traditional)
- Rust template engine (high-performance with streaming)
- Seamless fallback and integration
"""

from .engine import TemplateEngine

# Rust-powered template engine (optional)
try:
    from .rust_engine import (
        RustTemplateEngineWrapper,
        get_template_engine,
        render_template,
        render_string,
        reset_template_engine,
        RUST_AVAILABLE
    )
    
    __all__ = [
        "TemplateEngine",
        "RustTemplateEngineWrapper", 
        "get_template_engine",
        "render_template",
        "render_string", 
        "reset_template_engine",
        "RUST_AVAILABLE"
    ]
    
except ImportError:
    # Rust engine not available, use Jinja2 only
    RUST_AVAILABLE = False
    
    __all__ = [
        "TemplateEngine",
        "RUST_AVAILABLE"
    ]