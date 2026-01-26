"""
Gobstopper Rust Template Engine Integration

This module provides a high-performance Rust-powered template engine for Gobstopper
with streaming capabilities, hot reloading, and seamless fallback to Jinja2.
"""

import asyncio
import os
from typing import Dict, Any, Optional, AsyncGenerator, Union
from pathlib import Path

# Try to import the Rust template engine (leniently for older cores)
try:
    from gobstopper._core import RustTemplateEngine as RustEngineCore
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False
    RustEngineCore = None

# Optional components (older Rust cores may not provide these yet)
try:
    from gobstopper._core import StreamingRenderer, TemplateChunk
except Exception:
    StreamingRenderer = None
    TemplateChunk = None

try:
    from gobstopper._core import TemplateWatcher, TemplateChangeEvent
except Exception:
    TemplateWatcher = None
    TemplateChangeEvent = None

# Fallback to Jinja2 (optional)
try:
    from jinja2 import Environment, FileSystemLoader, Template
    from jinja2.exceptions import TemplateNotFound, TemplateSyntaxError
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False
    Environment = None
    FileSystemLoader = None
    Template = None
    TemplateNotFound = Exception
    TemplateSyntaxError = Exception

from ..log import logger


class RustTemplateEngineWrapper:
    """
    High-performance Rust template engine wrapper for Gobstopper.

    Features:
    - Rust-powered template rendering with Tera
    - Streaming template rendering for data-intensive dashboards
    - Hot reloading with file system watching
    - Built-in filters (currency, relative_time, tojson)
    - Optional fallback to Jinja2 when Rust is unavailable
    """

    def __init__(
        self,
        template_dir: str = "templates",
        auto_escape: bool = True,
        cache_limit: int = 1000,
        enable_streaming: bool = True,
        enable_hot_reload: bool = True,
        fallback_to_jinja: bool = False
    ):
        self.template_dir = Path(template_dir)
        self.auto_escape = auto_escape
        self.cache_limit = cache_limit
        self.enable_streaming = enable_streaming
        self.enable_hot_reload = enable_hot_reload
        self.fallback_to_jinja = fallback_to_jinja
        
        # Initialize engines
        self.rust_engine = None
        self.jinja_env = None
        self.streaming_renderer = None
        self.template_watcher = None
        self.using_rust = False
        
        # Additional template search paths (used by blueprints)
        self._extra_search_paths: list[str] = []
        # Warn-once flags
        self._warned_add_search_path: bool = False
        
        self._initialize_engines()
        
    def _initialize_engines(self):
        """Initialize the template engines with fallback logic."""

        # Try to initialize Rust engine first
        if RUST_AVAILABLE and self.template_dir.exists():
            try:
                self.rust_engine = RustEngineCore(
                    str(self.template_dir),
                    auto_escape=self.auto_escape,
                    cache_limit=self.cache_limit
                )

                if self.enable_streaming and StreamingRenderer is not None:
                    self.streaming_renderer = StreamingRenderer()

                # Hot reloading is initialized lazily when needed
                # to avoid Tokio runtime issues during import
                if self.enable_hot_reload and TemplateWatcher is not None:
                    try:
                        self.template_watcher = TemplateWatcher(
                            str(self.template_dir),
                            self.rust_engine,
                            watch_immediately=False  # Don't start immediately
                        )
                    except Exception as e:
                        logger.warning(f"Hot reload unavailable: {e}")
                        self.enable_hot_reload = False
                elif self.enable_hot_reload and TemplateWatcher is None:
                    logger.debug("Hot reload requested, but Rust core lacks TemplateWatcher; continuing without watcher")

                self.using_rust = True
                logger.info("🦀 Rust template engine initialized successfully")

            except Exception as e:
                logger.warning(f"Failed to initialize Rust engine: {e}")
                if not self.fallback_to_jinja:
                    raise

        # Fallback to Jinja2 if needed
        if not self.using_rust and self.fallback_to_jinja:
            if not JINJA2_AVAILABLE:
                raise ImportError(
                    "Jinja2 is not installed. Install it with: pip install 'gobstopper[templates]' "
                    "or pip install jinja2>=3.1.0"
                )
            try:
                loader = FileSystemLoader(str(self.template_dir))
                self.jinja_env = Environment(
                    loader=loader,
                    autoescape=self.auto_escape,
                    enable_async=True
                )

                # Add custom filters to match Rust engine
                self.jinja_env.filters['currency'] = self._currency_filter
                self.jinja_env.filters['relative_time'] = self._relative_time_filter
                self.jinja_env.filters['tojson'] = self._tojson_filter

                logger.info("📄 Jinja2 template engine initialized as fallback")

            except Exception as e:
                logger.error(f"Failed to initialize Jinja2 fallback: {e}")
                raise

        if not self.using_rust and not self.jinja_env:
            raise RuntimeError("No template engine available")
    
    async def render_template(
        self, 
        template_name: str, 
        context: Optional[Dict[str, Any]] = None,
        stream: bool = False
    ) -> Union[str, AsyncGenerator[str, None]]:
        """
        Render a template with the given context.
        
        Args:
            template_name: Name of the template file
            context: Template context variables
            stream: Whether to use streaming rendering (Rust only)
            
        Returns:
            Rendered template string or async generator for streaming
        """
        context = context or {}
        
        # Normalize explicit namespace syntax 'ns::name.html' -> 'ns/name.html'
        if '::' in template_name:
            parts = template_name.split('::', 1)
            if parts[0] and parts[1]:
                template_name = f"{parts[0]}/{parts[1]}"
        
        # If using Rust and user provided "ns/name.html", ensure the namespace is mounted
        # so we can give a clearer error message for unknown namespaces.
        if self.using_rust and '/' in template_name and hasattr(self, "_mounts"):
            first, rest = template_name.split('/', 1)
            if first and rest:
                # If looks like a namespace but not mounted, keep original to let engine try root,
                # but log a helpful hint for debugging.
                if first not in getattr(self, "_mounts", {}):
                    # Don't spam logs for common root templates like 'base.html'
                    if first not in ("base.html", "index.html") and '.' not in first:
                        logger.debug(f"Template path starts with '{first}/', which is not a mounted namespace; treating as regular path under root")
        
        if self.using_rust:
            # Attempt to render and wrap errors with more context if possible
            try:
                return await self._render_rust_template(template_name, context, stream)
            except Exception as e:
                # If Rust error exposes attributes, surface them nicely
                filename = getattr(e, 'template', template_name)
                line = getattr(e, 'line', None)
                col = getattr(e, 'column', None)
                msg = str(e)
                # Print full error for debugging
                print(f"RUST TEMPLATE ERROR: {type(e).__name__}: {msg}")
                import traceback
                traceback.print_exc()
                details = f"{msg}"
                if line is not None and col is not None:
                    details = f"{filename}:{line}:{col}: {msg}"
                raise RuntimeError(f"Template render error: {details}") from e
        else:
            return await self._render_jinja_template(template_name, context)
    
    async def render_string(
        self, 
        template_content: str, 
        context: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None
    ) -> str:
        """
        Render a template from string content.
        
        Args:
            template_content: Template source code
            context: Template context variables  
            name: Optional template name for debugging
            
        Returns:
            Rendered template string
        """
        context = context or {}
        
        if self.using_rust:
            return self.rust_engine.render_string(template_content, context, name)
        else:
            template = self.jinja_env.from_string(template_content)
            return await template.render_async(**context)
    
    async def _render_rust_template(
        self, 
        template_name: str, 
        context: Dict[str, Any],
        stream: bool = False
    ) -> Union[str, AsyncGenerator[str, None]]:
        """Render template using Rust engine."""
        
        if stream and self.streaming_renderer:
            # Streaming rendering for data-intensive dashboards
            return self._stream_rust_template(template_name, context)
        else:
            # Regular rendering
            return self.rust_engine.render(template_name, context)
    
    async def _stream_rust_template(
        self, 
        template_name: str, 
        context: Dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        """Stream template chunks for progressive rendering."""
        
        try:
            # For now, just render the full template and yield it
            # Real streaming would parse and yield chunks progressively
            content = self.rust_engine.render(template_name, context)
            
            # Simulate streaming by breaking into chunks
            chunk_size = 4096  # 4KB chunks
            for i in range(0, len(content), chunk_size):
                yield content[i:i + chunk_size]
                # Small delay to allow other async operations
                if i > 0:  # Don't delay first chunk
                    await asyncio.sleep(0.001)
                
        except Exception as e:
            logger.error(f"Streaming template error: {e}")
            # Fallback to regular rendering
            try:
                full_content = self.rust_engine.render(template_name, context)
                yield full_content
            except Exception as render_error:
                logger.error(f"Even fallback rendering failed: {render_error}")
                raise
    
    async def _render_jinja_template(
        self, 
        template_name: str, 
        context: Dict[str, Any]
    ) -> str:
        """Render template using Jinja2 fallback."""
        
        try:
            template = self.jinja_env.get_template(template_name)
            return await template.render_async(**context)
        except TemplateNotFound:
            raise FileNotFoundError(f"Template not found: {template_name}")
        except TemplateSyntaxError as e:
            raise ValueError(f"Template syntax error in {template_name}: {e}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get template engine cache statistics."""
        
        if self.using_rust:
            return self.rust_engine.cache_stats()
        else:
            return {
                "engine": "jinja2",
                "template_cache_size": len(self.jinja_env.cache) if self.jinja_env.cache else 0,
                "context_cache_size": 0,
                "cache_limit": "unlimited"
            }
    
    def clear_cache(self):
        """Clear all template caches."""
        
        if self.using_rust:
            self.rust_engine.clear_cache()
        
        if self.jinja_env and hasattr(self.jinja_env, 'cache'):
            self.jinja_env.cache.clear()
    
    def template_exists(self, template_name: str) -> bool:
        """Check if a template exists."""
        
        # Normalize ns:: syntax for both engines
        if '::' in template_name:
            parts = template_name.split('::', 1)
            if parts[0] and parts[1]:
                template_name = f"{parts[0]}/{parts[1]}"
        
        if self.using_rust:
            return self.rust_engine.template_exists(template_name)
        else:
            try:
                self.jinja_env.get_template(template_name)
                return True
            except TemplateNotFound:
                return False
    
    def list_templates(self) -> list[str]:
        """List all available templates."""
        
        if self.using_rust:
            return self.rust_engine.list_templates()
        else:
            return self.jinja_env.list_templates()
    
    def hot_reload_status(self) -> Dict[str, Any]:
        """Get hot reload status and statistics."""
        
        if self.template_watcher:
            return {
                "enabled": True,
                "watching": self.template_watcher.is_watching(),
                "template_dir": str(self.template_dir),
                "dependent_templates": self.template_watcher.get_dependent_templates("base.html")
            }
        else:
            return {
                "enabled": False,
                "watching": False,
                "template_dir": str(self.template_dir),
                "dependent_templates": []
            }
    
    # Built-in filters to match Rust engine
    @staticmethod
    def _currency_filter(value):
        """Format value as currency."""
        try:
            return f"${float(value):.2f}"
        except (ValueError, TypeError):
            return "$0.00"
    
    @staticmethod
    def _relative_time_filter(value):
        """Format as relative time."""
        return f"{value} ago"
    
    @staticmethod
    def _tojson_filter(value):
        """Convert value to JSON string."""
        import json
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            return "null"
    
    def add_filter(self, name: str, func):
        """Add a template filter (compatibility with Jinja2 API)."""
        if self.using_rust:
            # Rust engine has built-in filters, custom filters would need different implementation
            logger.warning(f"Custom filter '{name}' not supported in Rust engine, use built-in filters")
        else:
            # Jinja2 engine
            if hasattr(self.jinja_env, 'filters'):
                self.jinja_env.filters[name] = func
    
    def add_global(self, name: str, func):
        """Add a template global (compatibility with Jinja2 API)."""
        if self.using_rust:
            # Rust engine doesn't support custom globals the same way
            logger.warning(f"Custom global '{name}' not supported in Rust engine, pass via context instead")
        else:
            # Jinja2 engine
            if hasattr(self.jinja_env, 'globals'):
                self.jinja_env.globals[name] = func
    
    def add_search_path(self, path: str | os.PathLike[str], namespace: Optional[str] = None):
        """Add an additional search path for templates (used by blueprints).
        
        Behavior:
        - Rust engine: emulate multi-root via a namespaced symlink under template_dir so Tera can load
          templates from multiple roots transparently. The template will then be rendered using the
          path "<namespace>/name.html". If template names are explicitly passed as "ns::name.html",
          we translate to "ns/name.html" for convenience.
        - Jinja2 fallback: append the absolute path to the loader's searchpath list.
        
        Security:
        - The created namespace must be a simple segment (no path separators). We derive it from the
          last segment of the provided path when not given.
        - We canonicalize the target directory and refuse to mount non-existent or non-directories.
        """
        # Lazily create mounts registry
        if not hasattr(self, "_mounts"):
            self._mounts: dict[str, Path] = {}
        
        try:
            abs_path = Path(path).expanduser().resolve()
        except Exception:
            abs_path = Path(str(path))
        if not abs_path.exists() or not abs_path.is_dir():
            logger.warning(f"add_search_path ignored; not a directory: {abs_path}")
            return
        ns = namespace or abs_path.name
        # Basic namespace validation
        if "/" in ns or "\\" in ns or ns.strip() == "":
            logger.warning(f"Invalid namespace '{ns}' for template path {abs_path}")
            return
        
        # Track unique mounts
        if ns in getattr(self, "_mounts", {}):
            # If already mounted to the same path, nothing to do
            if self._mounts[ns] == abs_path:
                pass
            else:
                logger.warning(f"Namespace '{ns}' already mounted to {self._mounts[ns]}, ignoring mount to {abs_path}")
        else:
            self._mounts[ns] = abs_path
        
        # Ensure base template_dir exists
        try:
            self.template_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to ensure template_dir exists: {e}")
        
        # For Rust engine, create or verify a symlink under template_dir/<ns> -> abs_path
        link_path = (self.template_dir / ns)
        try:
            if link_path.exists() or link_path.is_symlink():
                try:
                    # If it already points to the right location, keep it
                    if link_path.is_symlink():
                        target = link_path.resolve()
                        if target == abs_path:
                            pass
                        else:
                            logger.warning(f"Namespace '{ns}' link exists but points to {target}; keeping existing to avoid clobbering")
                    else:
                        # A real directory/file exists; do not replace
                        logger.warning(f"Cannot create namespace link '{ns}': path already exists at {link_path}")
                except Exception as e:
                    logger.warning(f"Unable to verify existing namespace link '{ns}': {e}")
            else:
                # Create a symlink so Tera (and watcher) can see files under root
                os.symlink(str(abs_path), str(link_path))
        except OSError as e:
            # On platforms that disallow symlinks, we fall back to Jinja-only behavior
            logger.warning(f"Failed to create namespace symlink '{ns}': {e}")
        
        # Extend Jinja2 search paths if available
        if self.jinja_env and hasattr(self.jinja_env.loader, 'searchpath'):
            if str(abs_path) not in self.jinja_env.loader.searchpath:
                self.jinja_env.loader.searchpath.append(str(abs_path))
        
        # If hot reload is enabled and watcher exists, no extra action is needed since
        # the watcher already watches template_dir recursively and will see changes
        # through the namespace symlink. This preserves a single watcher.
        return
        
    async def render_template_async(self, template_name: str, **context):
        """Async template rendering (compatibility with Jinja2 API)."""
        return await self.render_template(template_name, context)
    
    def __repr__(self):
        engine_type = "Rust" if self.using_rust else "Jinja2"
        return f"RustTemplateEngineWrapper(engine={engine_type}, dir='{self.template_dir}')"


# Global template engine instance
_global_engine: Optional[RustTemplateEngineWrapper] = None


def get_template_engine(
    template_dir: str = "templates",
    **kwargs
) -> RustTemplateEngineWrapper:
    """
    Get or create the global template engine instance.
    
    Args:
        template_dir: Template directory path
        **kwargs: Additional arguments for template engine
        
    Returns:
        Configured template engine instance
    """
    global _global_engine
    
    if _global_engine is None:
        _global_engine = RustTemplateEngineWrapper(template_dir, **kwargs)
    
    return _global_engine


def reset_template_engine():
    """Reset the global template engine (useful for testing)."""
    global _global_engine
    _global_engine = None


# Convenience functions for direct use
async def render_template(
    template_name: str, 
    context: Optional[Dict[str, Any]] = None,
    stream: bool = False,
    **kwargs
) -> Union[str, AsyncGenerator[str, None]]:
    """
    Render a template using the global engine.
    
    Args:
        template_name: Name of the template file
        context: Template context variables
        stream: Whether to use streaming rendering
        **kwargs: Additional engine configuration
        
    Returns:
        Rendered template string or async generator
    """
    engine = get_template_engine(**kwargs)
    return await engine.render_template(template_name, context, stream)


async def render_string(
    template_content: str, 
    context: Optional[Dict[str, Any]] = None,
    **kwargs
) -> str:
    """
    Render a template from string content.
    
    Args:
        template_content: Template source code
        context: Template context variables
        **kwargs: Additional engine configuration
        
    Returns:
        Rendered template string
    """
    engine = get_template_engine(**kwargs)
    return await engine.render_string(template_content, context)