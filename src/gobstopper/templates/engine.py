"""
Jinja2 template engine for Gobstopper framework
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Union

try:
    import jinja2
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False
    jinja2 = None


class TemplateEngine:
    """Jinja2-based template engine with async support"""
    
    def __init__(self, 
                 template_folder: Union[str, Path] = "templates",
                 auto_reload: bool = True,
                 cache_size: int = 400):
        
        if not JINJA2_AVAILABLE:
            raise ImportError("Jinja2 is required for templating. Install: uv add jinja2")
        
        self.template_folder = Path(template_folder)
        loader = FileSystemLoader(str(self.template_folder))
        
        self.env = Environment(
            loader=loader,
            autoescape=select_autoescape(['html', 'xml']),
            auto_reload=auto_reload,
            cache_size=cache_size,
            enable_async=True
        )
        
        self._add_default_filters()
        self._add_default_globals()
        
    def add_search_path(self, path: Union[str, Path]):
        """Add an additional search path for templates (used by blueprints)."""
        p = str(Path(path))
        try:
            # FileSystemLoader has .searchpath list
            if hasattr(self.env.loader, 'searchpath'):
                if p not in self.env.loader.searchpath:
                    self.env.loader.searchpath.append(p)
        except Exception:
            pass
    
    def _add_default_filters(self):
        """Add default template filters"""
        def tojson_filter(obj):
            return json.dumps(obj)
        
        def currency_filter(amount):
            return f"${amount:,.2f}"
        
        def relative_time_filter(timestamp):
            diff = time.time() - timestamp
            if diff < 60:
                return f"{int(diff)}s ago"
            elif diff < 3600:
                return f"{int(diff // 60)}m ago"
            elif diff < 86400:
                return f"{int(diff // 3600)}h ago"
            else:
                return f"{int(diff // 86400)}d ago"

        self.env.filters['tojson'] = tojson_filter
        self.env.filters['currency'] = currency_filter
        self.env.filters['relative_time'] = relative_time_filter
    def _add_default_globals(self):
        """Add default global variables"""
        self.env.globals.update({
            'now': datetime.now,
            'timestamp': time.time,
            'range': range, 'len': len, 'str': str, 'int': int, 'float': float, 'bool': bool,
        })
    
    async def render_template_async(self, template_name: str, **context) -> str:
        """Render template asynchronously"""
        try:
            template = self.env.get_template(template_name)
            return await template.render_async(**context)
        except jinja2.TemplateNotFound:
            raise FileNotFoundError(f"Template '{template_name}' not found")
    
    def add_filter(self, name: str, func):
        """Add a custom filter"""
        self.env.filters[name] = func
    
    def add_global(self, name: str, func):
        """Add a custom global function"""
        self.env.globals[name] = func