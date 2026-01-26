"""
Type definitions for the Gobstopper charts extension.

This module defines type hints and TypedDicts used throughout the
charts extension for better IDE support and type checking.

Type Aliases:
    CDNProvider: Valid CDN providers for ECharts library
    ChartTheme: Available chart themes (custom and pyecharts built-in)

TypedDicts:
    ChartOptions: Base configuration options for charts
    SeriesData: Structure for chart series data
    AxisOptions: Configuration for chart axes
"""

from typing import Literal, TypedDict
from typing_extensions import NotRequired

# CDN providers
CDNProvider = Literal['jsdelivr', 'cdnjs', 'unpkg', 'local']

# Chart themes
ChartTheme = Literal[
    'tempest',
    'tempest-dark',
    'light',
    'dark',
    'white',
    'essos',
    'macarons',
    'infographic',
    'shine',
    'roma',
    'vintage',
    'westeros',
    'wonderland',
    'chalk',
    'halloween',
    'romantic',
    'purple-passion',
]


class ChartOptions(TypedDict, total=False):
    """Base chart options for pyecharts."""
    width: NotRequired[str]
    height: NotRequired[str]
    theme: NotRequired[str]
    bg_color: NotRequired[str]
    animation_opts: NotRequired[dict]
    toolbox_opts: NotRequired[dict]


class SeriesData(TypedDict, total=False):
    """Series data structure."""
    name: str
    data: list
    smooth: NotRequired[bool]
    stack: NotRequired[str]
    label_opts: NotRequired[dict]
    itemstyle_opts: NotRequired[dict]


class AxisOptions(TypedDict, total=False):
    """Axis configuration options."""
    type_: NotRequired[str]
    name: NotRequired[str]
    min_: NotRequired[float | int | str]
    max_: NotRequired[float | int | str]
    interval: NotRequired[float | int]
