"""
Custom themes for Gobstopper charts.

This module provides beautiful, modern themes designed specifically for the
Gobstopper framework. The themes use Tailwind-inspired color palettes and are
optimized for both light and dark modes.

Available Themes:
    - tempest: Light theme with vibrant colors (default)
    - tempest-dark: Dark mode variant with adjusted colors

The themes are automatically available when using ChartExtension and can
be applied by setting the theme parameter during chart creation or when
initializing the extension.

Example:
    Using the dark theme::

        charts = ChartExtension(app, theme='tempest-dark')
        chart = charts.line().build()  # Uses dark theme

    Per-chart theme override::

        chart = charts.line(theme='tempest').build()
"""

from typing import Any

# Tempest Light Theme
TEMPEST_THEME: dict[str, Any] = {
    'color': [
        '#3b82f6',  # Blue
        '#8b5cf6',  # Purple
        '#ec4899',  # Pink
        '#f59e0b',  # Amber
        '#10b981',  # Green
        '#06b6d4',  # Cyan
        '#f43f5e',  # Rose
        '#a855f7',  # Violet
    ],
    'backgroundColor': '#ffffff',
    'textStyle': {
        'fontFamily': 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        'fontSize': 14,
        'color': '#1f2937',
    },
    'title': {
        'textStyle': {
            'color': '#111827',
            'fontSize': 20,
            'fontWeight': 'bold',
        },
        'subtextStyle': {
            'color': '#6b7280',
            'fontSize': 14,
        },
    },
    'line': {
        'itemStyle': {'borderWidth': 2},
        'lineStyle': {'width': 3},
        'symbolSize': 6,
        'symbol': 'circle',
        'smooth': True,
    },
    'bar': {
        'itemStyle': {
            'borderRadius': [4, 4, 0, 0],
        },
    },
    'pie': {
        'itemStyle': {
            'borderRadius': 4,
            'borderColor': '#fff',
            'borderWidth': 2,
        },
    },
    'radar': {
        'itemStyle': {'borderWidth': 2},
        'lineStyle': {'width': 2},
        'symbolSize': 6,
        'symbol': 'circle',
    },
    'scatter': {
        'itemStyle': {'borderWidth': 0.5, 'borderColor': '#444'},
        'symbolSize': 10,
    },
    'categoryAxis': {
        'axisLine': {
            'show': True,
            'lineStyle': {'color': '#e5e7eb'},
        },
        'axisTick': {
            'show': True,
            'lineStyle': {'color': '#e5e7eb'},
        },
        'axisLabel': {
            'show': True,
            'color': '#6b7280',
        },
        'splitLine': {
            'show': False,
        },
    },
    'valueAxis': {
        'axisLine': {
            'show': False,
        },
        'axisTick': {
            'show': False,
        },
        'axisLabel': {
            'show': True,
            'color': '#6b7280',
        },
        'splitLine': {
            'show': True,
            'lineStyle': {'color': '#f3f4f6', 'type': 'dashed'},
        },
    },
    'legend': {
        'textStyle': {'color': '#4b5563'},
        'icon': 'roundRect',
    },
    'tooltip': {
        'backgroundColor': 'rgba(17, 24, 39, 0.95)',
        'borderColor': '#374151',
        'borderWidth': 1,
        'textStyle': {'color': '#f9fafb'},
    },
}

# Tempest Dark Theme
TEMPEST_DARK_THEME: dict[str, Any] = {
    'color': [
        '#60a5fa',  # Blue-400
        '#a78bfa',  # Purple-400
        '#f472b6',  # Pink-400
        '#fbbf24',  # Amber-400
        '#34d399',  # Green-400
        '#22d3ee',  # Cyan-400
        '#fb7185',  # Rose-400
        '#c084fc',  # Violet-400
    ],
    'backgroundColor': '#1f2937',
    'textStyle': {
        'fontFamily': 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        'fontSize': 14,
        'color': '#e5e7eb',
    },
    'title': {
        'textStyle': {
            'color': '#f9fafb',
            'fontSize': 20,
            'fontWeight': 'bold',
        },
        'subtextStyle': {
            'color': '#9ca3af',
            'fontSize': 14,
        },
    },
    'line': {
        'itemStyle': {'borderWidth': 2},
        'lineStyle': {'width': 3},
        'symbolSize': 6,
        'symbol': 'circle',
        'smooth': True,
    },
    'bar': {
        'itemStyle': {
            'borderRadius': [4, 4, 0, 0],
        },
    },
    'pie': {
        'itemStyle': {
            'borderRadius': 4,
            'borderColor': '#1f2937',
            'borderWidth': 2,
        },
    },
    'radar': {
        'itemStyle': {'borderWidth': 2},
        'lineStyle': {'width': 2},
        'symbolSize': 6,
        'symbol': 'circle',
    },
    'scatter': {
        'itemStyle': {'borderWidth': 0.5, 'borderColor': '#9ca3af'},
        'symbolSize': 10,
    },
    'categoryAxis': {
        'axisLine': {
            'show': True,
            'lineStyle': {'color': '#374151'},
        },
        'axisTick': {
            'show': True,
            'lineStyle': {'color': '#374151'},
        },
        'axisLabel': {
            'show': True,
            'color': '#9ca3af',
        },
        'splitLine': {
            'show': False,
        },
    },
    'valueAxis': {
        'axisLine': {
            'show': False,
        },
        'axisTick': {
            'show': False,
        },
        'axisLabel': {
            'show': True,
            'color': '#9ca3af',
        },
        'splitLine': {
            'show': True,
            'lineStyle': {'color': '#374151', 'type': 'dashed'},
        },
    },
    'legend': {
        'textStyle': {'color': '#d1d5db'},
        'icon': 'roundRect',
    },
    'tooltip': {
        'backgroundColor': 'rgba(31, 41, 55, 0.95)',
        'borderColor': '#4b5563',
        'borderWidth': 1,
        'textStyle': {'color': '#f9fafb'},
    },
}


def get_theme(theme_name: str) -> dict[str, Any] | None:
    """
    Get a theme by name.

    Args:
        theme_name: Name of the theme ('tempest', 'tempest-dark', or pyecharts built-in)

    Returns:
        Theme dictionary if custom theme, None for pyecharts built-ins
    """
    themes = {
        'tempest': TEMPEST_THEME,
        'tempest-dark': TEMPEST_DARK_THEME,
    }
    return themes.get(theme_name)


def register_tempest_themes() -> None:
    """
    Register Tempest themes with pyecharts.

    This is called automatically by ChartExtension.__init__
    """
    try:
        from pyecharts.globals import ThemeType
        from pyecharts import options as opts

        # Note: pyecharts doesn't support runtime theme registration easily
        # Themes are applied per-chart via InitOpts
        # This function is a placeholder for future enhancements
        pass
    except ImportError:
        # pyecharts not installed
        pass
