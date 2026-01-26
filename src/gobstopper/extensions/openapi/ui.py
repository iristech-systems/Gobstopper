"""HTML generators for interactive OpenAPI documentation UIs.

This module provides functions to generate standalone HTML pages for interactive
API documentation using popular OpenAPI visualization tools.

Supported UIs:
    - ReDoc: Clean, three-panel documentation layout
    - Stoplight Elements: Modern, feature-rich API explorer

The generated HTML includes CDN-hosted JavaScript and CSS, requiring no
local dependencies. The HTML pages fetch the OpenAPI spec from the provided
URL and render it interactively.

Functions:
    redoc_html: Generate ReDoc documentation page
    stoplight_elements_html: Generate Stoplight Elements documentation page

Note:
    Swagger UI is intentionally NOT provided as per project requirements.

See Also:
    - ReDoc: https://redocly.github.io/redoc/
    - Stoplight Elements: https://stoplight.io/open-source/elements
"""
from __future__ import annotations


def redoc_html(spec_url: str) -> str:
    """Generate a standalone HTML page with ReDoc interactive documentation.

    ReDoc provides a clean, responsive three-panel layout with navigation,
    content, and examples. It's particularly well-suited for large APIs with
    extensive documentation.

    Features:
        - Three-panel responsive layout
        - Search functionality
        - Deep linking to operations
        - Markdown rendering in descriptions
        - Code samples for multiple languages
        - No backend required (static HTML)

    Args:
        spec_url: URL where the OpenAPI JSON specification can be fetched.
            Typically "/openapi.json" for same-origin specs.

    Returns:
        Complete HTML document string with embedded ReDoc viewer.

    Example:
        >>> html = redoc_html("/openapi.json")
        >>> # Returns HTML that will fetch and render /openapi.json

    Note:
        ReDoc is loaded from CDN (cdn.redoc.ly). Requires internet connection
        for the JavaScript bundle unless self-hosted.

    See Also:
        - ReDoc documentation: https://redocly.github.io/redoc/
        - ReDoc GitHub: https://github.com/Redocly/redoc
    """
    return f"""
<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <title>API Docs - ReDoc</title>
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  </head>
  <body>
    <redoc spec-url=\"{spec_url}\"></redoc>
        <script src=\"https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js\" crossorigin></script>

  </body>
</html>
"""


def stoplight_elements_html(spec_url: str) -> str:
    """Generate a standalone HTML page with Stoplight Elements documentation.

    Stoplight Elements provides a modern, feature-rich API explorer with
    interactive request testing and comprehensive schema visualization.

    Features:
        - Interactive "Try It" functionality
        - Request/response examples
        - Schema visualization
        - Authentication configuration
        - Dark/light theme support
        - No backend required (static HTML)

    Args:
        spec_url: URL where the OpenAPI JSON specification can be fetched.
            Typically "/openapi.json" for same-origin specs.

    Returns:
        Complete HTML document string with embedded Stoplight Elements viewer.

    Example:
        >>> html = stoplight_elements_html("/openapi.json")
        >>> # Returns HTML that will fetch and render /openapi.json with Elements

    Note:
        - Uses Stoplight Elements from unpkg.com CDN
        - Requires internet connection unless self-hosted
        - Elements supports OpenAPI 2.0, 3.0, and 3.1
        - Router is set to "hash" mode for client-side navigation

    See Also:
        - Stoplight Elements: https://stoplight.io/open-source/elements
        - Elements docs: https://meta.stoplight.io/docs/elements
    """
    # Stoplight Elements embed
    return f"""
<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <title>API Docs - Stoplight Elements</title>
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <script src=\"https://unpkg.com/@stoplight/elements/web-components.min.js\"></script>
<link rel="stylesheet" href=\"https://unpkg.com/@stoplight/elements/styles.min.css\">
  </head>
  <body>
<elements-api
  apiDescriptionUrl=\"{spec_url}\"
  router="hash"
/>
  </body>
</html>
"""


# Backward compatibility alias
scalar_html = stoplight_elements_html


# Backward compatibility alias
scalar_html = stoplight_elements_html
